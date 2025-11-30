# Factory Chain과 의존성 그래프

## 개요

Bloom 프레임워크의 DI 컨테이너는 **토폴로지컬 정렬(Topological Sort)** 기반의 의존성 그래프를 사용하여 컴포넌트 초기화 순서를 결정합니다. 특히 **Factory Chain** 패턴을 지원하여, 동일한 타입을 반환하는 여러 Factory가 순차적으로 인스턴스를 생성/수정할 수 있습니다.

## Factory Chain이란?

Factory Chain은 동일한 타입을 반환하는 여러 `@Factory` 메서드가 체인 형태로 연결되어 실행되는 패턴입니다.

### 기본 구조

```python
@Component
class CounterConfig:
    @Factory
    def create(self) -> Counter:
        """Creator: 최초 인스턴스 생성"""
        return Counter(0)

    @Factory
    @Order(1)
    def add_one(self, counter: Counter) -> Counter:
        """Modifier: 기존 인스턴스 수정"""
        counter.value += 1
        return counter

    @Factory
    @Order(2)
    def add_two(self, counter: Counter) -> Counter:
        """Modifier: 추가 수정"""
        counter.value += 2
        return counter
```

실행 순서: `create()` → `add_one()` → `add_two()`
결과: `Counter(3)` (0 + 1 + 2)

### Creator vs Modifier

| 구분     | Creator                          | Modifier                    |
| -------- | -------------------------------- | --------------------------- |
| **정의** | 자기 타입을 의존성으로 갖지 않음 | 자기 타입을 의존성으로 가짐 |
| **역할** | 최초 인스턴스 생성               | 기존 인스턴스 수정          |
| **개수** | 체인당 1개만 허용                | 여러 개 가능                |

```python
# Creator - Counter를 의존하지 않음
def create(self) -> Counter:
    return Counter(0)

# Modifier - Counter를 의존함
def modify(self, counter: Counter) -> Counter:
    counter.value += 1
    return counter
```

## 의존성 그래프 구축 알고리즘

### 1단계: 타입별 그룹핑

모든 컨테이너를 반환 타입별로 그룹핑합니다.

```
Counter → [create, add_one, add_two]
Service → [create_service]
```

### 2단계: 그룹 내 정렬

같은 타입을 반환하는 Factory들을 다음 기준으로 정렬:

1. **@Order 데코레이터**: 값이 낮을수록 먼저 실행
2. **의존성 기반**: Creator(자기 타입 미의존) → Modifier(자기 타입 의존)

```python
def get_intra_type_order(item, target_type):
    # 1. @Order가 있으면 Order 값 사용
    if has_order(item):
        return (1, order_value)

    # 2. Order가 없으면 의존성 기반
    if target_type in item.dependencies:
        return (0, 1000)   # Modifier: 나중에
    else:
        return (0, -1000)  # Creator: 먼저
```

### 3단계: Chain 내부 연결

같은 타입의 Factory들을 순서대로 연결합니다.

```
Counter Chain:
create ──→ add_one ──→ add_two
```

### 4단계: 외부 타입 의존성 연결 (핵심!)

Factory가 외부 타입에 의존할 때, **순환을 방지**하면서 연결해야 합니다.

#### 문제 상황: 다이아몬드 의존성

```python
@Component
class Config:
    @Factory
    def create_counter(self) -> Counter:
        return Counter(0)

    @Factory
    @Order(1)
    def add_five(self, c: Counter) -> Counter:
        c.value += 5
        return c

    @Factory
    def create_transformer(self, c: Counter) -> Transformer:
        return Transformer(c.value)

    @Factory
    @Order(2)
    def transform(self, t: Transformer, c: Counter) -> Counter:
        return t.apply(c)
```

의존성 관계:

```
Counter 체인: create_counter → add_five → transform
Transformer 체인: create_transformer

transform → Transformer (외부 의존)
create_transformer → Counter (외부 의존)
```

#### 순환 발생 조건

단순히 "마지막 Factory에 연결"하면 순환이 발생합니다:

```
transform → Transformer.last(create_transformer) → Counter.last(transform)
                                                          ↑
                                                    순환 발생!
```

#### 해결책: Eligible Factory 선택

외부 타입에 의존할 때, 그 타입의 Chain에서 **현재 아이템의 타입을 의존하지 않는 Factory들 중 마지막**에 연결합니다.

```python
for dep_type in item.dependencies:
    if dep_type == item.target:
        continue  # 자기 타입은 Chain 내부에서 처리됨

    # 의존 타입의 Chain에서 eligible Factory 찾기
    eligible_deps = []
    for dep_item in dep_chain:
        if item.target not in dep_item.dependencies:
            eligible_deps.append(dep_item)

    if eligible_deps:
        # eligible한 것들 중 마지막에 연결
        connect(eligible_deps[-1], item)
    else:
        # 모두 현재 타입을 의존하면 첫 번째(Creator)에 연결
        connect(dep_chain[0], item)
```

#### 적용 예시

`transform`이 `Transformer`에 의존:

- Transformer Chain: `[create_transformer]`
- `create_transformer`는 `Counter`를 의존
- `Counter`는 `transform`의 타입 → eligible 아님!
- eligible 없음 → 첫 번째(`create_transformer`)에 연결

`create_transformer`가 `Counter`에 의존:

- Counter Chain: `[create_counter, add_five, transform]`
- `create_counter`: 의존 없음 → eligible ✓
- `add_five`: `Counter` 의존 (자기 타입) → eligible ✓
- `transform`: `Transformer` 의존 → eligible ✓ (Transformer ≠ Counter)
- 하지만 `transform`은 `Transformer`를 의존하고, `Transformer`는 `Counter`를 의존
- 따라서 `add_five`까지만 eligible

결과 그래프:

```
Config ──→ create_counter ──→ add_five ──→ create_transformer ──→ transform
```

## 그래프 시각화

### 단순 Factory Chain

```
┌─────────┐     ┌─────────┐     ┌─────────┐
│ create  │────▶│ add_one │────▶│ add_two │
│Counter=0│     │Counter=1│     │Counter=3│
└─────────┘     └─────────┘     └─────────┘
```

### 다이아몬드 의존성

```
                    ┌─────────────────────────────────┐
                    │                                 │
                    ▼                                 │
┌──────────┐   ┌─────────┐   ┌─────────────────┐   ┌─────────┐
│  Config  │──▶│ create  │──▶│    add_five     │──▶│transform│
│          │   │Counter=0│   │   Counter=5     │   │Counter=10
└──────────┘   └─────────┘   └────────┬────────┘   └─────────┘
                                      │                 ▲
                                      ▼                 │
                              ┌───────────────┐         │
                              │create_transf. │─────────┘
                              │Transformer(5) │
                              └───────────────┘
```

### 병렬 독립 Chain

```
┌──────────┐   ┌─────────────┐   ┌──────────────┐
│  Config  │──▶│create_count │──▶│modify_counter│  Counter=15
│          │   │  Counter=10 │   │  Counter=15  │
└──────────┘   └─────────────┘   └──────────────┘
      │
      │        ┌─────────────┐   ┌──────────────┐
      └───────▶│create_mult  │──▶│modify_mult   │  Multiplier=6
               │ Multiplier=2│   │ Multiplier=6 │
               └─────────────┘   └──────────────┘
```

## @Order 데코레이터

### 기본 사용법

```python
from bloom.core import Order

@Factory
@Order(1)
def step_one(self, c: Counter) -> Counter:
    return c

@Factory
@Order(2)
def step_two(self, c: Counter) -> Counter:
    return c
```

### 순서 규칙

1. **@Order가 있는 Factory끼리**: Order 값으로 정렬 (낮을수록 먼저)
2. **@Order가 없는 Factory끼리**: 의존성 기반 (Creator → Modifier)
3. **혼합**: Order 없는 것들 → Order 있는 것들 순서

```python
@Factory
def create(self) -> Counter:          # 1st: Creator, Order 없음
    return Counter(0)

@Factory
@Order(5)
def step_five(self, c: Counter):      # 3rd: Order=5
    pass

@Factory
@Order(1)
def step_one(self, c: Counter):       # 2nd: Order=1
    pass
```

### 음수 및 0 허용

```python
@Factory
@Order(-100)
def first(self) -> Counter:
    return Counter(100)

@Factory
@Order(0)
def second(self, c: Counter) -> Counter:
    return c
```

## Ambiguous Provider 에러

### 발생 조건

동일 타입을 생성하는 **Creator가 2개 이상**이고, 그 타입을 의존하는 **Modifier가 있는 경우**:

```python
@Component
class BadConfig:
    @Factory
    def create1(self) -> Value:      # Creator 1
        return Value()

    @Factory
    def create2(self) -> Value:      # Creator 2 (충돌!)
        return Value()

    @Factory
    def modify(self, v: Value):      # Modifier - 어떤 Creator를 받아야 하나?
        pass

# AmbiguousProviderError 발생!
```

### 해결 방법

1. **Creator를 하나로 통합**
2. **Modifier만 사용**: 하나의 Creator + 여러 Modifier

```python
@Component
class GoodConfig:
    @Factory
    def create(self) -> Value:       # 유일한 Creator
        return Value()

    @Factory
    @Order(1)
    def modify1(self, v: Value):     # Modifier 1
        pass

    @Factory
    @Order(2)
    def modify2(self, v: Value):     # Modifier 2
        pass
```

### 예외: Modifier 없이 여러 Creator

Modifier가 없으면 여러 Creator도 허용됩니다 (각각 독립적인 인스턴스):

```python
@Component
class MultipleCreators:
    @Factory
    def create_a(self) -> Service:
        s = Service()
        s.name = "A"
        return s

    @Factory
    def create_b(self) -> Service:
        s = Service()
        s.name = "B"
        return s

# OK! get_instances(Service)로 모두 조회 가능
```

## 실제 활용 예시

### MiddlewareChain 구성

```python
@Component
class MiddlewareConfig:
    @Factory
    def create_chain(self) -> MiddlewareChain:
        """빈 체인 생성"""
        return MiddlewareChain()

    @Factory
    @Order(1)
    def add_cors(self, chain: MiddlewareChain, cors: CorsMiddleware) -> MiddlewareChain:
        """CORS 미들웨어 추가"""
        chain.add(cors)
        return chain

    @Factory
    @Order(2)
    def add_auth(self, chain: MiddlewareChain, auth: AuthMiddleware) -> MiddlewareChain:
        """인증 미들웨어 추가"""
        chain.add(auth)
        return chain

    @Factory
    @Order(3)
    def add_error(self, chain: MiddlewareChain, error: ErrorMiddleware) -> MiddlewareChain:
        """에러 핸들러 미들웨어 추가"""
        chain.add(error)
        return chain
```

### Builder 패턴

```python
@Component
class DatabaseConfig:
    config: AppConfig  # 설정 주입

    @Factory
    def create_pool(self) -> ConnectionPool:
        """기본 풀 생성"""
        return ConnectionPool()

    @Factory
    @Order(1)
    def configure_pool(self, pool: ConnectionPool) -> ConnectionPool:
        """설정 적용"""
        pool.host = self.config.db_host
        pool.port = self.config.db_port
        return pool

    @Factory
    @Order(2)
    def add_monitoring(self, pool: ConnectionPool) -> ConnectionPool:
        """모니터링 래퍼 추가"""
        return MonitoredPool(pool)
```

## 토폴로지 정렬 결과

최종적으로 모든 컨테이너는 다음 순서로 초기화됩니다:

1. 의존성이 없는 컨테이너 (Level 0)
2. Level 0에만 의존하는 컨테이너 (Level 1)
3. ...계속

Factory Chain은 이 순서 내에서 **연속적으로** 배치됩니다:

```
Level 0: Config
Level 1: create_counter
Level 2: add_five
Level 3: create_transformer
Level 4: transform
```

## 주의사항

1. **PROTOTYPE Scope와 Factory Chain**: `@Scope(PROTOTYPE)` 컴포넌트는 즉시 초기화되지 않으므로, Factory Chain과 함께 사용 시 주의

2. **순환 의존성**: 서로 다른 타입 간의 순환 의존성은 여전히 에러 발생

   ```
   A → B → A  (에러!)
   ```

   > 참고: Bloom에서는 모든 필드 주입이 기본 Lazy이므로, 대부분의 순환 의존성은 자동으로 해결됩니다.

3. **병렬 초기화**: Factory Chain이 있는 경우, 순차 초기화(`parallel=False`) 권장

## 관련 파일

- `bloom/core/utils.py`: `topological_sort_with_order()` 함수
- `bloom/core/decorators.py`: `@Order` 데코레이터
- `bloom/core/container/factory.py`: `FactoryContainer`
- `bloom/application.py`: `_initialize_containers()` 메서드
