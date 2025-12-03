"""Tests for aggregate functions - Count, Sum, Avg, Min, Max, annotate, group_by, having"""

import pytest
from dataclasses import dataclass

from bloom.db import (
    Entity,
    Column,
    PrimaryKey,
    Query,
    Session,
    # Aggregate functions
    Count,
    Sum,
    Avg,
    Min,
    Max,
    HavingCondition,
)
from bloom.db.session import SessionFactory
from bloom.db.backends.sqlite import SQLiteBackend


# =============================================================================
# Test Entities
# =============================================================================


@Entity
@dataclass
class Order:
    """주문 엔티티 - 집계 테스트용"""

    id = PrimaryKey()
    user_id = Column()
    amount = Column()
    status = Column(default="pending")


@Entity
@dataclass
class Product:
    """상품 엔티티 - 집계 테스트용"""

    id = PrimaryKey()
    category = Column()
    price = Column()
    stock = Column()


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def session():
    """테스트용 세션"""
    backend = SQLiteBackend(":memory:")
    factory = SessionFactory(backend)

    with factory.session() as session:
        # 테이블 생성
        session._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS "order" (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                status TEXT DEFAULT 'pending'
            )
            """
        )
        session._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS product (
                id INTEGER PRIMARY KEY,
                category TEXT NOT NULL,
                price INTEGER NOT NULL,
                stock INTEGER NOT NULL
            )
            """
        )

        # 테스트 데이터 삽입
        session._connection.execute(
            'INSERT INTO "order" (id, user_id, amount, status) VALUES (1, 1, 100, "completed")'
        )
        session._connection.execute(
            'INSERT INTO "order" (id, user_id, amount, status) VALUES (2, 1, 200, "completed")'
        )
        session._connection.execute(
            'INSERT INTO "order" (id, user_id, amount, status) VALUES (3, 1, 150, "pending")'
        )
        session._connection.execute(
            'INSERT INTO "order" (id, user_id, amount, status) VALUES (4, 2, 300, "completed")'
        )
        session._connection.execute(
            'INSERT INTO "order" (id, user_id, amount, status) VALUES (5, 2, 250, "completed")'
        )
        session._connection.execute(
            'INSERT INTO "order" (id, user_id, amount, status) VALUES (6, 3, 500, "pending")'
        )

        session._connection.execute(
            'INSERT INTO product (id, category, price, stock) VALUES (1, "electronics", 1000, 10)'
        )
        session._connection.execute(
            'INSERT INTO product (id, category, price, stock) VALUES (2, "electronics", 500, 20)'
        )
        session._connection.execute(
            'INSERT INTO product (id, category, price, stock) VALUES (3, "clothing", 50, 100)'
        )
        session._connection.execute(
            'INSERT INTO product (id, category, price, stock) VALUES (4, "clothing", 80, 50)'
        )
        session._connection.execute(
            'INSERT INTO product (id, category, price, stock) VALUES (5, "food", 10, 200)'
        )

        yield session


# =============================================================================
# AggregateFunction 기본 테스트
# =============================================================================


class TestAggregateFunction:
    """집계 함수 클래스 테스트"""

    def test_count_to_sql(self):
        """Count.to_sql() 테스트"""
        count = Count("id")
        assert count.to_sql() == "COUNT(id)"

    def test_count_with_alias(self):
        """Count with alias"""
        count = Count("id").as_("order_count")
        assert count.to_sql() == "COUNT(id) AS order_count"
        assert count.alias == "order_count"

    def test_count_star(self):
        """COUNT(*) 테스트"""
        count = Count("*")
        assert count.to_sql() == "COUNT(*)"

    def test_sum_to_sql(self):
        """Sum.to_sql() 테스트"""
        total = Sum("amount")
        assert total.to_sql() == "SUM(amount)"

    def test_sum_with_alias(self):
        """Sum with alias"""
        total = Sum("amount").as_("total_amount")
        assert total.to_sql() == "SUM(amount) AS total_amount"

    def test_avg_to_sql(self):
        """Avg.to_sql() 테스트"""
        avg = Avg("price")
        assert avg.to_sql() == "AVG(price)"

    def test_min_to_sql(self):
        """Min.to_sql() 테스트"""
        minimum = Min("price")
        assert minimum.to_sql() == "MIN(price)"

    def test_max_to_sql(self):
        """Max.to_sql() 테스트"""
        maximum = Max("price")
        assert maximum.to_sql() == "MAX(price)"

    def test_output_name_with_alias(self):
        """output_name with alias"""
        count = Count("id").as_("cnt")
        assert count.output_name == "cnt"

    def test_output_name_without_alias(self):
        """output_name without alias (자동 생성)"""
        count = Count("id")
        assert count.output_name == "count_id"

    def test_aggregate_from_field_expression(self):
        """FieldExpression에서 집계 함수 생성"""
        count = Count(Order.id)  # type: ignore
        sql = count.to_sql()
        # FieldExpression을 사용하면 테이블명이 포함됨: COUNT("order"."id")
        assert "COUNT(" in sql and "id" in sql


# =============================================================================
# HavingCondition 테스트
# =============================================================================


class TestHavingCondition:
    """HAVING 조건 테스트"""

    def test_count_gt_condition(self):
        """COUNT > value"""
        cond = Count("id") > 5
        assert isinstance(cond, HavingCondition)
        sql, params = cond.to_sql()
        assert "COUNT(id) >" in sql
        assert 5 in params.values()

    def test_count_ge_condition(self):
        """COUNT >= value"""
        cond = Count("id") >= 5
        sql, params = cond.to_sql()
        assert "COUNT(id) >=" in sql

    def test_sum_lt_condition(self):
        """SUM < value"""
        cond = Sum("amount") < 1000
        sql, params = cond.to_sql()
        assert "SUM(amount) <" in sql
        assert 1000 in params.values()

    def test_avg_eq_condition(self):
        """AVG == value"""
        cond = Avg("price") == 100
        sql, params = cond.to_sql()
        assert "AVG(price) =" in sql

    def test_and_conditions(self):
        """AND 조건"""
        cond = (Count("id") > 5) & (Sum("amount") > 1000)
        sql, params = cond.to_sql()
        assert "AND" in sql
        assert "COUNT(id)" in sql
        assert "SUM(amount)" in sql

    def test_or_conditions(self):
        """OR 조건"""
        cond = (Count("id") > 10) | (Sum("amount") > 5000)
        sql, params = cond.to_sql()
        assert "OR" in sql


# =============================================================================
# Query.annotate() 테스트
# =============================================================================


class TestQueryAnnotate:
    """Query.annotate() 테스트"""

    def test_annotate_count(self, session):
        """단일 COUNT 집계"""
        results = (
            Query(Order)
            .annotate(order_count=Count(Order.id))  # type: ignore
            .group_by(Order.user_id)  # type: ignore
            .with_session(session)
            .aggregate_all()
        )

        assert len(results) == 3  # 3명의 user
        # user_id별 주문 수 확인
        by_user = {r["user_id"]: r["order_count"] for r in results}
        assert by_user[1] == 3  # user 1: 3개 주문
        assert by_user[2] == 2  # user 2: 2개 주문
        assert by_user[3] == 1  # user 3: 1개 주문

    def test_annotate_sum(self, session):
        """SUM 집계"""
        results = (
            Query(Order)
            .annotate(total_amount=Sum(Order.amount))  # type: ignore
            .group_by(Order.user_id)  # type: ignore
            .with_session(session)
            .aggregate_all()
        )

        by_user = {r["user_id"]: r["total_amount"] for r in results}
        assert by_user[1] == 450  # 100 + 200 + 150
        assert by_user[2] == 550  # 300 + 250
        assert by_user[3] == 500  # 500

    def test_annotate_multiple_aggregates(self, session):
        """복수 집계 함수"""
        results = (
            Query(Order)
            .annotate(
                order_count=Count(Order.id),  # type: ignore
                total_amount=Sum(Order.amount),  # type: ignore
                avg_amount=Avg(Order.amount),  # type: ignore
            )
            .group_by(Order.user_id)  # type: ignore
            .with_session(session)
            .aggregate_all()
        )

        assert len(results) == 3
        user1 = next(r for r in results if r["user_id"] == 1)
        assert user1["order_count"] == 3
        assert user1["total_amount"] == 450
        assert user1["avg_amount"] == 150  # 450 / 3

    def test_annotate_min_max(self, session):
        """MIN/MAX 집계"""
        results = (
            Query(Product)
            .annotate(
                min_price=Min(Product.price),  # type: ignore
                max_price=Max(Product.price),  # type: ignore
            )
            .group_by(Product.category)  # type: ignore
            .with_session(session)
            .aggregate_all()
        )

        by_cat = {r["category"]: r for r in results}
        assert by_cat["electronics"]["min_price"] == 500
        assert by_cat["electronics"]["max_price"] == 1000
        assert by_cat["clothing"]["min_price"] == 50
        assert by_cat["clothing"]["max_price"] == 80


# =============================================================================
# Query.group_by() 테스트
# =============================================================================


class TestQueryGroupBy:
    """Query.group_by() 테스트"""

    def test_group_by_single_column(self, session):
        """단일 컬럼 GROUP BY"""
        results = (
            Query(Order)
            .annotate(cnt=Count("*"))
            .group_by(Order.status)  # type: ignore
            .with_session(session)
            .aggregate_all()
        )

        by_status = {r["status"]: r["cnt"] for r in results}
        assert by_status["completed"] == 4
        assert by_status["pending"] == 2

    def test_group_by_multiple_columns(self, session):
        """복수 컬럼 GROUP BY"""
        results = (
            Query(Order)
            .annotate(cnt=Count("*"))
            .group_by(Order.user_id, Order.status)  # type: ignore
            .with_session(session)
            .aggregate_all()
        )

        # user_id=1: completed=2, pending=1
        # user_id=2: completed=2
        # user_id=3: pending=1
        assert len(results) == 4

    def test_group_by_with_string_column(self, session):
        """문자열로 컬럼 지정"""
        results = (
            Query(Product)
            .annotate(total_stock=Sum("stock"))
            .group_by("category")
            .with_session(session)
            .aggregate_all()
        )

        by_cat = {r["category"]: r["total_stock"] for r in results}
        assert by_cat["electronics"] == 30
        assert by_cat["clothing"] == 150
        assert by_cat["food"] == 200


# =============================================================================
# Query.having() 테스트
# =============================================================================


class TestQueryHaving:
    """Query.having() 테스트"""

    def test_having_count_gt(self, session):
        """HAVING COUNT > value"""
        results = (
            Query(Order)
            .annotate(order_count=Count(Order.id))  # type: ignore
            .group_by(Order.user_id)  # type: ignore
            .having(Count(Order.id) > 1)  # type: ignore
            .with_session(session)
            .aggregate_all()
        )

        # user_id=1 (3개), user_id=2 (2개) 만 포함
        assert len(results) == 2
        user_ids = {r["user_id"] for r in results}
        assert user_ids == {1, 2}

    def test_having_sum_ge(self, session):
        """HAVING SUM >= value"""
        results = (
            Query(Order)
            .annotate(total=Sum(Order.amount))  # type: ignore
            .group_by(Order.user_id)  # type: ignore
            .having(Sum(Order.amount) >= 500)  # type: ignore
            .with_session(session)
            .aggregate_all()
        )

        # user_id=2 (550), user_id=3 (500) 만 포함
        assert len(results) == 2
        user_ids = {r["user_id"] for r in results}
        assert user_ids == {2, 3}

    def test_having_combined_with_where(self, session):
        """WHERE + HAVING 조합"""
        results = (
            Query(Order)
            .filter(Order.status == "completed")  # type: ignore
            .annotate(total=Sum(Order.amount))  # type: ignore
            .group_by(Order.user_id)  # type: ignore
            .having(Sum(Order.amount) >= 300)  # type: ignore
            .with_session(session)
            .aggregate_all()
        )

        # completed 주문만:
        # user_id=1: 100+200=300 ✓
        # user_id=2: 300+250=550 ✓
        assert len(results) == 2


# =============================================================================
# Query.build() SQL 생성 테스트
# =============================================================================


class TestQueryBuild:
    """Query.build() SQL 생성 테스트"""

    def test_build_simple_aggregate(self):
        """단순 집계 SQL"""
        sql, params = Query(Order).annotate(cnt=Count("*")).group_by("user_id").build()

        assert 'SELECT "user_id", COUNT(*)' in sql
        assert "GROUP BY" in sql
        assert '"user_id"' in sql

    def test_build_with_having(self):
        """HAVING 포함 SQL"""
        sql, params = (
            Query(Order)
            .annotate(cnt=Count("id"))
            .group_by("user_id")
            .having(Count("id") > 5)
            .build()
        )

        assert "GROUP BY" in sql
        assert "HAVING" in sql
        assert "COUNT(id)" in sql

    def test_build_with_order_by(self):
        """ORDER BY 포함"""
        sql, params = (
            Query(Order)
            .annotate(cnt=Count("*"))
            .group_by("user_id")
            .order_by(Order.user_id.asc())  # type: ignore
            .build()
        )

        assert "GROUP BY" in sql
        assert "ORDER BY" in sql

    def test_build_with_limit(self):
        """LIMIT 포함"""
        sql, params = (
            Query(Order).annotate(cnt=Count("*")).group_by("user_id").limit(5).build()
        )

        assert "LIMIT 5" in sql


# =============================================================================
# aggregate_first() 테스트
# =============================================================================


class TestAggregateFirst:
    """aggregate_first() 테스트"""

    def test_aggregate_first(self, session):
        """첫 번째 집계 결과"""
        result = (
            Query(Order)
            .annotate(total=Sum(Order.amount))  # type: ignore
            .group_by(Order.user_id)  # type: ignore
            .order_by(Order.user_id.asc())  # type: ignore
            .with_session(session)
            .aggregate_first()
        )

        assert result is not None
        assert result["user_id"] == 1
        assert result["total"] == 450

    def test_aggregate_first_empty(self, session):
        """빈 결과"""
        result = (
            Query(Order)
            .filter(Order.user_id == 999)  # type: ignore
            .annotate(total=Sum(Order.amount))  # type: ignore
            .group_by(Order.user_id)  # type: ignore
            .with_session(session)
            .aggregate_first()
        )

        assert result is None


# =============================================================================
# 비동기 테스트
# =============================================================================


@pytest.fixture
async def async_session():
    """비동기 테스트용 세션"""
    backend = SQLiteBackend(":memory:")
    factory = SessionFactory(backend)

    session = await factory.create_async()

    try:
        # 테이블 생성
        await session._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS "order" (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                status TEXT DEFAULT 'pending'
            )
            """
        )

        # 테스트 데이터 삽입
        await session._connection.execute(
            'INSERT INTO "order" (id, user_id, amount, status) VALUES (1, 1, 100, "completed")'
        )
        await session._connection.execute(
            'INSERT INTO "order" (id, user_id, amount, status) VALUES (2, 1, 200, "completed")'
        )
        await session._connection.execute(
            'INSERT INTO "order" (id, user_id, amount, status) VALUES (3, 2, 300, "completed")'
        )

        yield session
    finally:
        # :memory: DB의 경우 release_async가 연결을 닫지 않으므로 직접 닫기
        await session._connection.raw.close()


@pytest.mark.asyncio
class TestAsyncAggregate:
    """비동기 집계 테스트"""

    async def test_async_aggregate_all(self, async_session):
        """async_aggregate_all() 테스트"""
        results = await (
            Query(Order)
            .annotate(cnt=Count(Order.id))
            .group_by(Order.user_id)
            .with_session(async_session)
            .async_aggregate_all()
        )

        assert len(results) == 2
        by_user = {r["user_id"]: r["cnt"] for r in results}
        assert by_user[1] == 2
        assert by_user[2] == 1

    async def test_async_aggregate_first(self, async_session):
        """async_aggregate_first() 테스트"""
        result = await (
            Query(Order)
            .annotate(total=Sum(Order.amount))
            .group_by(Order.user_id)
            .order_by(Order.user_id.asc())
            .with_session(async_session)
            .async_aggregate_first()
        )

        assert result is not None
        assert result["user_id"] == 1
        assert result["total"] == 300
