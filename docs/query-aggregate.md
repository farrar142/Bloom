# Query Aggregate Functions

Bloom ORM은 Django 스타일의 `annotate()`, `group_by()`, `having()` 메서드를 통해 집계 쿼리를 지원합니다.

## 집계 함수 (Aggregate Functions)

### 기본 사용법

```python
from bloom.db import Query, Count, Sum, Avg, Min, Max

# COUNT
count = Count(Order.id)           # COUNT(id)
count = Count("*")                # COUNT(*)

# SUM
total = Sum(Order.amount)         # SUM(amount)

# AVG
average = Avg(Product.price)      # AVG(price)

# MIN / MAX
min_val = Min(Product.price)      # MIN(price)
max_val = Max(Product.price)      # MAX(price)

# 별칭 지정
count = Count(Order.id).as_("order_count")  # COUNT(id) AS order_count
```

### 지원하는 집계 함수

| 함수    | 설명       | 예시                            |
| ------- | ---------- | ------------------------------- |
| `Count` | 행 수 계산 | `Count(Order.id)`, `Count("*")` |
| `Sum`   | 합계       | `Sum(Order.amount)`             |
| `Avg`   | 평균       | `Avg(Product.price)`            |
| `Min`   | 최소값     | `Min(Product.price)`            |
| `Max`   | 최대값     | `Max(Product.price)`            |

## annotate()

`annotate()` 메서드로 집계 함수를 쿼리에 추가합니다.

```python
from bloom.db import Query, Count, Sum, Avg

# 사용자별 주문 수 집계
results = (
    Query(Order)
    .annotate(order_count=Count(Order.id))
    .group_by(Order.user_id)
    .with_session(session)
    .aggregate_all()
)
# 결과: [{"user_id": 1, "order_count": 10}, {"user_id": 2, "order_count": 5}, ...]

# 복수 집계 함수
results = (
    Query(Order)
    .annotate(
        order_count=Count(Order.id),
        total_amount=Sum(Order.amount),
        avg_amount=Avg(Order.amount),
    )
    .group_by(Order.user_id)
    .with_session(session)
    .aggregate_all()
)
# 결과: [{"user_id": 1, "order_count": 10, "total_amount": 5000, "avg_amount": 500}, ...]
```

## group_by()

`group_by()` 메서드로 그룹화할 컬럼을 지정합니다.

```python
# 단일 컬럼 그룹화
results = (
    Query(Order)
    .annotate(cnt=Count("*"))
    .group_by(Order.status)
    .with_session(session)
    .aggregate_all()
)
# 결과: [{"status": "completed", "cnt": 100}, {"status": "pending", "cnt": 20}]

# 복수 컬럼 그룹화
results = (
    Query(Order)
    .annotate(cnt=Count("*"))
    .group_by(Order.user_id, Order.status)
    .with_session(session)
    .aggregate_all()
)

# 문자열로 컬럼 지정
results = (
    Query(Product)
    .annotate(total_stock=Sum("stock"))
    .group_by("category")
    .with_session(session)
    .aggregate_all()
)
```

## having()

`having()` 메서드로 집계 결과에 대한 필터링 조건을 추가합니다.

```python
from bloom.db import Query, Count, Sum

# 주문 수가 5개 초과인 사용자만 조회
results = (
    Query(Order)
    .annotate(order_count=Count(Order.id))
    .group_by(Order.user_id)
    .having(Count(Order.id) > 5)
    .with_session(session)
    .aggregate_all()
)

# 총 주문 금액이 1000 이상인 사용자
results = (
    Query(Order)
    .annotate(total=Sum(Order.amount))
    .group_by(Order.user_id)
    .having(Sum(Order.amount) >= 1000)
    .with_session(session)
    .aggregate_all()
)

# 복합 HAVING 조건 (AND)
results = (
    Query(Order)
    .annotate(
        order_count=Count(Order.id),
        total=Sum(Order.amount)
    )
    .group_by(Order.user_id)
    .having(
        (Count(Order.id) > 5) & (Sum(Order.amount) > 1000)
    )
    .with_session(session)
    .aggregate_all()
)
```

### HAVING 연산자

| 연산자 | 설명 | 예시                              |
| ------ | ---- | --------------------------------- | ----------------------------------- |
| `>`    | 초과 | `Count(Order.id) > 5`             |
| `>=`   | 이상 | `Sum(Order.amount) >= 1000`       |
| `<`    | 미만 | `Avg(Product.price) < 100`        |
| `<=`   | 이하 | `Max(Product.price) <= 500`       |
| `==`   | 같음 | `Count("*") == 10`                |
| `!=`   | 다름 | `Min(Product.stock) != 0`         |
| `&`    | AND  | `(Count(a) > 5) & (Sum(b) > 100)` |
| `      | `    | OR                                | `(Count(a) > 10) \| (Sum(b) > 500)` |

## WHERE와 HAVING 조합

`filter()`와 `having()`을 함께 사용하여 행 레벨 필터링과 그룹 레벨 필터링을 조합할 수 있습니다.

```python
# 완료된 주문 중, 총 금액이 500 이상인 사용자
results = (
    Query(Order)
    .filter(Order.status == "completed")  # WHERE: 행 필터링
    .annotate(total=Sum(Order.amount))
    .group_by(Order.user_id)
    .having(Sum(Order.amount) >= 500)     # HAVING: 그룹 필터링
    .with_session(session)
    .aggregate_all()
)
```

## 결과 반환 메서드

집계 쿼리는 엔티티가 아닌 딕셔너리로 결과를 반환합니다.

### 동기 메서드

```python
# 모든 결과 반환
results: list[dict[str, Any]] = query.aggregate_all()

# 첫 번째 결과만 반환
result: dict[str, Any] | None = query.aggregate_first()
```

### 비동기 메서드

```python
# 비동기 모든 결과
results = await query.async_aggregate_all()

# 비동기 첫 번째 결과
result = await query.async_aggregate_first()
```

## 정렬과 제한

```python
# ORDER BY
results = (
    Query(Order)
    .annotate(total=Sum(Order.amount))
    .group_by(Order.user_id)
    .order_by(Order.user_id.asc())
    .with_session(session)
    .aggregate_all()
)

# LIMIT
results = (
    Query(Order)
    .annotate(total=Sum(Order.amount))
    .group_by(Order.user_id)
    .limit(10)
    .with_session(session)
    .aggregate_all()
)
```

## 전체 예제

```python
from dataclasses import dataclass
from bloom.db import (
    Entity, Column, PrimaryKey, Query,
    Count, Sum, Avg, Min, Max
)

@Entity
@dataclass
class Order:
    id: int = PrimaryKey()
    user_id: int = Column()
    amount: int = Column()
    status: str = Column(default="pending")


# 사용자별 주문 통계
def get_user_order_stats(session):
    return (
        Query(Order)
        .filter(Order.status == "completed")
        .annotate(
            order_count=Count(Order.id),
            total_amount=Sum(Order.amount),
            avg_amount=Avg(Order.amount),
            min_order=Min(Order.amount),
            max_order=Max(Order.amount),
        )
        .group_by(Order.user_id)
        .having(Count(Order.id) >= 3)
        .order_by(Order.user_id.asc())
        .with_session(session)
        .aggregate_all()
    )

# 결과 예시:
# [
#     {
#         "user_id": 1,
#         "order_count": 10,
#         "total_amount": 5000,
#         "avg_amount": 500,
#         "min_order": 100,
#         "max_order": 1000
#     },
#     ...
# ]
```

## Django 비교

| Django                                   | Bloom                                               |
| ---------------------------------------- | --------------------------------------------------- |
| `User.objects.annotate(cnt=Count('id'))` | `Query(User).annotate(cnt=Count(User.id))`          |
| `.values('status')`                      | `.group_by(User.status)`                            |
| `.annotate(...).filter(cnt__gt=5)`       | `.having(Count(User.id) > 5)`                       |
| `.aggregate(Sum('amount'))`              | `.annotate(total=Sum(User.amount)).aggregate_all()` |
