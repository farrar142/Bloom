"""Query expressions - Condition, ConditionGroup, OrderBy, FieldExpression, Aggregates"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .columns import Column


# =============================================================================
# Aggregate Functions
# =============================================================================


@dataclass(eq=False)
class AggregateFunction:
    """집계 함수 기본 클래스

    Examples:
        Count(User.id)            →  COUNT(id)
        Sum(Order.amount)         →  SUM(amount)
        Avg(Product.price)        →  AVG(price)
        Count(User.id).as_("cnt") →  COUNT(id) AS cnt
    """

    field: str | FieldExpression[Any]
    alias: str | None = None
    _func_name: str = field(default="", init=False)

    def __post_init__(self) -> None:
        # FieldExpression에서 field name 추출
        if hasattr(self.field, "name"):
            self.field = self.field.name  # type: ignore[assignment]

    def as_(self, alias: str) -> AggregateFunction:
        """별칭 지정 (SQL AS)"""
        self.alias = alias
        return self

    def to_sql(self) -> str:
        """SQL 표현식 생성"""
        sql = f"{self._func_name}({self.field})"
        if self.alias:
            sql = f"{sql} AS {self.alias}"
        return sql

    @property
    def output_name(self) -> str:
        """결과 컬럼 이름 (alias 또는 자동 생성)"""
        if self.alias:
            return self.alias
        return f"{self._func_name.lower()}_{self.field}"

    # -------------------------------------------------------------------------
    # 비교 연산자 (HAVING 절용)
    # -------------------------------------------------------------------------

    def __eq__(self, other: Any) -> HavingCondition:  # type: ignore[override]
        return HavingCondition(self, "=", other)

    def __ne__(self, other: Any) -> HavingCondition:  # type: ignore[override]
        return HavingCondition(self, "!=", other)

    def __gt__(self, other: Any) -> HavingCondition:
        return HavingCondition(self, ">", other)

    def __ge__(self, other: Any) -> HavingCondition:
        return HavingCondition(self, ">=", other)

    def __lt__(self, other: Any) -> HavingCondition:
        return HavingCondition(self, "<", other)

    def __le__(self, other: Any) -> HavingCondition:
        return HavingCondition(self, "<=", other)


@dataclass(eq=False)
class Count(AggregateFunction):
    """COUNT 집계 함수

    Examples:
        Count(User.id)           →  COUNT(id)
        Count("*")               →  COUNT(*)
        Count(User.id).as_("n")  →  COUNT(id) AS n
    """

    def __post_init__(self) -> None:
        self._func_name = "COUNT"
        super().__post_init__()


@dataclass(eq=False)
class Sum(AggregateFunction):
    """SUM 집계 함수

    Examples:
        Sum(Order.amount)              →  SUM(amount)
        Sum(Order.amount).as_("total") →  SUM(amount) AS total
    """

    def __post_init__(self) -> None:
        self._func_name = "SUM"
        super().__post_init__()


@dataclass(eq=False)
class Avg(AggregateFunction):
    """AVG 집계 함수

    Examples:
        Avg(Product.price)               →  AVG(price)
        Avg(Product.price).as_("avg_p")  →  AVG(price) AS avg_p
    """

    def __post_init__(self) -> None:
        self._func_name = "AVG"
        super().__post_init__()


@dataclass(eq=False)
class Min(AggregateFunction):
    """MIN 집계 함수

    Examples:
        Min(Product.price)              →  MIN(price)
        Min(Product.price).as_("min_p") →  MIN(price) AS min_p
    """

    def __post_init__(self) -> None:
        self._func_name = "MIN"
        super().__post_init__()


@dataclass(eq=False)
class Max(AggregateFunction):
    """MAX 집계 함수

    Examples:
        Max(Product.price)              →  MAX(price)
        Max(Product.price).as_("max_p") →  MAX(price) AS max_p
    """

    def __post_init__(self) -> None:
        self._func_name = "MAX"
        super().__post_init__()


@dataclass
class HavingCondition:
    """HAVING 절 조건 - 집계 함수 결과 필터링

    Examples:
        Count(User.id) > 5  →  HavingCondition(Count(User.id), ">", 5)
    """

    aggregate: AggregateFunction
    operator: str
    value: Any

    def __and__(
        self, other: HavingCondition | HavingConditionGroup
    ) -> HavingConditionGroup:
        return HavingConditionGroup("AND", [self, other])

    def __or__(
        self, other: HavingCondition | HavingConditionGroup
    ) -> HavingConditionGroup:
        return HavingConditionGroup("OR", [self, other])

    def to_sql(self, param_prefix: str = "h") -> tuple[str, dict[str, Any]]:
        """SQL HAVING 조건절과 파라미터 생성"""
        param_name = f"{param_prefix}_{self.aggregate.output_name}"
        agg_sql = self.aggregate.to_sql().split(" AS ")[0]  # alias 제거
        return f"{agg_sql} {self.operator} :{param_name}", {param_name: self.value}


@dataclass
class HavingConditionGroup:
    """HAVING 조건 그룹 (AND/OR)"""

    operator: str  # "AND" or "OR"
    conditions: list[HavingCondition | HavingConditionGroup] = field(
        default_factory=list
    )

    def __and__(
        self, other: HavingCondition | HavingConditionGroup
    ) -> HavingConditionGroup:
        if self.operator == "AND":
            return HavingConditionGroup("AND", [*self.conditions, other])
        return HavingConditionGroup("AND", [self, other])

    def __or__(
        self, other: HavingCondition | HavingConditionGroup
    ) -> HavingConditionGroup:
        if self.operator == "OR":
            return HavingConditionGroup("OR", [*self.conditions, other])
        return HavingConditionGroup("OR", [self, other])

    def to_sql(
        self, param_prefix: str = "h", depth: int = 0
    ) -> tuple[str, dict[str, Any]]:
        """SQL HAVING 조건절과 파라미터 생성"""
        if not self.conditions:
            return "1=1", {}

        parts: list[str] = []
        params: dict[str, Any] = {}

        for i, cond in enumerate(self.conditions):
            sub_prefix = f"{param_prefix}_{depth}_{i}"
            if isinstance(cond, HavingCondition):
                sql, sub_params = cond.to_sql(sub_prefix)
            else:
                sql, sub_params = cond.to_sql(sub_prefix, depth + 1)
            parts.append(sql)
            params.update(sub_params)

        joined = f" {self.operator} ".join(parts)
        if len(self.conditions) > 1:
            joined = f"({joined})"
        return joined, params


# =============================================================================
# Query Conditions
# =============================================================================


@dataclass
class Condition:
    """쿼리 조건 - SQL WHERE 절 표현

    Examples:
        User.name == "alice"  →  Condition("name", "=", "alice")
        User.age > 18         →  Condition("age", ">", 18)
    """

    field: str
    operator: str
    value: Any

    def __and__(self, other: Condition | ConditionGroup) -> ConditionGroup:
        return ConditionGroup("AND", [self, other])

    def __or__(self, other: Condition | ConditionGroup) -> ConditionGroup:
        return ConditionGroup("OR", [self, other])

    def __invert__(self) -> Condition:
        """NOT 연산"""
        return Condition(self.field, f"NOT {self.operator}", self.value)

    def to_sql(self, param_prefix: str = "p") -> tuple[str, dict[str, Any]]:
        """SQL 조건절과 파라미터 생성

        Returns:
            (sql_string, params_dict)
        """
        param_name = f"{param_prefix}_{self.field}"

        if self.operator in ("IS", "IS NOT"):
            return f"{self.field} {self.operator} NULL", {}

        if self.operator == "IN":
            if not self.value:
                return "1=0", {}  # 빈 리스트는 항상 false
            placeholders = ", ".join(
                f":{param_name}_{i}" for i in range(len(self.value))
            )
            params = {f"{param_name}_{i}": v for i, v in enumerate(self.value)}
            return f"{self.field} IN ({placeholders})", params

        if self.operator == "NOT IN":
            if not self.value:
                return "1=1", {}  # 빈 리스트는 항상 true
            placeholders = ", ".join(
                f":{param_name}_{i}" for i in range(len(self.value))
            )
            params = {f"{param_name}_{i}": v for i, v in enumerate(self.value)}
            return f"{self.field} NOT IN ({placeholders})", params

        if self.operator == "BETWEEN":
            low, high = self.value
            return (
                f"{self.field} BETWEEN :{param_name}_low AND :{param_name}_high",
                {f"{param_name}_low": low, f"{param_name}_high": high},
            )

        return f"{self.field} {self.operator} :{param_name}", {param_name: self.value}


@dataclass
class ConditionGroup:
    """조건 그룹 (AND/OR)

    Examples:
        (User.name == "alice") & (User.age > 18)
        (User.status == "active") | (User.role == "admin")
    """

    operator: str  # "AND" or "OR"
    conditions: list[Condition | ConditionGroup] = field(default_factory=list)

    def __and__(self, other: Condition | ConditionGroup) -> ConditionGroup:
        if self.operator == "AND":
            return ConditionGroup("AND", [*self.conditions, other])
        return ConditionGroup("AND", [self, other])

    def __or__(self, other: Condition | ConditionGroup) -> ConditionGroup:
        if self.operator == "OR":
            return ConditionGroup("OR", [*self.conditions, other])
        return ConditionGroup("OR", [self, other])

    def __invert__(self) -> ConditionGroup:
        """NOT 연산 - De Morgan's law 적용"""
        inverted_op = "OR" if self.operator == "AND" else "AND"
        inverted_conditions = [~c for c in self.conditions]
        return ConditionGroup(inverted_op, inverted_conditions)

    def to_sql(
        self, param_prefix: str = "p", depth: int = 0
    ) -> tuple[str, dict[str, Any]]:
        """SQL 조건절과 파라미터 생성"""
        if not self.conditions:
            return "1=1", {}

        parts: list[str] = []
        params: dict[str, Any] = {}

        for i, cond in enumerate(self.conditions):
            sub_prefix = f"{param_prefix}_{depth}_{i}"
            if isinstance(cond, Condition):
                sql, sub_params = cond.to_sql(sub_prefix)
            else:
                sql, sub_params = cond.to_sql(sub_prefix, depth + 1)
            parts.append(sql)
            params.update(sub_params)

        joined = f" {self.operator} ".join(parts)
        if len(self.conditions) > 1:
            joined = f"({joined})"
        return joined, params


@dataclass
class OrderBy:
    """정렬 표현식

    Examples:
        User.name.asc()   →  OrderBy("name", "ASC")
        User.age.desc()   →  OrderBy("age", "DESC")
    """

    field: str
    direction: str = "ASC"  # "ASC" or "DESC"

    def to_sql(self) -> str:
        return f"{self.field} {self.direction}"


# =============================================================================
# Field Expression (클래스 레벨 접근 시 반환)
# =============================================================================


class FieldExpression[T]:
    """필드 표현식 - QueryDSL 스타일 쿼리 빌더용

    클래스 레벨에서 컬럼 접근 시 반환됩니다.

    Examples:
        User.name         →  FieldExpression[str]
        User.name == "x"  →  Condition("name", "=", "x")
        User.age > 18     →  Condition("age", ">", 18)
        User.name.asc()   →  OrderBy("name", "ASC")
    """

    __slots__ = ("name", "column")

    def __init__(self, name: str, column: Column[T]):
        self.name = name
        self.column = column

    # -------------------------------------------------------------------------
    # 비교 연산자
    # -------------------------------------------------------------------------

    def __eq__(self, other: T | None) -> Condition:  # type: ignore[override]
        if other is None:
            return Condition(self.name, "IS", None)
        return Condition(self.name, "=", other)

    def __ne__(self, other: T | None) -> Condition:  # type: ignore[override]
        if other is None:
            return Condition(self.name, "IS NOT", None)
        return Condition(self.name, "!=", other)

    def __gt__(self, other: T) -> Condition:
        return Condition(self.name, ">", other)

    def __ge__(self, other: T) -> Condition:
        return Condition(self.name, ">=", other)

    def __lt__(self, other: T) -> Condition:
        return Condition(self.name, "<", other)

    def __le__(self, other: T) -> Condition:
        return Condition(self.name, "<=", other)

    # -------------------------------------------------------------------------
    # 문자열 연산
    # -------------------------------------------------------------------------

    def like(self, pattern: str) -> Condition:
        """LIKE 패턴 매칭"""
        return Condition(self.name, "LIKE", pattern)

    def ilike(self, pattern: str) -> Condition:
        """대소문자 무시 LIKE (PostgreSQL)"""
        return Condition(self.name, "ILIKE", pattern)

    def startswith(self, prefix: str) -> Condition:
        """문자열 시작 매칭"""
        return Condition(self.name, "LIKE", f"{prefix}%")

    def endswith(self, suffix: str) -> Condition:
        """문자열 끝 매칭"""
        return Condition(self.name, "LIKE", f"%{suffix}")

    def contains(self, substring: str) -> Condition:
        """문자열 포함 매칭"""
        return Condition(self.name, "LIKE", f"%{substring}%")

    # -------------------------------------------------------------------------
    # 컬렉션 연산
    # -------------------------------------------------------------------------

    def in_(self, values: list[T]) -> Condition:
        """IN 연산"""
        return Condition(self.name, "IN", values)

    def not_in(self, values: list[T]) -> Condition:
        """NOT IN 연산"""
        return Condition(self.name, "NOT IN", values)

    def between(self, low: T, high: T) -> Condition:
        """BETWEEN 연산"""
        return Condition(self.name, "BETWEEN", (low, high))

    # -------------------------------------------------------------------------
    # NULL 체크
    # -------------------------------------------------------------------------

    def is_null(self) -> Condition:
        """IS NULL 체크"""
        return Condition(self.name, "IS", None)

    def is_not_null(self) -> Condition:
        """IS NOT NULL 체크"""
        return Condition(self.name, "IS NOT", None)

    # -------------------------------------------------------------------------
    # 정렬
    # -------------------------------------------------------------------------

    def asc(self) -> OrderBy:
        """오름차순 정렬"""
        return OrderBy(self.name, "ASC")

    def desc(self) -> OrderBy:
        """내림차순 정렬"""
        return OrderBy(self.name, "DESC")

    def __repr__(self) -> str:
        return f"FieldExpression({self.name!r})"

    def __hash__(self) -> int:
        return hash(self.name)
