"""Expressions 테스트 - Condition, ConditionGroup, OrderBy, FieldExpression"""

import pytest
from dataclasses import dataclass

from bloom.db import Entity, Column, PrimaryKey
from bloom.db.expressions import Condition, ConditionGroup, OrderBy, FieldExpression


# =============================================================================
# Condition Tests
# =============================================================================


class TestCondition:
    """Condition 테스트"""

    async def test_basic_condition_to_sql(self):
        """기본 조건 SQL 생성"""
        cond = Condition("name", "=", "alice")
        sql, params = cond.to_sql("p")

        assert sql == "name = :p_name"
        assert params == {"p_name": "alice"}

    async def test_comparison_operators(self):
        """비교 연산자"""
        cases = [
            (Condition("age", ">", 18), "age > :p_age", {"p_age": 18}),
            (Condition("age", ">=", 18), "age >= :p_age", {"p_age": 18}),
            (Condition("age", "<", 18), "age < :p_age", {"p_age": 18}),
            (Condition("age", "<=", 18), "age <= :p_age", {"p_age": 18}),
            (Condition("name", "!=", "bob"), "name != :p_name", {"p_name": "bob"}),
        ]

        for cond, expected_sql, expected_params in cases:
            sql, params = cond.to_sql("p")
            assert sql == expected_sql
            assert params == expected_params

    async def test_is_null_condition(self):
        """IS NULL 조건"""
        cond = Condition("email", "IS", None)
        sql, params = cond.to_sql("p")

        assert sql == "email IS NULL"
        assert params == {}

    async def test_is_not_null_condition(self):
        """IS NOT NULL 조건"""
        cond = Condition("email", "IS NOT", None)
        sql, params = cond.to_sql("p")

        assert sql == "email IS NOT NULL"
        assert params == {}

    async def test_in_condition(self):
        """IN 조건"""
        cond = Condition("status", "IN", ["active", "pending"])
        sql, params = cond.to_sql("p")

        assert sql == "status IN (:p_status_0, :p_status_1)"
        assert params == {"p_status_0": "active", "p_status_1": "pending"}

    async def test_in_empty_list(self):
        """IN 빈 리스트는 false"""
        cond = Condition("status", "IN", [])
        sql, params = cond.to_sql("p")

        assert sql == "1=0"
        assert params == {}

    async def test_not_in_condition(self):
        """NOT IN 조건"""
        cond = Condition("status", "NOT IN", ["deleted", "banned"])
        sql, params = cond.to_sql("p")

        assert sql == "status NOT IN (:p_status_0, :p_status_1)"
        assert params == {"p_status_0": "deleted", "p_status_1": "banned"}

    async def test_not_in_empty_list(self):
        """NOT IN 빈 리스트는 true"""
        cond = Condition("status", "NOT IN", [])
        sql, params = cond.to_sql("p")

        assert sql == "1=1"
        assert params == {}

    async def test_between_condition(self):
        """BETWEEN 조건"""
        cond = Condition("age", "BETWEEN", (18, 65))
        sql, params = cond.to_sql("p")

        assert sql == "age BETWEEN :p_age_low AND :p_age_high"
        assert params == {"p_age_low": 18, "p_age_high": 65}

    async def test_like_condition(self):
        """LIKE 조건"""
        cond = Condition("name", "LIKE", "%alice%")
        sql, params = cond.to_sql("p")

        assert sql == "name LIKE :p_name"
        assert params == {"p_name": "%alice%"}

    async def test_condition_and(self):
        """AND 조합"""
        cond1 = Condition("name", "=", "alice")
        cond2 = Condition("age", ">", 18)

        group = cond1 & cond2

        assert isinstance(group, ConditionGroup)
        assert group.operator == "AND"
        assert len(group.conditions) == 2

    async def test_condition_or(self):
        """OR 조합"""
        cond1 = Condition("status", "=", "active")
        cond2 = Condition("role", "=", "admin")

        group = cond1 | cond2

        assert isinstance(group, ConditionGroup)
        assert group.operator == "OR"
        assert len(group.conditions) == 2

    async def test_condition_not(self):
        """NOT 연산"""
        cond = Condition("status", "=", "deleted")
        negated = ~cond

        assert negated.operator == "NOT ="
        assert negated.value == "deleted"


# =============================================================================
# ConditionGroup Tests
# =============================================================================


class TestConditionGroup:
    """ConditionGroup 테스트"""

    async def test_empty_group(self):
        """빈 그룹은 1=1"""
        group = ConditionGroup("AND", [])
        sql, params = group.to_sql()

        assert sql == "1=1"
        assert params == {}

    async def test_single_condition_group(self):
        """단일 조건 그룹"""
        cond = Condition("name", "=", "alice")
        group = ConditionGroup("AND", [cond])
        sql, params = group.to_sql()

        assert "name = " in sql
        assert "alice" in params.values()

    async def test_and_group_to_sql(self):
        """AND 그룹 SQL 생성"""
        cond1 = Condition("name", "=", "alice")
        cond2 = Condition("age", ">", 18)
        group = ConditionGroup("AND", [cond1, cond2])

        sql, params = group.to_sql()

        assert " AND " in sql
        assert "(" in sql and ")" in sql

    async def test_or_group_to_sql(self):
        """OR 그룹 SQL 생성"""
        cond1 = Condition("status", "=", "active")
        cond2 = Condition("role", "=", "admin")
        group = ConditionGroup("OR", [cond1, cond2])

        sql, params = group.to_sql()

        assert " OR " in sql

    async def test_nested_groups(self):
        """중첩 그룹"""
        # (name = "alice" AND age > 18) OR (status = "admin")
        inner_group = ConditionGroup(
            "AND",
            [
                Condition("name", "=", "alice"),
                Condition("age", ">", 18),
            ],
        )
        outer_group = ConditionGroup(
            "OR",
            [
                inner_group,
                Condition("status", "=", "admin"),
            ],
        )

        sql, params = outer_group.to_sql()

        assert " OR " in sql
        assert " AND " in sql

    async def test_group_chaining_and(self):
        """그룹 체이닝 - AND"""
        cond1 = Condition("a", "=", 1)
        cond2 = Condition("b", "=", 2)
        cond3 = Condition("c", "=", 3)

        group = (cond1 & cond2) & cond3

        assert group.operator == "AND"
        assert len(group.conditions) == 3  # 플래트닝

    async def test_group_chaining_or(self):
        """그룹 체이닝 - OR"""
        cond1 = Condition("a", "=", 1)
        cond2 = Condition("b", "=", 2)
        cond3 = Condition("c", "=", 3)

        group = (cond1 | cond2) | cond3

        assert group.operator == "OR"
        assert len(group.conditions) == 3

    async def test_group_not(self):
        """그룹 NOT (De Morgan)"""
        # NOT (a AND b) = (NOT a) OR (NOT b)
        group = ConditionGroup(
            "AND",
            [
                Condition("a", "=", 1),
                Condition("b", "=", 2),
            ],
        )

        negated = ~group

        assert negated.operator == "OR"
        assert len(negated.conditions) == 2


# =============================================================================
# OrderBy Tests
# =============================================================================


class TestOrderBy:
    """OrderBy 테스트"""

    async def test_asc_order(self):
        """오름차순"""
        order = OrderBy("name", "ASC")
        assert order.to_sql() == "name ASC"

    async def test_desc_order(self):
        """내림차순"""
        order = OrderBy("name", "DESC")
        assert order.to_sql() == "name DESC"

    async def test_default_is_asc(self):
        """기본값은 ASC"""
        order = OrderBy("name")
        assert order.direction == "ASC"


# =============================================================================
# FieldExpression Tests
# =============================================================================


class TestFieldExpression:
    """FieldExpression 테스트"""

    @pytest.fixture
    def field_expr(self):
        """테스트용 FieldExpression"""
        from bloom.db.columns import Column

        col = Column[str]()
        col.name = "name"  # type: ignore
        return FieldExpression("name", col)

    @pytest.fixture
    def age_expr(self):
        """숫자 필드 표현식"""
        from bloom.db.columns import Column

        col = Column[int]()
        col.name = "age"  # type: ignore
        return FieldExpression("age", col)

    # -------------------------------------------------------------------------
    # 비교 연산자
    # -------------------------------------------------------------------------

    async def test_eq(self, field_expr):
        """== 연산"""
        cond = field_expr == "alice"
        assert isinstance(cond, Condition)
        assert cond.field == "name"
        assert cond.operator == "="
        assert cond.value == "alice"

    async def test_eq_none(self, field_expr):
        """== None은 IS NULL"""
        cond = field_expr == None
        assert cond.operator == "IS"

    async def test_ne(self, field_expr):
        """!= 연산"""
        cond = field_expr != "bob"
        assert cond.operator == "!="

    async def test_ne_none(self, field_expr):
        """!= None은 IS NOT NULL"""
        cond = field_expr != None
        assert cond.operator == "IS NOT"

    async def test_gt(self, age_expr):
        """> 연산"""
        cond = age_expr > 18
        assert cond.operator == ">"
        assert cond.value == 18

    async def test_ge(self, age_expr):
        """>= 연산"""
        cond = age_expr >= 18
        assert cond.operator == ">="

    async def test_lt(self, age_expr):
        """< 연산"""
        cond = age_expr < 65
        assert cond.operator == "<"

    async def test_le(self, age_expr):
        """<= 연산"""
        cond = age_expr <= 65
        assert cond.operator == "<="

    # -------------------------------------------------------------------------
    # 문자열 연산
    # -------------------------------------------------------------------------

    async def test_like(self, field_expr):
        """LIKE"""
        cond = field_expr.like("%alice%")
        assert cond.operator == "LIKE"
        assert cond.value == "%alice%"

    async def test_ilike(self, field_expr):
        """ILIKE (대소문자 무시)"""
        cond = field_expr.ilike("%alice%")
        assert cond.operator == "ILIKE"

    async def test_startswith(self, field_expr):
        """startswith"""
        cond = field_expr.startswith("al")
        assert cond.operator == "LIKE"
        assert cond.value == "al%"

    async def test_endswith(self, field_expr):
        """endswith"""
        cond = field_expr.endswith("ice")
        assert cond.operator == "LIKE"
        assert cond.value == "%ice"

    async def test_contains(self, field_expr):
        """contains"""
        cond = field_expr.contains("lic")
        assert cond.operator == "LIKE"
        assert cond.value == "%lic%"

    # -------------------------------------------------------------------------
    # 컬렉션 연산
    # -------------------------------------------------------------------------

    async def test_in_(self, field_expr):
        """IN 연산"""
        cond = field_expr.in_(["alice", "bob"])
        assert cond.operator == "IN"
        assert cond.value == ["alice", "bob"]

    async def test_not_in(self, field_expr):
        """NOT IN 연산"""
        cond = field_expr.not_in(["deleted", "banned"])
        assert cond.operator == "NOT IN"

    async def test_between(self, age_expr):
        """BETWEEN 연산"""
        cond = age_expr.between(18, 65)
        assert cond.operator == "BETWEEN"
        assert cond.value == (18, 65)

    # -------------------------------------------------------------------------
    # NULL 체크
    # -------------------------------------------------------------------------

    async def test_is_null(self, field_expr):
        """IS NULL"""
        cond = field_expr.is_null()
        assert cond.operator == "IS"
        assert cond.value is None

    async def test_is_not_null(self, field_expr):
        """IS NOT NULL"""
        cond = field_expr.is_not_null()
        assert cond.operator == "IS NOT"

    # -------------------------------------------------------------------------
    # 정렬
    # -------------------------------------------------------------------------

    async def test_asc(self, field_expr):
        """asc()"""
        order = field_expr.asc()
        assert isinstance(order, OrderBy)
        assert order.field == "name"
        assert order.direction == "ASC"

    async def test_desc(self, field_expr):
        """desc()"""
        order = field_expr.desc()
        assert order.direction == "DESC"

    # -------------------------------------------------------------------------
    # 기타
    # -------------------------------------------------------------------------

    async def test_repr(self, field_expr):
        """repr"""
        assert "name" in repr(field_expr)

    async def test_hash(self, field_expr):
        """hash"""
        assert hash(field_expr) == hash("name")


# =============================================================================
# Integration Tests
# =============================================================================


class TestExpressionsIntegration:
    """표현식 통합 테스트"""

    async def test_complex_condition_sql(self):
        """복잡한 조건 SQL 생성"""
        # (name = "alice" AND age > 18) OR (status IN ["active", "pending"])
        cond = ConditionGroup(
            "OR",
            [
                ConditionGroup(
                    "AND",
                    [
                        Condition("name", "=", "alice"),
                        Condition("age", ">", 18),
                    ],
                ),
                Condition("status", "IN", ["active", "pending"]),
            ],
        )

        sql, params = cond.to_sql()

        # SQL 구조 확인
        assert " OR " in sql
        assert " AND " in sql
        assert "IN" in sql

        # 파라미터 확인
        assert "alice" in params.values()
        assert 18 in params.values()
        assert "active" in params.values() or any(
            "active" in str(v) for v in params.values()
        )

    async def test_operator_chaining(self):
        """연산자 체이닝"""
        # 파이썬 연산자로 복잡한 조건 생성
        cond1 = Condition("a", "=", 1)
        cond2 = Condition("b", "=", 2)
        cond3 = Condition("c", "=", 3)
        cond4 = Condition("d", "=", 4)

        # (a = 1 AND b = 2) OR (c = 3 AND d = 4)
        result = (cond1 & cond2) | (cond3 & cond4)

        assert isinstance(result, ConditionGroup)
        assert result.operator == "OR"

    async def test_multiple_orders(self):
        """다중 정렬"""
        orders = [
            OrderBy("created_at", "DESC"),
            OrderBy("name", "ASC"),
        ]

        sqls = [o.to_sql() for o in orders]
        assert sqls == ["created_at DESC", "name ASC"]
