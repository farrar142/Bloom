# Method Advice 패턴

MethodAdvice 패턴은 메서드 호출을 가로채어 전처리/후처리 로직을 실행하는 AOP(Aspect-Oriented Programming) 패턴입니다.

## 목차

1. [아키텍처 개요](#아키텍처-개요)
2. [핵심 컴포넌트](#핵심-컴포넌트)
3. [사용 방법](#사용-방법)
4. [실행 흐름](#실행-흐름)
5. [고급 기능](#고급-기능)
6. [주의사항](#주의사항)

---

## 아키텍처 개요

### 컴포넌트 관계도

```
┌─────────────────────────────────────────────────────────────────┐
│                        Application                               │
│                                                                   │
│  1. ready() 호출 시:                                              │
│     - MethodInvocationManager 생성                                │
│     - initialize(ContainerManager) 호출                          │
│     - HandlerContainer 메서드들에 MethodProxy 적용                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                  MethodInvocationManager                         │
│                                                                   │
│  - Application에서 생성 (DI 컨테이너에 등록되지 않음)              │
│  - initialize()에서 ContainerManager로부터 Registry 조회          │
│  - invoke() / invoke_sync()로 Advice 체인 실행                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │ get_sub_instances(MethodAdviceRegistry)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                   MethodAdviceRegistry                           │
│                                                                   │
│  - @Factory로 생성하여 DI 컨테이너에 등록                         │
│  - MethodAdvice 인스턴스들을 수집                                 │
│  - find_applicable(container)로 적용 가능한 Advice 반환           │
└──────────────────────────┬──────────────────────────────────────┘
                           │ register()
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                       MethodAdvice                               │
│                                                                   │
│  - @Component로 등록하여 DI 컨테이너에서 관리                     │
│  - supports()로 적용 여부 결정                                    │
│  - before/after/on_error 훅 제공                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 관리 주체 요약

| 컴포넌트 | 생성 방법 | 관리 주체 | 역할 |
|---------|----------|----------|------|
| `MethodAdvice` | `@Component` | DI Container | 개별 Advice 로직 정의 |
| `MethodAdviceRegistry` | `@Factory` | DI Container | Advice 수집 및 조회 |
| `MethodInvocationManager` | `Application` 직접 생성 | Application | Registry 조회, Advice 체인 실행 |

---

## 핵심 컴포넌트

### 1. MethodAdvice (추상 클래스)

메서드 호출 전후에 실행되는 로직을 정의합니다.

```python
from abc import ABC, abstractmethod
from typing import Any, Callable
from bloom.core.container import HandlerContainer
from bloom.core.advice import InvocationContext

class MethodAdvice(ABC):
    """메서드 호출 전후에 실행되는 어드바이스"""

    @abstractmethod
    def supports(self, container: HandlerContainer) -> bool:
        """
        이 Container에 Advice를 적용할지 결정합니다.
        
        Container의 Element(메타데이터)를 확인하여 판단합니다.
        """
        ...

    # === 비동기 메서드용 훅 ===
    
    async def before(self, context: InvocationContext) -> None:
        """메서드 실행 전 호출"""
        pass

    async def after(self, context: InvocationContext, result: Any) -> Any:
        """메서드 실행 후 호출 (결과 수정 가능)"""
        return result

    async def on_error(self, context: InvocationContext, error: Exception) -> Any:
        """예외 발생 시 호출 (복구하거나 재throw)"""
        raise error

    # === 동기 메서드용 훅 ===
    
    def before_sync(self, context: InvocationContext) -> None:
        """동기 메서드 실행 전 호출"""
        pass

    def after_sync(self, context: InvocationContext, result: Any) -> Any:
        """동기 메서드 실행 후 호출"""
        return result

    def on_error_sync(self, context: InvocationContext, error: Exception) -> Any:
        """동기 메서드 예외 발생 시 호출"""
        raise error

    # === 호출 가로채기 ===
    
    def invoke_sync(self, context: InvocationContext, proceed: Callable) -> Any | None:
        """
        동기 호출을 완전히 가로챕니다.
        
        Returns:
            None: 가로채지 않음 (기본 before/after 흐름 진행)
            Any: 가로챔 (이 값이 최종 결과)
        """
        return None

    async def invoke_async(self, context: InvocationContext, proceed: Callable) -> Any | None:
        """비동기 호출을 완전히 가로챕니다."""
        return None
```

### 2. MethodAdviceRegistry

Advice 인스턴스들을 수집하고 조회합니다. **반드시 `@Factory`로 생성해야 합니다.**

```python
from bloom.core.advice import MethodAdviceRegistry

class MethodAdviceRegistry:
    """MethodAdvice를 수집하고 조회하는 Registry"""

    def register(self, advice: MethodAdvice) -> None:
        """Advice를 등록합니다."""
        ...

    def find_applicable(self, container: HandlerContainer) -> list[MethodAdvice]:
        """
        주어진 Container에 적용 가능한 Advice 목록을 반환합니다.
        
        각 Advice의 supports()를 호출하여 필터링합니다.
        """
        ...

    def __len__(self) -> int:
        """등록된 Advice 개수"""
        ...
```

### 3. MethodInvocationManager

Advice 체인을 실행하는 Manager입니다. **Application에서 직접 생성합니다.**

```python
from bloom.core.advice import MethodInvocationManager

class MethodInvocationManager:
    """메서드 호출 시 Advice 체인을 관리"""

    def __init__(self, registry: MethodAdviceRegistry | None = None):
        """
        생성자
        
        Args:
            registry: 테스트용으로 Registry를 직접 주입할 때 사용
        """
        ...

    def initialize(self, container_manager: ContainerManager | None = None) -> None:
        """
        Manager 초기화
        
        ContainerManager에서 @Factory로 생성된 MethodAdviceRegistry를 조회합니다.
        """
        ...

    async def invoke(self, container, instance, handler, *args, **kwargs) -> Any:
        """비동기 Advice 체인 실행"""
        ...

    def invoke_sync(self, container, instance, handler, *args, **kwargs) -> Any:
        """동기 Advice 체인 실행"""
        ...
```

### 4. InvocationContext

Advice 간에 데이터를 공유하기 위한 컨텍스트입니다.

```python
from bloom.core.advice import InvocationContext

class InvocationContext:
    """호출 컨텍스트 - Advice 간 데이터 공유"""
    
    container: HandlerContainer  # 핸들러 컨테이너
    instance: Any                # 메서드가 바인딩된 인스턴스
    args: tuple                  # 위치 인자
    kwargs: dict                 # 키워드 인자

    def set_attribute(self, key: str, value: Any) -> None:
        """속성 설정 (before에서 저장, after에서 조회)"""
        ...

    def get_attribute(self, key: str, default: Any = None) -> Any:
        """속성 조회"""
        ...
```

---

## 사용 방법

### 1. Element 정의 (마커)

Advice 적용 여부를 결정하는 마커 Element를 정의합니다.

```python
from bloom.core.container.element import Element

class TransactionalElement(Element):
    """트랜잭션 적용 마커"""
    pass

class CacheableElement(Element):
    """캐시 적용 마커"""
    def __init__(self, ttl: int = 60):
        super().__init__()
        self.metadata["ttl"] = ttl
```

### 2. 데코레이터 정의 (선택사항)

Element를 적용하는 편의 데코레이터를 만듭니다.

```python
from bloom.core.container import HandlerContainer

def Transactional(method):
    """@Transactional 데코레이터"""
    container = HandlerContainer.get_or_create(method)
    container.add_elements(TransactionalElement())
    return method

def Cacheable(ttl: int = 60):
    """@Cacheable(ttl=300) 데코레이터"""
    def decorator(method):
        container = HandlerContainer.get_or_create(method)
        container.add_elements(CacheableElement(ttl))
        return method
    return decorator
```

### 3. MethodAdvice 구현

```python
from bloom import Component
from bloom.core.advice import MethodAdvice, InvocationContext
from bloom.core.container import HandlerContainer

@Component
class TransactionAdvice(MethodAdvice):
    """트랜잭션 관리 Advice"""
    
    db: Database  # DI로 주입

    def supports(self, container: HandlerContainer) -> bool:
        # TransactionalElement가 있는 메서드에만 적용
        return container.has_element(TransactionalElement)

    async def before(self, context: InvocationContext) -> None:
        tx = await self.db.begin()
        context.set_attribute("tx", tx)

    async def after(self, context: InvocationContext, result: Any) -> Any:
        tx = context.get_attribute("tx")
        await tx.commit()
        return result

    async def on_error(self, context: InvocationContext, error: Exception) -> Any:
        tx = context.get_attribute("tx")
        await tx.rollback()
        raise error
```

### 4. Registry 생성 (@Factory 필수!)

**⚠️ 중요**: Registry는 반드시 `@Factory`로 생성해야 합니다.

```python
from bloom import Component
from bloom.core.decorators import Factory
from bloom.core.advice import MethodAdvice, MethodAdviceRegistry

@Component
class AdviceConfig:
    
    @Factory
    def advice_registry(self, *advices: MethodAdvice) -> MethodAdviceRegistry:
        """
        @Factory로 Registry 생성
        
        *advices: MethodAdvice - 모든 @Component MethodAdvice가 자동 주입됨
        """
        registry = MethodAdviceRegistry()
        for advice in advices:
            registry.register(advice)
        return registry
```

### 5. 서비스에서 사용

```python
from bloom import Component

@Component
class OrderService:
    
    @Transactional  # HandlerContainer가 이미 생성됨 - @Handler 불필요
    async def create_order(self, order_data: dict) -> Order:
        """트랜잭션 내에서 주문 생성"""
        # TransactionAdvice가 자동으로 적용됨
        order = Order(**order_data)
        await self.order_repo.save(order)
        return order
```

### 6. Application 시작

```python
from bloom import Application

app = (
    Application("my_app")
    .scan(TransactionAdvice, AdviceConfig, OrderService)
    .ready()  # 여기서 MethodProxy가 자동 적용됨
)

# 사용
order_service = app.manager.get_instance(OrderService)
order = await order_service.create_order({"item": "book"})
# → TransactionAdvice.before() → create_order() → TransactionAdvice.after()
```

---

## 실행 흐름

### 정상 흐름

```
요청 → Advice1.before() → Advice2.before() → handler() → Advice2.after() → Advice1.after() → 응답
```

- `before`: 등록 순서대로 실행
- `after`: 역순으로 실행

### 예외 발생 시

```
요청 → Advice1.before() → Advice2.before() → handler() [예외!]
                                                    ↓
      Advice1.on_error() ← Advice2.on_error() ←────┘
             ↓
         예외 전파 또는 복구
```

### 코드로 보는 흐름

```python
# 실행 순서 예시
class Advice1(MethodAdvice):
    async def before(self, ctx): print("1. Advice1.before")
    async def after(self, ctx, result): 
        print("4. Advice1.after")
        return result

class Advice2(MethodAdvice):
    async def before(self, ctx): print("2. Advice2.before")
    async def after(self, ctx, result): 
        print("3. Advice2.after")
        return result

# registry.register(Advice1())
# registry.register(Advice2())
# 
# 출력:
# 1. Advice1.before
# 2. Advice2.before
# (handler 실행)
# 3. Advice2.after
# 4. Advice1.after
```

---

## 고급 기능

### invoke_sync / invoke_async로 호출 가로채기

기본 before/after 흐름을 완전히 대체할 때 사용합니다.

```python
from bloom.core.advice import MethodAdvice, AsyncTask

class AsyncMethodAdvice(MethodAdvice):
    """@Async 메서드를 ThreadPool에서 실행"""
    
    def __init__(self, executor: ThreadPoolExecutor):
        self.executor = executor

    def supports(self, container: HandlerContainer) -> bool:
        return container.has_element(AsyncElement)

    def invoke_sync(self, context: InvocationContext, proceed: Callable) -> AsyncTask:
        # proceed()를 ThreadPool에 제출
        future = self.executor.submit(proceed)
        return AsyncTask(future)  # None이 아니므로 이 값이 최종 결과
```

### Context를 통한 데이터 공유

```python
class AuthAdvice(MethodAdvice):
    async def before(self, context: InvocationContext) -> None:
        user = await self.auth_service.get_current_user()
        context.set_attribute("current_user", user)

class AuditAdvice(MethodAdvice):
    async def after(self, context: InvocationContext, result: Any) -> Any:
        user = context.get_attribute("current_user")  # AuthAdvice에서 설정한 값
        await self.audit_log.record(user, result)
        return result
```

### 결과 수정

```python
class CacheAdvice(MethodAdvice):
    async def before(self, context: InvocationContext) -> None:
        cache_key = self._make_key(context.args, context.kwargs)
        cached = await self.cache.get(cache_key)
        if cached:
            context.set_attribute("cached_result", cached)

    async def after(self, context: InvocationContext, result: Any) -> Any:
        cached = context.get_attribute("cached_result")
        if cached:
            return cached  # 캐시된 값 반환
        
        cache_key = self._make_key(context.args, context.kwargs)
        await self.cache.set(cache_key, result)
        return result
```

### 에러 복구

```python
class RetryAdvice(MethodAdvice):
    async def on_error(self, context: InvocationContext, error: Exception) -> Any:
        if isinstance(error, TransientError):
            # 복구 가능한 에러면 기본값 반환
            return {"status": "retry_later"}
        # 그 외에는 예외 전파
        raise error
```

---

## 주의사항

### 1. supports()는 Element 기반으로 판단

```python
# ✅ 올바른 방법
def supports(self, container: HandlerContainer) -> bool:
    return container.has_element(TransactionalElement)

# ❌ 잘못된 방법 - Container 타입 비교 금지
def supports(self, container: HandlerContainer) -> bool:
    return isinstance(container, SomeSpecificContainer)
```

### 2. Registry는 반드시 @Factory로 생성

```python
# ✅ 올바른 방법
@Component
class AdviceConfig:
    @Factory
    def advice_registry(self, *advices: MethodAdvice) -> MethodAdviceRegistry:
        registry = MethodAdviceRegistry()
        for advice in advices:
            registry.register(advice)
        return registry

# ❌ 잘못된 방법 - @Component로 직접 등록
@Component
class MethodAdviceRegistry:  # 이렇게 하면 안 됨!
    pass
```

### 3. MethodInvocationManager는 DI에 등록하지 않음

```python
# Application 내부에서 직접 생성됨
class Application:
    def _apply_method_proxies(self):
        # Manager는 Application에서 직접 생성
        self._invocation_manager = MethodInvocationManager()
        # ContainerManager에서 Registry 조회
        self._invocation_manager.initialize(self.manager)
```

### 4. HandlerContainer가 없으면 Advice 미적용

Advice는 `HandlerContainer`가 있는 메서드에만 적용됩니다.  
`@Handler`, `@Transactional` 등 HandlerContainer를 생성하는 데코레이터를 사용해야 합니다.

```python
@Component
class MyService:
    @Handler  # HandlerContainer 생성됨
    def with_handler(self): ...  # Advice 적용 ✅
    
    @Transactional  # HandlerContainer 생성됨 (get_or_create)
    def with_transactional(self): ...  # Advice 적용 ✅
    
    def plain_method(self): ...  # HandlerContainer 없음 → Advice 미적용 ❌
```

---

## 테스트 방법

### 단위 테스트 (Registry 직접 주입)

```python
def test_advice():
    # Given
    registry = MethodAdviceRegistry()
    registry.register(MyAdvice())
    manager = MethodInvocationManager(registry)  # 테스트용 직접 주입

    container = MockHandlerContainer()
    container.add_elements(MyElement())

    def handler():
        return "result"

    # When
    result = manager.invoke_sync(container, None, handler)

    # Then
    assert result == "result"
```

### 통합 테스트 (Application 사용)

```python
def test_advice_with_di():
    # Given
    @Component
    class AdviceConfig:
        @Factory
        def advice_registry(self) -> MethodAdviceRegistry:
            registry = MethodAdviceRegistry()
            registry.register(LoggingAdvice())
            return registry

    @Component
    class MyService:
        @Handler
        def do_something(self) -> str:
            return "result"

    # When
    app = Application("test").scan(AdviceConfig, MyService).ready()
    service = app.manager.get_instance(MyService)
    result = service.do_something()

    # Then
    assert result == "result"
```

---

## 관련 파일

```
bloom/core/advice/
├── __init__.py          # 모듈 export
├── base.py              # MethodAdvice ABC
├── context.py           # InvocationContext
├── registry.py          # MethodAdviceRegistry
├── manager.py           # MethodInvocationManager
├── proxy.py             # MethodProxy
└── builtin/
    └── async_advice.py  # @Async, AsyncTask, AsyncElement
```
