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

    def in_(self, values: list[T] | Subquery) -> Condition | "SubqueryInCondition":
        """IN 연산 (리스트 또는 서브쿼리)

        Examples:
            User.id.in_([1, 2, 3])
            User.id.in_(Query(Order).select(Order.user_id).subquery())
        """
        if isinstance(values, Subquery):
            return SubqueryInCondition(self.name, values, negate=False)
        return Condition(self.name, "IN", values)

    def not_in(self, values: list[T] | Subquery) -> Condition | "SubqueryInCondition":
        """NOT IN 연산 (리스트 또는 서브쿼리)

        Examples:
            User.id.not_in([1, 2, 3])
            User.id.not_in(Query(Order).select(Order.user_id).subquery())
        """
        if isinstance(values, Subquery):
            return SubqueryInCondition(self.name, values, negate=True)
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


# =============================================================================
# Subquery
# =============================================================================


class Subquery:
    """서브쿼리 표현식

    Query 객체를 서브쿼리로 사용할 수 있게 해줍니다.

    Examples:
        # IN 서브쿼리
        active_user_ids = Query(User).filter(User.status == "active").select(User.id)
        orders = Query(Order).filter(Order.user_id.in_(Subquery(active_user_ids)))

        # EXISTS 서브쿼리
        has_orders = Subquery(Query(Order).filter(Order.user_id == User.id)).exists()
        users = Query(User).filter(has_orders)

        # Scalar 서브쿼리 (단일 값)
        avg_amount = Subquery(Query(Order).annotate(avg=Avg(Order.amount))).scalar("avg")
        orders = Query(Order).filter(Order.amount > avg_amount)
    """

    def __init__(self, query: Any, alias: str | None = None):
        """
        Args:
            query: Query 객체
            alias: 서브쿼리 별칭
        """
        self._query = query
        self._alias = alias
        self._param_offset: int = 0

    def as_(self, alias: str) -> "Subquery":
        """별칭 지정"""
        self._alias = alias
        return self

    def to_sql(self, param_prefix: str = "sq") -> tuple[str, dict[str, Any]]:
        """SQL 생성

        Returns:
            (sql, params)
        """
        sql, params = self._query.build()

        # 파라미터 이름 재매핑 (충돌 방지)
        new_params: dict[str, Any] = {}
        for old_key, value in params.items():
            new_key = f"{param_prefix}_{old_key}"
            sql = sql.replace(f":{old_key}", f":{new_key}")
            new_params[new_key] = value

        subquery_sql = f"({sql})"
        if self._alias:
            subquery_sql = f"{subquery_sql} AS {self._alias}"

        return subquery_sql, new_params

    def exists(self) -> "SubqueryCondition":
        """EXISTS 조건 생성"""
        return SubqueryCondition(self, "EXISTS")

    def not_exists(self) -> "SubqueryCondition":
        """NOT EXISTS 조건 생성"""
        return SubqueryCondition(self, "NOT EXISTS")

    def scalar(self, column: str | None = None) -> "ScalarSubquery":
        """스칼라 서브쿼리 (단일 값 반환)

        Args:
            column: 반환할 컬럼명 (None이면 첫 번째 컬럼)
        """
        return ScalarSubquery(self, column)


@dataclass
class SubqueryInCondition:
    """서브쿼리 IN 조건

    Examples:
        User.id.in_(subquery)      →  "id" IN (SELECT ...)
        User.id.not_in(subquery)   →  "id" NOT IN (SELECT ...)
    """

    field: str
    subquery: Subquery
    negate: bool = False

    def __and__(
        self, other: Condition | ConditionGroup | "SubqueryInCondition"
    ) -> ConditionGroup:
        return ConditionGroup("AND", [self, other])  # type: ignore

    def __or__(
        self, other: Condition | ConditionGroup | "SubqueryInCondition"
    ) -> ConditionGroup:
        return ConditionGroup("OR", [self, other])  # type: ignore

    def to_sql(self, param_prefix: str = "sq") -> tuple[str, dict[str, Any]]:
        """SQL 생성"""
        subquery_sql, params = self.subquery.to_sql(param_prefix)
        op = "NOT IN" if self.negate else "IN"
        return f'"{self.field}" {op} {subquery_sql}', params


@dataclass
class SubqueryCondition:
    """서브쿼리 조건 (EXISTS, NOT EXISTS 등)

    Examples:
        Subquery(query).exists()       →  EXISTS (SELECT ...)
        Subquery(query).not_exists()   →  NOT EXISTS (SELECT ...)
    """

    subquery: Subquery
    operator: str  # "EXISTS", "NOT EXISTS"

    def __and__(
        self, other: Condition | ConditionGroup | "SubqueryCondition"
    ) -> ConditionGroup:
        return ConditionGroup("AND", [self, other])  # type: ignore

    def __or__(
        self, other: Condition | ConditionGroup | "SubqueryCondition"
    ) -> ConditionGroup:
        return ConditionGroup("OR", [self, other])  # type: ignore

    def to_sql(self, param_prefix: str = "sq") -> tuple[str, dict[str, Any]]:
        """SQL 생성"""
        subquery_sql, params = self.subquery.to_sql(param_prefix)
        return f"{self.operator} {subquery_sql}", params


@dataclass(eq=False)
class ScalarSubquery:
    """스칼라 서브쿼리 - 단일 값을 반환하는 서브쿼리

    비교 연산자를 지원하여 WHERE 절에서 사용 가능합니다.

    Examples:
        avg_amount = Subquery(Query(Order).annotate(avg=Avg(Order.amount))).scalar()
        Order.amount > avg_amount  →  "amount" > (SELECT AVG(amount) FROM orders)
    """

    subquery: Subquery
    column: str | None = None

    def __eq__(self, other: Any) -> Condition:  # type: ignore[override]
        return Condition(f"({self._get_sql()})", "=", other)

    def __ne__(self, other: Any) -> Condition:  # type: ignore[override]
        return Condition(f"({self._get_sql()})", "!=", other)

    def __gt__(self, other: Any) -> Condition:
        return Condition(f"({self._get_sql()})", ">", other)

    def __ge__(self, other: Any) -> Condition:
        return Condition(f"({self._get_sql()})", ">=", other)

    def __lt__(self, other: Any) -> Condition:
        return Condition(f"({self._get_sql()})", "<", other)

    def __le__(self, other: Any) -> Condition:
        return Condition(f"({self._get_sql()})", "<=", other)

    def __radd__(self, other: Any) -> "ScalarSubqueryExpr":
        return ScalarSubqueryExpr(self, other, "+", reverse=True)

    def __rsub__(self, other: Any) -> "ScalarSubqueryExpr":
        return ScalarSubqueryExpr(self, other, "-", reverse=True)

    def _get_sql(self) -> str:
        sql, _ = self.subquery.to_sql()
        return sql

    def to_sql(self, param_prefix: str = "sq") -> tuple[str, dict[str, Any]]:
        """SQL 생성"""
        return self.subquery.to_sql(param_prefix)


@dataclass
class ScalarSubqueryExpr:
    """스칼라 서브쿼리 표현식 (산술 연산 지원)"""

    scalar: ScalarSubquery
    value: Any
    operator: str
    reverse: bool = False

    def to_sql(self, param_prefix: str = "sq") -> tuple[str, dict[str, Any]]:
        sql, params = self.scalar.to_sql(param_prefix)
        param_name = f"{param_prefix}_val"
        params[param_name] = self.value
        if self.reverse:
            return f":{param_name} {self.operator} {sql}", params
        return f"{sql} {self.operator} :{param_name}", params


# =============================================================================
# JOIN
# =============================================================================


class JoinType:
    """JOIN 타입"""

    INNER = "INNER JOIN"
    LEFT = "LEFT JOIN"
    RIGHT = "RIGHT JOIN"
    FULL = "FULL OUTER JOIN"
    CROSS = "CROSS JOIN"


@dataclass
class JoinClause:
    """JOIN 절 표현

    Examples:
        JoinClause(Order, User, Order.user_id == User.id, JoinType.INNER)
        → INNER JOIN "users" ON "orders"."user_id" = "users"."id"
    """

    target: type[Any]  # 조인할 엔티티 클래스
    condition: Condition | ConditionGroup | None  # ON 조건
    join_type: str = JoinType.INNER  # JOIN 타입
    alias: str | None = None  # 테이블 별칭

    def to_sql(self, param_prefix: str = "j") -> tuple[str, dict[str, Any]]:
        """SQL JOIN 절 생성"""
        from .entity import get_entity_meta

        meta = get_entity_meta(self.target)
        if meta is None:
            raise ValueError(f"{self.target.__name__} is not an Entity")

        table_name = meta.table_name
        if self.alias:
            table_ref = f'"{table_name}" AS {self.alias}'
        else:
            table_ref = f'"{table_name}"'

        if self.join_type == JoinType.CROSS or self.condition is None:
            return f"{self.join_type} {table_ref}", {}

        cond_sql, params = self.condition.to_sql(param_prefix)
        return f"{self.join_type} {table_ref} ON {cond_sql}", params


@dataclass
class JoinCondition:
    """JOIN ON 조건 - 두 테이블의 컬럼 비교

    Examples:
        on(Order.user_id, User.id)  →  "orders"."user_id" = "users"."id"
    """

    left_field: str | FieldExpression[Any]
    right_field: str | FieldExpression[Any]
    operator: str = "="
    left_table: str | None = None
    right_table: str | None = None

    def __post_init__(self) -> None:
        if hasattr(self.left_field, "name"):
            self.left_field = self.left_field.name  # type: ignore
        if hasattr(self.right_field, "name"):
            self.right_field = self.right_field.name  # type: ignore

    def to_sql(self, param_prefix: str = "j") -> tuple[str, dict[str, Any]]:
        """SQL 조건 생성 (파라미터 없이 컬럼 간 비교)"""
        left = (
            f'"{self.left_table}"."{self.left_field}"'
            if self.left_table
            else f'"{self.left_field}"'
        )
        right = (
            f'"{self.right_table}"."{self.right_field}"'
            if self.right_table
            else f'"{self.right_field}"'
        )
        return f"{left} {self.operator} {right}", {}


def on(
    left: str | FieldExpression[Any],
    right: str | FieldExpression[Any],
    operator: str = "=",
    left_table: str | None = None,
    right_table: str | None = None,
) -> JoinCondition:
    """JOIN ON 조건 헬퍼 함수

    Examples:
        on(Order.user_id, User.id)
        on("user_id", "id", left_table="orders", right_table="users")
    """
    return JoinCondition(left, right, operator, left_table, right_table)
