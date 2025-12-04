"""Query expressions - Condition, ConditionGroup, OrderBy, FieldExpression, Aggregates"""

from __future__ import annotations
from typing import Any, TYPE_CHECKING, Union, overload, Self

if TYPE_CHECKING:
    from .columns import Column

# =============================================================================
# Type Aliases (Forward References)
# =============================================================================

# ConditionLike: Condition, ConditionGroup, JoinCondition 모두 포함
# 실제 정의는 클래스 정의 후 하단에서 이루어짐
ConditionLike = Union["Condition", "ConditionGroup", "JoinCondition"]


# =============================================================================
# Aggregate Functions
# =============================================================================


class AggregateFunction:
    """집계 함수 기본 클래스

    Examples:
        Count(User.id)            →  COUNT("users"."id")
        Sum(Order.amount)         →  SUM("orders"."amount")
        Avg(Product.price)        →  AVG("products"."price")
        Count(User.id).as_("cnt") →  COUNT("users"."id") AS cnt
    """

    __slots__ = ("field", "alias", "_table_name")

    _func_name: str = ""

    def __init__(
        self,
        field: str | FieldExpression[Any],
        alias: str | None = None,
    ) -> None:
        self.alias = alias
        self._table_name: str | None = None

        if isinstance(field, str):
            self.field = field
        else:
            self.field = field.name
            if hasattr(field, "table_name"):
                self._table_name = field.table_name  # type: ignore

        # # FieldExpression에서 field name과 table_name 추출
        # if hasattr(field, "name"):
        #     if hasattr(field, "table_name"):
        #         self._table_name = field.table_name  # type: ignore
        #     self.field: str = field.name  # type: ignore[union-attr]
        # else:
        #     self.field = field  # type: ignore[assignment]

    def as_(self, alias: str) -> Self:
        """별칭 지정 (SQL AS)"""
        self.alias = alias
        return self

    def _get_field_ref(self) -> str:
        """테이블 접두사가 있으면 포함한 필드 참조 반환"""
        if self._table_name:
            return f'"{self._table_name}"."{self.field}"'
        return str(self.field)

    def to_sql(self) -> str:
        """SQL 표현식 생성"""
        field_ref = self._get_field_ref()
        sql = f"{self._func_name}({field_ref})"
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


class Count(AggregateFunction):
    """COUNT 집계 함수

    Examples:
        Count(User.id)           →  COUNT(id)
        Count("*")               →  COUNT(*)
        Count(User.id).as_("n")  →  COUNT(id) AS n
    """

    _func_name = "COUNT"


class Sum(AggregateFunction):
    """SUM 집계 함수

    Examples:
        Sum(Order.amount)              →  SUM(amount)
        Sum(Order.amount).as_("total") →  SUM(amount) AS total
    """

    _func_name = "SUM"


class Avg(AggregateFunction):
    """AVG 집계 함수

    Examples:
        Avg(Product.price)               →  AVG(price)
        Avg(Product.price).as_("avg_p")  →  AVG(price) AS avg_p
    """

    _func_name = "AVG"


class Min(AggregateFunction):
    """MIN 집계 함수

    Examples:
        Min(Product.price)              →  MIN(price)
        Min(Product.price).as_("min_p") →  MIN(price) AS min_p
    """

    _func_name = "MIN"


class Max(AggregateFunction):
    """MAX 집계 함수

    Examples:
        Max(Product.price)              →  MAX(price)
        Max(Product.price).as_("max_p") →  MAX(price) AS max_p
    """

    _func_name = "MAX"


class HavingCondition:
    """HAVING 절 조건 - 집계 함수 결과 필터링

    Examples:
        Count(User.id) > 5  →  HavingCondition(Count(User.id), ">", 5)
    """

    __slots__ = ("aggregate", "operator", "value")

    def __init__(
        self,
        aggregate: AggregateFunction,
        operator: str,
        value: Any,
    ) -> None:
        self.aggregate = aggregate
        self.operator = operator
        self.value = value

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


class HavingConditionGroup:
    """HAVING 조건 그룹 (AND/OR)"""

    __slots__ = ("operator", "conditions")

    def __init__(
        self,
        operator: str,
        conditions: list[HavingCondition | HavingConditionGroup] | None = None,
    ) -> None:
        self.operator = operator  # "AND" or "OR"
        self.conditions: list[HavingCondition | HavingConditionGroup] = (
            conditions if conditions is not None else []
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


class Condition:
    """쿼리 조건 - SQL WHERE 절 표현

    Examples:
        User.name == "alice"  →  Condition("name", "=", "alice", table_name="users")
        User.age > 18         →  Condition("age", ">", 18, table_name="users")
    """

    __slots__ = ("field", "operator", "value", "table_name")

    def __init__(
        self,
        field: str,
        operator: str,
        value: Any,
        table_name: str | None = None,
    ) -> None:
        self.field = field
        self.operator = operator
        self.value = value
        self.table_name = table_name  # JOIN 시 테이블 접두사

    def __and__(self, other: ConditionLike) -> ConditionGroup:
        return ConditionGroup("AND", [self, other])

    def __or__(self, other: ConditionLike) -> ConditionGroup:
        return ConditionGroup("OR", [self, other])

    def __invert__(self) -> Condition:
        """NOT 연산"""
        return Condition(
            self.field, f"NOT {self.operator}", self.value, self.table_name
        )

    def _get_field_ref(self) -> str:
        """테이블 접두사가 있으면 포함한 필드 참조 반환"""
        if self.table_name:
            return f'"{self.table_name}"."{self.field}"'
        return self.field  # 기존 동작 유지: 테이블명 없으면 필드명만

    def to_sql(self, param_prefix: str = "p") -> tuple[str, dict[str, Any]]:
        """SQL 조건절과 파라미터 생성

        Returns:
            (sql_string, params_dict)
        """
        param_name = f"{param_prefix}_{self.field}"
        field_ref = self._get_field_ref()

        if self.operator in ("IS", "IS NOT"):
            return f"{field_ref} {self.operator} NULL", {}

        if self.operator == "IN":
            if not self.value:
                return "1=0", {}  # 빈 리스트는 항상 false
            placeholders = ", ".join(
                f":{param_name}_{i}" for i in range(len(self.value))
            )
            params = {f"{param_name}_{i}": v for i, v in enumerate(self.value)}
            return f"{field_ref} IN ({placeholders})", params

        if self.operator == "NOT IN":
            if not self.value:
                return "1=1", {}  # 빈 리스트는 항상 true
            placeholders = ", ".join(
                f":{param_name}_{i}" for i in range(len(self.value))
            )
            params = {f"{param_name}_{i}": v for i, v in enumerate(self.value)}
            return f"{field_ref} NOT IN ({placeholders})", params

        if self.operator == "BETWEEN":
            low, high = self.value
            return (
                f"{field_ref} BETWEEN :{param_name}_low AND :{param_name}_high",
                {f"{param_name}_low": low, f"{param_name}_high": high},
            )

        return f"{field_ref} {self.operator} :{param_name}", {param_name: self.value}


class ConditionGroup:
    """조건 그룹 (AND/OR)

    Examples:
        (User.name == "alice") & (User.age > 18)
        (User.status == "active") | (User.role == "admin")
    """

    __slots__ = ("operator", "conditions")

    def __init__(
        self,
        operator: str,
        conditions: list[ConditionLike] | None = None,
    ) -> None:
        self.operator = operator  # "AND" or "OR"
        self.conditions: list[ConditionLike] = (
            conditions if conditions is not None else []
        )

    def __and__(self, other: ConditionLike) -> ConditionGroup:
        if self.operator == "AND":
            return ConditionGroup("AND", [*self.conditions, other])
        return ConditionGroup("AND", [self, other])

    def __or__(self, other: ConditionLike) -> ConditionGroup:
        if self.operator == "OR":
            return ConditionGroup("OR", [*self.conditions, other])
        return ConditionGroup("OR", [self, other])

    def __invert__(self) -> ConditionGroup:
        """NOT 연산 - De Morgan's law 적용"""
        inverted_op = "OR" if self.operator == "AND" else "AND"
        inverted_conditions: list[ConditionLike] = [
            ~c for c in self.conditions  # type: ignore[operator]
        ]
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


class OrderBy:
    """정렬 표현식

    Examples:
        User.name.asc()   →  OrderBy("name", "ASC")
        User.age.desc()   →  OrderBy("age", "DESC")
    """

    __slots__ = ("field", "direction")

    def __init__(self, field: str, direction: str = "ASC") -> None:
        self.field = field
        self.direction = direction  # "ASC" or "DESC"

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

    __slots__ = ("name", "column", "_owner_class")

    def __init__(self, name: str, column: Column[T], owner_class: type | None = None):
        self.name = name
        self.column = column
        self._owner_class = owner_class

    @property
    def table_name(self) -> str | None:
        """테이블명 반환 (Entity 메타에서 추출)"""
        if self._owner_class is None:
            return None
        # EntityMeta에서 테이블명 가져오기
        meta = getattr(self._owner_class, "__bloom_meta__", None)
        if meta is not None:
            return meta.table_name
        return None

    # -------------------------------------------------------------------------
    # 비교 연산자
    # -------------------------------------------------------------------------

    @overload
    def __eq__(self, other: "FieldExpression[Any]") -> "JoinCondition": ...
    @overload
    def __eq__(self, other: T | None) -> "Condition": ...

    def __eq__(
        self, other: T | "FieldExpression[Any]" | None
    ) -> "Condition | JoinCondition":
        # FieldExpression 간 비교 (JOIN ON 조건)
        if isinstance(other, FieldExpression):
            return JoinCondition(
                left_field=self.name,
                right_field=other.name,
                operator="=",
                left_table=self.table_name,
                right_table=other.table_name,
            )
        if other is None:
            return Condition(self.name, "IS", None, self.table_name)
        return Condition(self.name, "=", other, self.table_name)

    @overload
    def __ne__(self, other: "FieldExpression[Any]") -> "JoinCondition": ...
    @overload
    def __ne__(self, other: T | None) -> "Condition": ...

    def __ne__(
        self, other: T | "FieldExpression[Any]" | None
    ) -> "Condition | JoinCondition":
        # FieldExpression 간 비교 (JOIN ON 조건)
        if isinstance(other, FieldExpression):
            return JoinCondition(
                left_field=self.name,
                right_field=other.name,
                operator="!=",
                left_table=self.table_name,
                right_table=other.table_name,
            )
        if other is None:
            return Condition(self.name, "IS NOT", None, self.table_name)
        return Condition(self.name, "!=", other, self.table_name)

    @overload
    def __gt__(self, other: "FieldExpression[Any]") -> "JoinCondition": ...
    @overload
    def __gt__(self, other: T) -> "Condition": ...

    def __gt__(self, other: T | "FieldExpression[Any]") -> "Condition | JoinCondition":
        if isinstance(other, FieldExpression):
            return JoinCondition(
                left_field=self.name,
                right_field=other.name,
                operator=">",
                left_table=self.table_name,
                right_table=other.table_name,
            )
        return Condition(self.name, ">", other, self.table_name)

    @overload
    def __ge__(self, other: "FieldExpression[Any]") -> "JoinCondition": ...
    @overload
    def __ge__(self, other: T) -> "Condition": ...

    def __ge__(self, other: T | "FieldExpression[Any]") -> "Condition | JoinCondition":
        if isinstance(other, FieldExpression):
            return JoinCondition(
                left_field=self.name,
                right_field=other.name,
                operator=">=",
                left_table=self.table_name,
                right_table=other.table_name,
            )
        return Condition(self.name, ">=", other, self.table_name)

    @overload
    def __lt__(self, other: "FieldExpression[Any]") -> "JoinCondition": ...
    @overload
    def __lt__(self, other: T) -> "Condition": ...

    def __lt__(self, other: T | "FieldExpression[Any]") -> "Condition | JoinCondition":
        if isinstance(other, FieldExpression):
            return JoinCondition(
                left_field=self.name,
                right_field=other.name,
                operator="<",
                left_table=self.table_name,
                right_table=other.table_name,
            )
        return Condition(self.name, "<", other, self.table_name)

    @overload
    def __le__(self, other: "FieldExpression[Any]") -> "JoinCondition": ...
    @overload
    def __le__(self, other: T) -> "Condition": ...

    def __le__(self, other: T | "FieldExpression[Any]") -> "Condition | JoinCondition":
        if isinstance(other, FieldExpression):
            return JoinCondition(
                left_field=self.name,
                right_field=other.name,
                operator="<=",
                left_table=self.table_name,
                right_table=other.table_name,
            )
        return Condition(self.name, "<=", other, self.table_name)

    # -------------------------------------------------------------------------
    # 문자열 연산
    # -------------------------------------------------------------------------

    def like(self, pattern: str) -> Condition:
        """LIKE 패턴 매칭"""
        return Condition(self.name, "LIKE", pattern, self.table_name)

    def ilike(self, pattern: str) -> Condition:
        """대소문자 무시 LIKE (PostgreSQL)"""
        return Condition(self.name, "ILIKE", pattern, self.table_name)

    def startswith(self, prefix: str) -> Condition:
        """문자열 시작 매칭"""
        return Condition(self.name, "LIKE", f"{prefix}%", self.table_name)

    def endswith(self, suffix: str) -> Condition:
        """문자열 끝 매칭"""
        return Condition(self.name, "LIKE", f"%{suffix}", self.table_name)

    def contains(self, substring: str) -> Condition:
        """문자열 포함 매칭"""
        return Condition(self.name, "LIKE", f"%{substring}%", self.table_name)

    # -------------------------------------------------------------------------
    # 컬렉션 연산
    # -------------------------------------------------------------------------

    def in_(self, values: list[T] | Subquery) -> "Condition | SubqueryInCondition":
        """IN 연산 (리스트 또는 서브쿼리)

        Examples:
            User.id.in_([1, 2, 3])
            User.id.in_(Query(Order).select(Order.user_id).subquery())
        """
        if isinstance(values, Subquery):
            return SubqueryInCondition(
                self.name, values, negate=False, table_name=self.table_name
            )
        return Condition(self.name, "IN", values, self.table_name)

    def not_in(self, values: list[T] | Subquery) -> "Condition | SubqueryInCondition":
        """NOT IN 연산 (리스트 또는 서브쿼리)

        Examples:
            User.id.not_in([1, 2, 3])
            User.id.not_in(Query(Order).select(Order.user_id).subquery())
        """
        if isinstance(values, Subquery):
            return SubqueryInCondition(
                self.name, values, negate=True, table_name=self.table_name
            )
        return Condition(self.name, "NOT IN", values, self.table_name)

    def between(self, low: T, high: T) -> Condition:
        """BETWEEN 연산"""
        return Condition(self.name, "BETWEEN", (low, high), self.table_name)

    # -------------------------------------------------------------------------
    # NULL 체크
    # -------------------------------------------------------------------------

    def is_null(self) -> Condition:
        """IS NULL 체크"""
        return Condition(self.name, "IS", None, self.table_name)

    def is_not_null(self) -> Condition:
        """IS NOT NULL 체크"""
        return Condition(self.name, "IS NOT", None, self.table_name)

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


class SubqueryInCondition:
    """서브쿼리 IN 조건

    Examples:
        User.id.in_(subquery)      →  "id" IN (SELECT ...)
        User.id.not_in(subquery)   →  "id" NOT IN (SELECT ...)
    """

    __slots__ = ("field", "subquery", "negate", "table_name")

    def __init__(
        self,
        field: str,
        subquery: Subquery,
        negate: bool = False,
        table_name: str | None = None,
    ) -> None:
        self.field = field
        self.subquery = subquery
        self.negate = negate
        self.table_name = table_name  # JOIN 시 테이블 접두사

    def __and__(
        self, other: Condition | ConditionGroup | SubqueryInCondition
    ) -> ConditionGroup:
        return ConditionGroup("AND", [self, other])  # type: ignore[list-item]

    def __or__(
        self, other: Condition | ConditionGroup | SubqueryInCondition
    ) -> ConditionGroup:
        return ConditionGroup("OR", [self, other])  # type: ignore[list-item]

    def _get_field_ref(self) -> str:
        """테이블 접두사가 있으면 포함한 필드 참조 반환"""
        if self.table_name:
            return f'"{self.table_name}"."{self.field}"'
        return f'"{self.field}"'  # 서브쿼리는 항상 따옴표 필요

    def to_sql(
        self, param_prefix: str = "sq", depth: int = 0
    ) -> tuple[str, dict[str, Any]]:
        """SQL 생성"""
        subquery_sql, params = self.subquery.to_sql(f"{param_prefix}_{depth}")
        op = "NOT IN" if self.negate else "IN"
        field_ref = self._get_field_ref()
        return f"{field_ref} {op} {subquery_sql}", params


class SubqueryCondition:
    """서브쿼리 조건 (EXISTS, NOT EXISTS 등)

    Examples:
        Subquery(query).exists()       →  EXISTS (SELECT ...)
        Subquery(query).not_exists()   →  NOT EXISTS (SELECT ...)
    """

    __slots__ = ("subquery", "operator")

    def __init__(self, subquery: Subquery, operator: str) -> None:
        self.subquery = subquery
        self.operator = operator  # "EXISTS", "NOT EXISTS"

    def __and__(
        self, other: Condition | ConditionGroup | SubqueryCondition
    ) -> ConditionGroup:
        return ConditionGroup("AND", [self, other])  # type: ignore[list-item]

    def __or__(
        self, other: Condition | ConditionGroup | SubqueryCondition
    ) -> ConditionGroup:
        return ConditionGroup("OR", [self, other])  # type: ignore[list-item]

    def to_sql(
        self, param_prefix: str = "sq", depth: int = 0
    ) -> tuple[str, dict[str, Any]]:
        """SQL 생성"""
        subquery_sql, params = self.subquery.to_sql(f"{param_prefix}_{depth}")
        return f"{self.operator} {subquery_sql}", params


class ScalarSubquery:
    """스칼라 서브쿼리 - 단일 값을 반환하는 서브쿼리

    비교 연산자를 지원하여 WHERE 절에서 사용 가능합니다.

    Examples:
        avg_amount = Subquery(Query(Order).annotate(avg=Avg(Order.amount))).scalar()
        Order.amount > avg_amount  →  "amount" > (SELECT AVG(amount) FROM orders)
    """

    __slots__ = ("subquery", "column")

    def __init__(self, subquery: Subquery, column: str | None = None) -> None:
        self.subquery = subquery
        self.column = column

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

    def __radd__(self, other: Any) -> ScalarSubqueryExpr:
        return ScalarSubqueryExpr(self, other, "+", reverse=True)

    def __rsub__(self, other: Any) -> ScalarSubqueryExpr:
        return ScalarSubqueryExpr(self, other, "-", reverse=True)

    def _get_sql(self) -> str:
        sql, _ = self.subquery.to_sql()
        return sql

    def to_sql(self, param_prefix: str = "sq") -> tuple[str, dict[str, Any]]:
        """SQL 생성"""
        return self.subquery.to_sql(param_prefix)


class ScalarSubqueryExpr:
    """스칼라 서브쿼리 표현식 (산술 연산 지원)"""

    __slots__ = ("scalar", "value", "operator", "reverse")

    def __init__(
        self,
        scalar: ScalarSubquery,
        value: Any,
        operator: str,
        reverse: bool = False,
    ) -> None:
        self.scalar = scalar
        self.value = value
        self.operator = operator
        self.reverse = reverse

    def to_sql(self, param_prefix: str = "sq") -> tuple[str, dict[str, Any]]:
        sql, params = self.scalar.to_sql(param_prefix)
        param_name = f"{param_prefix}_val"
        params[param_name] = self.value
        if self.reverse:
            return f":{param_name} {self.operator} {sql}", params
        return f"{sql} {self.operator} :{param_name}", params


# =============================================================================
# Window Functions
# =============================================================================


class FrameBound:
    """Window Frame 경계 상수"""

    UNBOUNDED_PRECEDING = "UNBOUNDED PRECEDING"
    CURRENT_ROW = "CURRENT ROW"
    UNBOUNDED_FOLLOWING = "UNBOUNDED FOLLOWING"

    @staticmethod
    def preceding(n: int) -> str:
        """N PRECEDING"""
        return f"{n} PRECEDING"

    @staticmethod
    def following(n: int) -> str:
        """N FOLLOWING"""
        return f"{n} FOLLOWING"


class WindowFrame:
    """Window Frame 정의 (ROWS/RANGE BETWEEN)

    Examples:
        WindowFrame()  # 기본값: RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        WindowFrame("ROWS", "UNBOUNDED PRECEDING", "CURRENT ROW")
        WindowFrame("ROWS", FrameBound.preceding(1), FrameBound.following(1))
    """

    __slots__ = ("frame_type", "start", "end")

    def __init__(
        self,
        frame_type: str = "RANGE",
        start: str = FrameBound.UNBOUNDED_PRECEDING,
        end: str = FrameBound.CURRENT_ROW,
    ) -> None:
        self.frame_type = frame_type  # "ROWS" or "RANGE"
        self.start = start
        self.end = end

    def to_sql(self) -> str:
        """SQL Frame 절 생성"""
        return f"{self.frame_type} BETWEEN {self.start} AND {self.end}"


class WindowSpec:
    """Window 명세 (OVER 절)

    Examples:
        WindowSpec(partition_by=["user_id"], order_by=[OrderBy("created_at", "DESC")])
        → OVER (PARTITION BY "user_id" ORDER BY created_at DESC)
    """

    __slots__ = ("partition_by", "order_by", "frame", "alias")

    def __init__(
        self,
        partition_by: list[str | FieldExpression[Any]] | None = None,
        order_by: list[OrderBy] | None = None,
        frame: WindowFrame | None = None,
        alias: str | None = None,
    ) -> None:
        self.partition_by: list[str | FieldExpression[Any]] = (
            partition_by if partition_by is not None else []
        )
        self.order_by: list[OrderBy] = order_by if order_by is not None else []
        self.frame = frame
        self.alias = alias  # 윈도우 별칭 (WINDOW 절에서 사용)

    def to_sql(self) -> str:
        """SQL OVER 절 생성"""
        parts: list[str] = []

        if self.partition_by:
            cols = []
            for col in self.partition_by:
                if hasattr(col, "name"):
                    cols.append(f'"{col.name}"')  # type: ignore[union-attr]
                else:
                    cols.append(f'"{col}"')
            parts.append(f"PARTITION BY {', '.join(cols)}")

        if self.order_by:
            order_parts = [o.to_sql() for o in self.order_by]
            parts.append(f"ORDER BY {', '.join(order_parts)}")

        if self.frame:
            parts.append(self.frame.to_sql())

        inner = " ".join(parts)
        return f"OVER ({inner})" if inner else "OVER ()"


class WindowFunction:
    """윈도우 함수 기본 클래스

    Examples:
        RowNumber().over(partition_by=[Order.user_id], order_by=[Order.created_at.desc()])
        → ROW_NUMBER() OVER (PARTITION BY "user_id" ORDER BY created_at DESC)
    """

    __slots__ = ("_window", "_alias")

    _func_name: str = ""

    def __init__(self) -> None:
        self._window: WindowSpec | None = None
        self._alias: str | None = None

    def over(
        self,
        partition_by: list[str | FieldExpression[Any]] | None = None,
        order_by: list[OrderBy | FieldExpression[Any]] | None = None,
        frame: WindowFrame | None = None,
    ) -> Self:
        """OVER 절 설정

        Examples:
            RowNumber().over(
                partition_by=[Order.user_id],
                order_by=[Order.amount.desc()]
            )
        """
        # OrderBy 변환
        converted_order: list[OrderBy] = []
        if order_by:
            for o in order_by:
                if isinstance(o, OrderBy):
                    converted_order.append(o)
                elif hasattr(o, "asc"):  # FieldExpression
                    converted_order.append(o.asc())  # type: ignore[union-attr]

        self._window = WindowSpec(
            partition_by=partition_by or [],
            order_by=converted_order,
            frame=frame,
        )
        return self

    def as_(self, alias: str) -> Self:
        """별칭 지정"""
        self._alias = alias
        return self

    def _get_args_sql(self) -> str:
        """함수 인자 SQL (서브클래스에서 오버라이드)"""
        return ""

    def to_sql(self) -> str:
        """SQL 표현식 생성"""
        args = self._get_args_sql()
        sql = f"{self._func_name}({args})"

        if self._window:
            sql = f"{sql} {self._window.to_sql()}"

        if self._alias:
            sql = f"{sql} AS {self._alias}"

        return sql

    @property
    def output_name(self) -> str:
        """결과 컬럼 이름"""
        if self._alias:
            return self._alias
        return self._func_name.lower()


# -----------------------------------------------------------------------------
# Ranking Functions
# -----------------------------------------------------------------------------


class RowNumber(WindowFunction):
    """ROW_NUMBER() 윈도우 함수

    Examples:
        RowNumber().over(order_by=[User.created_at.desc()]).as_("rn")
        → ROW_NUMBER() OVER (ORDER BY created_at DESC) AS rn
    """

    _func_name = "ROW_NUMBER"


class Rank(WindowFunction):
    """RANK() 윈도우 함수 - 동순위 시 다음 순위 건너뜀

    Examples:
        Rank().over(partition_by=[Order.user_id], order_by=[Order.amount.desc()])
        → RANK() OVER (PARTITION BY "user_id" ORDER BY amount DESC)
    """

    _func_name = "RANK"


class DenseRank(WindowFunction):
    """DENSE_RANK() 윈도우 함수 - 동순위 시 다음 순위 건너뛰지 않음

    Examples:
        DenseRank().over(order_by=[Score.points.desc()]).as_("dense_rank")
        → DENSE_RANK() OVER (ORDER BY points DESC) AS dense_rank
    """

    _func_name = "DENSE_RANK"


class NTile(WindowFunction):
    """NTILE(n) 윈도우 함수 - n개 그룹으로 분할

    Examples:
        NTile(4).over(order_by=[User.score.desc()]).as_("quartile")
        → NTILE(4) OVER (ORDER BY score DESC) AS quartile
    """

    __slots__ = ("_window", "_alias", "n")

    _func_name = "NTILE"

    def __init__(self, n: int = 1) -> None:
        super().__init__()
        self.n = n

    def _get_args_sql(self) -> str:
        return str(self.n)


class PercentRank(WindowFunction):
    """PERCENT_RANK() 윈도우 함수 - 백분위 순위 (0~1)

    Examples:
        PercentRank().over(order_by=[Score.points.desc()])
        → PERCENT_RANK() OVER (ORDER BY points DESC)
    """

    _func_name = "PERCENT_RANK"


class CumeDist(WindowFunction):
    """CUME_DIST() 윈도우 함수 - 누적 분포

    Examples:
        CumeDist().over(order_by=[Score.points.desc()])
        → CUME_DIST() OVER (ORDER BY points DESC)
    """

    _func_name = "CUME_DIST"


# -----------------------------------------------------------------------------
# Value Functions
# -----------------------------------------------------------------------------


class Lag(WindowFunction):
    """LAG() 윈도우 함수 - 이전 행 값

    Examples:
        Lag(Order.amount, 1, 0).over(partition_by=[Order.user_id], order_by=[Order.created_at])
        → LAG(amount, 1, 0) OVER (PARTITION BY "user_id" ORDER BY created_at)
    """

    __slots__ = ("_window", "_alias", "field", "offset", "default")

    _func_name = "LAG"

    def __init__(
        self,
        field: str | FieldExpression[Any] = "",
        offset: int = 1,
        default: Any = None,
    ) -> None:
        super().__init__()
        if hasattr(field, "name"):
            self.field: str = field.name  # type: ignore[union-attr]
        else:
            self.field = field  # type: ignore[assignment]
        self.offset = offset
        self.default = default

    def _get_args_sql(self) -> str:
        parts = [str(self.field)]
        if self.offset != 1 or self.default is not None:
            parts.append(str(self.offset))
        if self.default is not None:
            if isinstance(self.default, str):
                parts.append(f"'{self.default}'")
            else:
                parts.append(str(self.default))
        return ", ".join(parts)


class Lead(WindowFunction):
    """LEAD() 윈도우 함수 - 다음 행 값

    Examples:
        Lead(Order.amount, 1).over(order_by=[Order.created_at])
        → LEAD(amount, 1) OVER (ORDER BY created_at)
    """

    __slots__ = ("_window", "_alias", "field", "offset", "default")

    _func_name = "LEAD"

    def __init__(
        self,
        field: str | FieldExpression[Any] = "",
        offset: int = 1,
        default: Any = None,
    ) -> None:
        super().__init__()
        if hasattr(field, "name"):
            self.field: str = field.name  # type: ignore[union-attr]
        else:
            self.field = field  # type: ignore[assignment]
        self.offset = offset
        self.default = default

    def _get_args_sql(self) -> str:
        parts = [str(self.field)]
        if self.offset != 1 or self.default is not None:
            parts.append(str(self.offset))
        if self.default is not None:
            if isinstance(self.default, str):
                parts.append(f"'{self.default}'")
            else:
                parts.append(str(self.default))
        return ", ".join(parts)


class FirstValue(WindowFunction):
    """FIRST_VALUE() 윈도우 함수 - 윈도우 내 첫 번째 값

    Examples:
        FirstValue(Order.amount).over(
            partition_by=[Order.user_id],
            order_by=[Order.created_at],
            frame=WindowFrame("ROWS", FrameBound.UNBOUNDED_PRECEDING, FrameBound.UNBOUNDED_FOLLOWING)
        )
    """

    __slots__ = ("_window", "_alias", "field")

    _func_name = "FIRST_VALUE"

    def __init__(self, field: str | FieldExpression[Any] = "") -> None:
        super().__init__()
        if hasattr(field, "name"):
            self.field: str = field.name  # type: ignore[union-attr]
        else:
            self.field = field  # type: ignore[assignment]

    def _get_args_sql(self) -> str:
        return str(self.field)


class LastValue(WindowFunction):
    """LAST_VALUE() 윈도우 함수 - 윈도우 내 마지막 값

    Examples:
        LastValue(Order.amount).over(
            partition_by=[Order.user_id],
            order_by=[Order.created_at],
            frame=WindowFrame("ROWS", FrameBound.UNBOUNDED_PRECEDING, FrameBound.UNBOUNDED_FOLLOWING)
        )
    """

    __slots__ = ("_window", "_alias", "field")

    _func_name = "LAST_VALUE"

    def __init__(self, field: str | FieldExpression[Any] = "") -> None:
        super().__init__()
        if hasattr(field, "name"):
            self.field: str = field.name  # type: ignore[union-attr]
        else:
            self.field = field  # type: ignore[assignment]

    def _get_args_sql(self) -> str:
        return str(self.field)


class NthValue(WindowFunction):
    """NTH_VALUE() 윈도우 함수 - 윈도우 내 N번째 값

    Examples:
        NthValue(Order.amount, 2).over(order_by=[Order.created_at])
        → NTH_VALUE(amount, 2) OVER (ORDER BY created_at)
    """

    __slots__ = ("_window", "_alias", "field", "n")

    _func_name = "NTH_VALUE"

    def __init__(self, field: str | FieldExpression[Any] = "", n: int = 1) -> None:
        super().__init__()
        if hasattr(field, "name"):
            self.field: str = field.name  # type: ignore[union-attr]
        else:
            self.field = field  # type: ignore[assignment]
        self.n = n

    def _get_args_sql(self) -> str:
        return f"{self.field}, {self.n}"


# -----------------------------------------------------------------------------
# Aggregate Functions as Window Functions
# -----------------------------------------------------------------------------


class SumOver(WindowFunction):
    """SUM() OVER - 윈도우 합계

    Examples:
        SumOver(Order.amount).over(partition_by=[Order.user_id]).as_("running_total")
        → SUM(amount) OVER (PARTITION BY "user_id") AS running_total
    """

    __slots__ = ("_window", "_alias", "field")

    _func_name = "SUM"

    def __init__(self, field: str | FieldExpression[Any] = "") -> None:
        super().__init__()
        if hasattr(field, "name"):
            self.field: str = field.name  # type: ignore[union-attr]
        else:
            self.field = field  # type: ignore[assignment]

    def _get_args_sql(self) -> str:
        return str(self.field)


class AvgOver(WindowFunction):
    """AVG() OVER - 윈도우 평균

    Examples:
        AvgOver(Order.amount).over(
            partition_by=[Order.user_id],
            frame=WindowFrame("ROWS", FrameBound.preceding(2), FrameBound.CURRENT_ROW)
        ).as_("moving_avg")
    """

    __slots__ = ("_window", "_alias", "field")

    _func_name = "AVG"

    def __init__(self, field: str | FieldExpression[Any] = "") -> None:
        super().__init__()
        if hasattr(field, "name"):
            self.field: str = field.name  # type: ignore[union-attr]
        else:
            self.field = field  # type: ignore[assignment]

    def _get_args_sql(self) -> str:
        return str(self.field)


class CountOver(WindowFunction):
    """COUNT() OVER - 윈도우 개수

    Examples:
        CountOver("*").over(partition_by=[Order.user_id]).as_("user_order_count")
        → COUNT(*) OVER (PARTITION BY "user_id") AS user_order_count
    """

    __slots__ = ("_window", "_alias", "field")

    _func_name = "COUNT"

    def __init__(self, field: str | FieldExpression[Any] = "*") -> None:
        super().__init__()
        if hasattr(field, "name"):
            self.field: str = field.name  # type: ignore[union-attr]
        else:
            self.field = field  # type: ignore[assignment]

    def _get_args_sql(self) -> str:
        return str(self.field)


class MinOver(WindowFunction):
    """MIN() OVER - 윈도우 최소값

    Examples:
        MinOver(Order.amount).over(partition_by=[Order.user_id])
        → MIN(amount) OVER (PARTITION BY "user_id")
    """

    __slots__ = ("_window", "_alias", "field")

    _func_name = "MIN"

    def __init__(self, field: str | FieldExpression[Any] = "") -> None:
        super().__init__()
        if hasattr(field, "name"):
            self.field: str = field.name  # type: ignore[union-attr]
        else:
            self.field = field  # type: ignore[assignment]

    def _get_args_sql(self) -> str:
        return str(self.field)


class MaxOver(WindowFunction):
    """MAX() OVER - 윈도우 최대값

    Examples:
        MaxOver(Order.amount).over(partition_by=[Order.user_id])
        → MAX(amount) OVER (PARTITION BY "user_id")
    """

    __slots__ = ("_window", "_alias", "field")

    _func_name = "MAX"

    def __init__(self, field: str | FieldExpression[Any] = "") -> None:
        super().__init__()
        if hasattr(field, "name"):
            self.field: str = field.name  # type: ignore[union-attr]
        else:
            self.field = field  # type: ignore[assignment]

    def _get_args_sql(self) -> str:
        return str(self.field)


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


# JoinCondition은 아래에 정의되므로 forward reference 필요
# JoinClause.condition에서 사용할 타입 별칭
JoinOnCondition = "Condition | ConditionGroup | JoinCondition"


class JoinClause:
    """JOIN 절 표현

    Examples:
        JoinClause(Order, User, Order.user_id == User.id, JoinType.INNER)
        → INNER JOIN "users" ON "orders"."user_id" = "users"."id"
    """

    __slots__ = ("target", "condition", "join_type", "alias")

    def __init__(
        self,
        target: type[Any],
        condition: Condition | ConditionGroup | JoinCondition | None = None,
        join_type: str = JoinType.INNER,
        alias: str | None = None,
    ) -> None:
        self.target = target  # 조인할 엔티티 클래스
        self.condition = condition  # ON 조건
        self.join_type = join_type  # JOIN 타입
        self.alias = alias  # 테이블 별칭

    def _replace_table_in_condition(
        self, cond: Any, original_table: str, new_table: str
    ) -> Any:
        """조건 내의 테이블명을 별칭으로 교체"""
        from copy import copy

        if isinstance(cond, JoinCondition):
            new_cond = copy(cond)
            if new_cond.left_table == original_table:
                new_cond.left_table = new_table
            if new_cond.right_table == original_table:
                new_cond.right_table = new_table
            return new_cond
        elif isinstance(cond, Condition):
            new_cond = copy(cond)
            if new_cond.table_name == original_table:
                new_cond.table_name = new_table
            return new_cond
        elif isinstance(cond, ConditionGroup):
            new_conditions = [
                self._replace_table_in_condition(c, original_table, new_table)
                for c in cond.conditions
            ]
            return ConditionGroup(cond.operator, new_conditions)
        return cond

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

        # 별칭이 있으면 조건에서 테이블명을 별칭으로 교체
        condition = self.condition
        if self.alias:
            condition = self._replace_table_in_condition(
                condition, table_name, self.alias
            )

        cond_sql, params = condition.to_sql(param_prefix)
        return f"{self.join_type} {table_ref} ON {cond_sql}", params


class JoinCondition:
    """JOIN ON 조건 - 두 테이블의 컬럼 비교

    Examples:
        on(Order.user_id, User.id)  →  "orders"."user_id" = "users"."id"
    """

    __slots__ = ("left_field", "right_field", "operator", "left_table", "right_table")

    def __init__(
        self,
        left_field: str | FieldExpression[Any],
        right_field: str | FieldExpression[Any],
        operator: str = "=",
        left_table: str | None = None,
        right_table: str | None = None,
    ) -> None:
        # FieldExpression에서 테이블명과 필드명 추출
        if isinstance(left_field, FieldExpression):
            self.left_table: str | None = (
                left_table if left_table is not None else left_field.table_name
            )
            self.left_field: str = left_field.name
        else:
            self.left_table = left_table
            self.left_field = left_field

        if isinstance(right_field, FieldExpression):
            self.right_table: str | None = (
                right_table if right_table is not None else right_field.table_name
            )
            self.right_field: str = right_field.name
        else:
            self.right_table = right_table
            self.right_field = right_field

        self.operator = operator

    def __and__(self, other: ConditionLike) -> ConditionGroup:
        """AND 연산으로 ConditionGroup 생성"""
        return ConditionGroup("AND", [self, other])

    def __or__(self, other: ConditionLike) -> ConditionGroup:
        """OR 연산으로 ConditionGroup 생성"""
        return ConditionGroup("OR", [self, other])

    def to_sql(
        self, param_prefix: str = "j", depth: int = 0
    ) -> tuple[str, dict[str, Any]]:
        """SQL 조건 생성 (파라미터 없이 컬럼 간 비교)

        depth 인자는 ConditionGroup과의 호환성을 위해 존재하지만 사용되지 않습니다.
        """
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
