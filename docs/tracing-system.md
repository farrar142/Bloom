# 콜스택 추적 시스템 (Tracing)

## 개요

Bloom 프레임워크는 모든 컴포넌트의 메서드 호출을 자동으로 추적하는 시스템을 제공합니다.
`ContextVar`와 불변 튜플을 사용하여 **async/multithread 환경에서 안전**합니다.

## 빠른 시작

```python
from bloom import Application, Component
from bloom.core.decorators import Factory
from bloom.core.advice import (
    MethodAdvice,
    MethodAdviceRegistry,
    CallStackTraceAdvice,
    CallFrame,
    get_call_stack,
)

# 1. 커스텀 트레이싱 Advice 정의
@Component
class LoggingTraceAdvice(CallStackTraceAdvice):
    include_args = True  # 인자 요약 포함

    def on_enter(self, frame: CallFrame) -> None:
        indent = "  " * frame.depth
        print(f"{indent}→ {frame.full_name}({frame.args_summary})")

    def on_exit(self, frame: CallFrame, duration_ms: float) -> None:
        indent = "  " * frame.depth
        print(f"{indent}← {frame.full_name} [{duration_ms:.2f}ms]")

    def on_error(self, frame: CallFrame, error: Exception) -> None:
        indent = "  " * frame.depth
        print(f"{indent}✗ {frame.full_name} ERROR: {error}")

# 2. Registry 설정 (필수!)
@Component
class AdviceConfig:
    @Factory
    def advice_registry(self, *advices: MethodAdvice) -> MethodAdviceRegistry:
        registry = MethodAdviceRegistry()
        for advice in advices:
            registry.register(advice)
        return registry

# 3. 앱에서 사용
app = Application("myapp")
app.scan(LoggingTraceAdvice)
app.scan(AdviceConfig)
app.scan(MyService)  # 비즈니스 로직
app.ready()
```

## 출력 예시

```
→ UserController.get_user_detail(42)
  → UserService.get_user(42)
    → UserRepository.find_by_id(42)
    ← UserRepository.find_by_id [0.01ms]
  ← UserService.get_user [0.06ms]
← UserController.get_user_detail [0.14ms]
```

## 핵심 컴포넌트

### CallFrame

메서드 호출을 나타내는 **불변** 객체입니다.

```python
@dataclass(frozen=True)
class CallFrame:
    instance_type: str   # 클래스명 (예: "UserService")
    method_name: str     # 메서드명 (예: "get_user")
    start_time: float    # 호출 시작 시간
    trace_id: str        # 요청별 추적 ID
    depth: int           # 콜스택 깊이 (0부터)
    args_summary: str    # 인자 요약 (선택)

    @property
    def full_name(self) -> str:
        return f"{self.instance_type}.{self.method_name}"

    @property
    def elapsed_ms(self) -> float:
        return (time.time() - self.start_time) * 1000
```

### Context API

어디서든 현재 콜스택을 조회할 수 있습니다.

```python
from bloom.core.advice import (
    get_call_stack,      # 전체 스택 조회
    get_current_frame,   # 현재 프레임
    get_call_depth,      # 스택 깊이
    get_trace_id,        # 추적 ID
    set_trace_id,        # 추적 ID 설정
)

# 현재 콜스택 출력
for frame in get_call_stack():
    print(f"  {frame}")

# 현재 프레임
current = get_current_frame()
if current:
    print(f"현재: {current.full_name}")
```

### CallStackTraceAdvice

확장 가능한 베이스 클래스입니다.

| 메서드                        | 호출 시점   | 용도            |
| ----------------------------- | ----------- | --------------- |
| `on_enter(frame)`             | 메서드 진입 | 로깅, span 시작 |
| `on_exit(frame, duration_ms)` | 정상 종료   | 로깅, 메트릭    |
| `on_error(frame, error)`      | 예외 발생   | 에러 로깅       |

## async/multithread 안전성

`ContextVar`와 **불변 튜플**을 사용하여 각 코루틴/스레드가 독립적인 콜스택을 가집니다.

```python
# 내부 구현
_call_stack: ContextVar[tuple[CallFrame, ...]] = ContextVar(
    "bloom_call_stack", default=()
)

def push_frame(...) -> CallFrame:
    current_stack = _call_stack.get()
    frame = CallFrame(...)
    # 새 튜플 생성 (불변성 유지)
    _call_stack.set(current_stack + (frame,))
    return frame

def pop_frame() -> CallFrame | None:
    current_stack = _call_stack.get()
    if not current_stack:
        return None
    frame = current_stack[-1]
    # 새 튜플 생성 (불변성 유지)
    _call_stack.set(current_stack[:-1])
    return frame
```

### 왜 불변 튜플인가?

```python
# ❌ 위험: 가변 리스트
_stack: ContextVar[list] = ContextVar("stack", default=[])
# 문제: default=[]가 모든 코루틴에서 공유됨!

# ✅ 안전: 불변 튜플
_stack: ContextVar[tuple] = ContextVar("stack", default=())
# 각 set() 호출마다 새 튜플 생성 → 독립성 보장
```

## 자동 프록시 적용

`@Handler` 데코레이터 없이도 모든 컴포넌트의 메서드에 자동으로 프록시가 적용됩니다.

```python
# Application._apply_proxies_to_instance()에서:
container = HandlerContainer.get_container(attr)
if container is None:
    # HandlerContainer가 없으면 자동 생성
    original_func = getattr(attr, "__func__", attr)
    container = HandlerContainer.get_or_create(original_func)

# 프록시 적용
proxy = MethodProxy(container, instance, attr, invocation_manager)
setattr(instance, name, proxy)
```

### 제외되는 클래스

무한 재귀 방지를 위해 일부 인프라 클래스는 프록시가 적용되지 않습니다:

- `MethodAdvice` 및 하위 클래스
- `MethodAdviceRegistry`

## 활용 사례

### 1. 로깅

```python
@Component
class LoggingAdvice(CallStackTraceAdvice):
    logger: Logger

    def on_enter(self, frame: CallFrame) -> None:
        self.logger.debug(f"→ {frame.full_name}")

    def on_exit(self, frame: CallFrame, duration_ms: float) -> None:
        self.logger.debug(f"← {frame.full_name} ({duration_ms:.2f}ms)")
```

### 2. 성능 메트릭

```python
@Component
class MetricsAdvice(CallStackTraceAdvice):
    metrics: MetricsClient

    def on_exit(self, frame: CallFrame, duration_ms: float) -> None:
        self.metrics.histogram(
            "method_duration_ms",
            duration_ms,
            tags={"method": frame.full_name}
        )
```

### 3. 분산 트레이싱 (OpenTelemetry)

```python
@Component
class OTelAdvice(CallStackTraceAdvice):
    tracer: Tracer

    def on_enter(self, frame: CallFrame) -> None:
        span = self.tracer.start_span(frame.full_name)
        # span을 어딘가에 저장 (context 등)

    def on_exit(self, frame: CallFrame, duration_ms: float) -> None:
        span = # 저장된 span 가져오기
        span.end()
```

## PROTOTYPE 자동 정리

콜스택 시스템은 PROTOTYPE 스코프 인스턴스의 자동 정리도 담당합니다.

### 동작 원리

1. **메서드 진입**: `push_frame()`으로 새 depth 생성
2. **PROTOTYPE 생성**: `LazyFieldProxy`가 `register_prototype(instance, container)` 호출
3. **메서드 종료**: `pop_frame()`에서 `cleanup_prototypes_at_depth(depth)` 자동 호출
4. **@PreDestroy 실행**: 해당 depth에서 생성된 모든 PROTOTYPE의 `@PreDestroy` 호출

```python
from bloom.core.advice.tracing.context import (
    register_prototype,           # PROTOTYPE 등록
    cleanup_prototypes_at_depth,  # 특정 depth 정리
    get_prototype_count_at_depth, # 디버깅용
)
```

자세한 내용은 [PROTOTYPE 스코프와 자동 라이프사이클 관리](./prototype-scope.md) 참조.

## 시스템 이벤트 발행

`CallStackTraceAdvice`는 메서드 호출 시 시스템 이벤트를 발행합니다:

| 시점 | 이벤트 |
|------|--------|
| 메서드 진입 | `MethodEnteredEvent` |
| 정상 종료 | `MethodExitedEvent` |
| 예외 발생 | `MethodErrorEvent` |

```python
from bloom.core.events import (
    MethodEnteredEvent,
    MethodExitedEvent,
    MethodErrorEvent,
)
```

자세한 내용은 [이벤트 시스템](./event-system.md) 참조.

## 파일 구조

```
bloom/core/advice/tracing/
├── __init__.py      # 패키지 exports
├── frame.py         # CallFrame 정의
├── context.py       # ContextVar 기반 스택 관리, PROTOTYPE 추적
└── advice.py        # CallStackTraceAdvice
```

## 관련 문서

- [PROTOTYPE 스코프와 자동 라이프사이클 관리](./prototype-scope.md)
- [이벤트 시스템](./event-system.md)
- [Method Advice 패턴](./method-advice-pattern.md)
- [Architecture Patterns](./architecture-patterns.md)
