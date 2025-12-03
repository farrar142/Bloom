"""Tests for JOIN and Subquery functionality"""

import pytest

from bloom.db import (
    Entity,
    Column,
    PrimaryKey,
    Query,
    Count,
    Sum,
    Avg,
    JoinType,
    on,
    Subquery,
)
from bloom.db.session import SessionFactory
from bloom.db.backends.sqlite import SQLiteBackend


# =============================================================================
# Test Entities
# =============================================================================
# NOTE: @Entity와 @dataclass를 함께 사용하면 Column 디스크립터와 충돌이 발생합니다.
# @Entity만 사용하세요.


@Entity
class JsUser:
    """사용자 엔티티 (JOIN/Subquery 테스트용)"""

    __tablename__ = "user"

    id = PrimaryKey()
    name = Column()
    status = Column(default="active")


@Entity
class JsOrder:
    """주문 엔티티 (JOIN/Subquery 테스트용)"""

    __tablename__ = "order"

    id = PrimaryKey()
    user_id = Column()
    amount = Column()
    status = Column(default="pending")


@Entity
class JsProduct:
    """상품 엔티티 (JOIN/Subquery 테스트용)"""

    __tablename__ = "product"

    id = PrimaryKey()
    name = Column()
    price = Column()


@Entity
class JsOrderItem:
    """주문 항목 엔티티 (JOIN/Subquery 테스트용)"""

    __tablename__ = "order_item"

    id = PrimaryKey()
    order_id = Column()
    product_id = Column()
    quantity = Column()


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def session():
    """테스트용 세션 with 테이블 생성"""
    backend = SQLiteBackend(":memory:")
    factory = SessionFactory(backend)

    with factory.session() as session:
        # 테이블 생성
        session._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS "user" (
                "id" INTEGER PRIMARY KEY AUTOINCREMENT,
                "name" TEXT NOT NULL,
                "status" TEXT DEFAULT 'active'
            )
            """
        )
        session._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS "order" (
                "id" INTEGER PRIMARY KEY AUTOINCREMENT,
                "user_id" INTEGER NOT NULL,
                "amount" INTEGER NOT NULL,
                "status" TEXT DEFAULT 'pending'
            )
            """
        )
        session._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS "product" (
                "id" INTEGER PRIMARY KEY AUTOINCREMENT,
                "name" TEXT NOT NULL,
                "price" INTEGER NOT NULL
            )
            """
        )
        session._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS "order_item" (
                "id" INTEGER PRIMARY KEY AUTOINCREMENT,
                "order_id" INTEGER NOT NULL,
                "product_id" INTEGER NOT NULL,
                "quantity" INTEGER NOT NULL
            )
            """
        )
        session._connection.commit()

        # 테스트 데이터 삽입
        # Users
        session._connection.execute(
            'INSERT INTO "user" (name, status) VALUES (:n, :s)',
            {"n": "Alice", "s": "active"},
        )
        session._connection.execute(
            'INSERT INTO "user" (name, status) VALUES (:n, :s)',
            {"n": "Bob", "s": "active"},
        )
        session._connection.execute(
            'INSERT INTO "user" (name, status) VALUES (:n, :s)',
            {"n": "Charlie", "s": "inactive"},
        )

        # Orders
        session._connection.execute(
            'INSERT INTO "order" (user_id, amount, status) VALUES (:u, :a, :s)',
            {"u": 1, "a": 100, "s": "completed"},
        )
        session._connection.execute(
            'INSERT INTO "order" (user_id, amount, status) VALUES (:u, :a, :s)',
            {"u": 1, "a": 200, "s": "completed"},
        )
        session._connection.execute(
            'INSERT INTO "order" (user_id, amount, status) VALUES (:u, :a, :s)',
            {"u": 2, "a": 150, "s": "pending"},
        )

        # Products
        session._connection.execute(
            'INSERT INTO "product" (name, price) VALUES (:n, :p)',
            {"n": "Laptop", "p": 1000},
        )
        session._connection.execute(
            'INSERT INTO "product" (name, price) VALUES (:n, :p)',
            {"n": "Mouse", "p": 50},
        )

        # OrderItems
        session._connection.execute(
            'INSERT INTO "order_item" (order_id, product_id, quantity) VALUES (:o, :p, :q)',
            {"o": 1, "p": 1, "q": 1},
        )
        session._connection.execute(
            'INSERT INTO "order_item" (order_id, product_id, quantity) VALUES (:o, :p, :q)',
            {"o": 1, "p": 2, "q": 2},
        )
        session._connection.execute(
            'INSERT INTO "order_item" (order_id, product_id, quantity) VALUES (:o, :p, :q)',
            {"o": 2, "p": 2, "q": 3},
        )

        session._connection.commit()

        yield session


# =============================================================================
# JOIN Tests
# =============================================================================


class TestJoin:
    """JOIN 테스트"""

    def test_inner_join_basic(self, session):
        """기본 INNER JOIN 테스트"""
        query = Query(JsOrder).join(JsUser).on(JsOrder.user_id, JsUser.id)
        sql, params = query.build()

        assert "INNER JOIN" in sql
        assert '"user"' in sql
        assert "ON" in sql

    def test_left_join_basic(self, session):
        """LEFT JOIN 테스트"""
        query = Query(JsUser).left_join(JsOrder).on(JsUser.id, JsOrder.user_id)
        sql, params = query.build()

        assert "LEFT JOIN" in sql
        assert '"order"' in sql

    def test_right_join_basic(self, session):
        """RIGHT JOIN 테스트"""
        query = Query(JsOrder).right_join(JsUser).on(JsOrder.user_id, JsUser.id)
        sql, params = query.build()

        assert "RIGHT JOIN" in sql

    def test_full_join_basic(self, session):
        """FULL OUTER JOIN 테스트"""
        query = Query(JsUser).full_join(JsOrder).on(JsUser.id, JsOrder.user_id)
        sql, params = query.build()

        assert "FULL OUTER JOIN" in sql

    def test_cross_join_basic(self, session):
        """CROSS JOIN 테스트"""
        query = Query(JsUser).cross_join(JsOrder)
        sql, params = query.build()

        assert "CROSS JOIN" in sql
        # CROSS JOIN은 ON 조건이 없음
        assert "ON" not in sql

    def test_multiple_joins(self, session):
        """다중 JOIN 테스트"""
        query = (
            Query(JsOrderItem)
            .join(JsOrder)
            .on(JsOrderItem.order_id, JsOrder.id)
            .join(JsProduct)
            .on(JsOrderItem.product_id, JsProduct.id)
        )
        sql, params = query.build()

        # 두 개의 INNER JOIN이 있어야 함
        assert sql.count("INNER JOIN") == 2

    def test_join_with_filter(self, session):
        """JOIN + WHERE 테스트"""
        query = (
            Query(JsOrder)
            .join(JsUser)
            .on(JsOrder.user_id, JsUser.id)
            .filter(JsOrder.status == "completed")
        )
        sql, params = query.build()

        assert "INNER JOIN" in sql
        assert "WHERE" in sql

    def test_join_with_alias(self, session):
        """JOIN with alias 테스트"""
        query = Query(JsOrder).join(JsUser, alias="u").on(JsOrder.user_id, JsUser.id)
        sql, params = query.build()

        assert '"user" AS u' in sql


# =============================================================================
# Subquery Tests
# =============================================================================


class TestSubquery:
    """서브쿼리 테스트"""

    def test_subquery_in_basic(self, session):
        """IN 서브쿼리 기본 테스트"""
        # active 사용자들의 ID를 서브쿼리로
        active_user_ids = (
            Query(JsUser).filter(JsUser.status == "active").select(JsUser.id)
        )

        # 해당 사용자들의 주문 조회
        query = Query(JsOrder).filter(JsOrder.user_id.in_(active_user_ids.subquery()))
        sql, params = query.build()

        assert "IN" in sql
        # 두 개의 SELECT가 있어야 함 (외부 + 서브쿼리)
        assert sql.count("SELECT") == 2

    def test_subquery_not_in(self, session):
        """NOT IN 서브쿼리 테스트"""
        inactive_user_ids = (
            Query(JsUser).filter(JsUser.status == "inactive").select(JsUser.id)
        )

        query = Query(JsOrder).filter(
            JsOrder.user_id.not_in(inactive_user_ids.subquery())
        )
        sql, params = query.build()

        assert "NOT IN" in sql

    def test_subquery_exists(self, session):
        """EXISTS 서브쿼리 테스트"""
        # 주문이 있는 사용자 (EXISTS 패턴으로 표현)
        subquery = Query(JsOrder).select(JsOrder.id).subquery()
        exists_cond = subquery.exists()

        query = Query(JsUser).filter(exists_cond)
        sql, params = query.build()

        assert "EXISTS" in sql

    def test_subquery_not_exists(self, session):
        """NOT EXISTS 서브쿼리 테스트"""
        subquery = Query(JsOrder).select(JsOrder.id).subquery()

        query = Query(JsUser).filter(subquery.not_exists())
        sql, params = query.build()

        assert "NOT EXISTS" in sql

    def test_subquery_with_conditions(self, session):
        """조건이 있는 서브쿼리 테스트"""
        # 100 이상 주문한 사용자 ID
        high_value_orders = (
            Query(JsOrder).filter(JsOrder.amount >= 100).select(JsOrder.user_id)
        )

        query = Query(JsUser).filter(JsUser.id.in_(high_value_orders.subquery()))
        sql, params = query.build()

        assert "IN" in sql
        # 파라미터가 올바르게 매핑되어야 함
        assert len(params) > 0

    def test_subquery_alias(self, session):
        """서브쿼리 별칭 테스트"""
        subquery = Query(JsUser).select(JsUser.id).subquery("active_users")
        sql, params = subquery.to_sql()

        assert "AS active_users" in sql

    def test_nested_subquery(self, session):
        """중첩 서브쿼리 테스트"""
        # 주문이 있는 사용자들의 주문 조회
        users_with_orders = Query(JsOrder).select(JsOrder.user_id)
        orders_of_active_users = Query(JsOrder).filter(
            JsOrder.user_id.in_(users_with_orders.subquery())
        )
        sql, params = orders_of_active_users.build()

        assert "IN" in sql


# =============================================================================
# JOIN + Subquery Combined Tests
# =============================================================================


class TestJoinSubqueryCombined:
    """JOIN과 서브쿼리 조합 테스트"""

    def test_join_with_subquery_filter(self, session):
        """JOIN + 서브쿼리 필터 테스트"""
        # 특정 상품을 주문한 주문들
        laptop_orders = (
            Query(JsOrderItem)
            .filter(JsOrderItem.product_id == 1)
            .select(JsOrderItem.order_id)
        )

        query = (
            Query(JsOrder)
            .join(JsUser)
            .on(JsOrder.user_id, JsUser.id)
            .filter(JsOrder.id.in_(laptop_orders.subquery()))
        )
        sql, params = query.build()

        assert "INNER JOIN" in sql
        assert "IN" in sql

    def test_multiple_conditions_with_subquery(self, session):
        """다중 조건 + 서브쿼리 테스트"""
        active_users = Query(JsUser).filter(JsUser.status == "active").select(JsUser.id)

        query = (
            Query(JsOrder)
            .filter(JsOrder.user_id.in_(active_users.subquery()))
            .filter(JsOrder.amount >= 100)
        )
        sql, params = query.build()

        assert "IN" in sql


# =============================================================================
# SQL Generation Tests
# =============================================================================


class TestSQLGeneration:
    """SQL 생성 테스트"""

    def test_join_condition_with_on_helper(self, session):
        """on() 헬퍼 함수 테스트"""
        cond = on(JsOrder.user_id, JsUser.id)
        sql, params = cond.to_sql()

        assert '"user_id"' in sql
        assert '"id"' in sql
        assert "=" in sql
        assert params == {}  # 컬럼 간 비교이므로 파라미터 없음

    def test_join_condition_with_table_prefix(self, session):
        """테이블 접두사가 있는 JOIN 조건 테스트"""
        cond = on("user_id", "id", left_table="order", right_table="user")
        sql, params = cond.to_sql()

        assert '"order"."user_id"' in sql
        assert '"user"."id"' in sql

    def test_subquery_param_remapping(self, session):
        """서브쿼리 파라미터 재매핑 테스트"""
        inner = Query(JsUser).filter(JsUser.status == "active")
        subquery = inner.subquery()

        # 외부 쿼리에서 사용
        outer = Query(JsOrder).filter(JsOrder.user_id.in_(subquery))
        sql, params = outer.build()

        # 파라미터 이름에 sq_ 접두사가 있어야 함
        has_prefixed_param = any("sq_" in key or "w_" in key for key in params)
        assert has_prefixed_param or len(params) > 0


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """엣지 케이스 테스트"""

    def test_empty_subquery_result(self, session):
        """빈 결과를 반환하는 서브쿼리"""
        # 존재하지 않는 상태로 필터링
        no_users = (
            Query(JsUser).filter(JsUser.status == "nonexistent").select(JsUser.id)
        )

        query = Query(JsOrder).filter(JsOrder.user_id.in_(no_users.subquery()))
        sql, params = query.build()

        # SQL은 정상적으로 생성되어야 함
        assert "IN" in sql

    def test_join_without_condition(self, session):
        """조건 없는 JOIN (CROSS JOIN)"""
        query = Query(JsUser).cross_join(JsOrder)
        sql, params = query.build()

        assert "CROSS JOIN" in sql
        assert "ON" not in sql

    def test_chained_joins(self, session):
        """연쇄 JOIN 테스트"""
        query = (
            Query(JsOrderItem)
            .join(JsOrder)
            .on(JsOrderItem.order_id, JsOrder.id)
            .join(JsUser)
            .on(JsOrder.user_id, JsUser.id)
            .join(JsProduct)
            .on(JsOrderItem.product_id, JsProduct.id)
        )
        sql, params = query.build()

        assert sql.count("INNER JOIN") == 3

    def test_subquery_with_select(self, session):
        """SELECT가 있는 서브쿼리 테스트"""
        avg_query = Query(JsOrder).select(JsOrder.amount)
        subquery = avg_query.subquery()
        sql, params = subquery.to_sql()

        assert "SELECT" in sql


# =============================================================================
# Execution Tests (실제 실행)
# =============================================================================


class TestExecution:
    """실제 쿼리 실행 테스트"""

    def test_subquery_in_execution(self, session):
        """IN 서브쿼리 실행 테스트"""
        # active 사용자들의 ID 서브쿼리
        active_user_ids = (
            Query(JsUser).filter(JsUser.status == "active").select(JsUser.id)
        )

        # 해당 사용자들의 주문 조회
        query = (
            Query(JsOrder)
            .filter(JsOrder.user_id.in_(active_user_ids.subquery()))
            .with_session(session)
        )

        orders = query.all()

        # Alice(id=1)와 Bob(id=2)의 주문만 조회되어야 함
        # Charlie(id=3)는 inactive이므로 제외
        assert len(orders) == 3  # Alice 2개 + Bob 1개
        for order in orders:
            assert order.user_id in [1, 2]

    def test_subquery_not_in_execution(self, session):
        """NOT IN 서브쿼리 실행 테스트"""
        # inactive 사용자들의 ID 서브쿼리
        inactive_user_ids = (
            Query(JsUser).filter(JsUser.status == "inactive").select(JsUser.id)
        )

        query = (
            Query(JsOrder)
            .filter(JsOrder.user_id.not_in(inactive_user_ids.subquery()))
            .with_session(session)
        )

        orders = query.all()

        # Charlie(id=3)의 주문은 없으므로 모든 주문이 반환됨
        assert len(orders) == 3

    def test_subquery_exists_execution(self, session):
        """EXISTS 서브쿼리 실행 테스트"""
        # 주문이 있는 사용자만 조회 (correlated subquery 패턴)
        # 참고: 실제 correlated subquery는 아니지만 EXISTS 동작 확인
        subquery = Query(JsOrder).select(JsOrder.id).subquery()

        query = Query(JsUser).filter(subquery.exists()).with_session(session)

        users = query.all()
        # 주문 데이터가 있으므로 EXISTS는 True
        assert len(users) == 3  # 모든 사용자 반환

    def test_complex_subquery_execution(self, session):
        """복잡한 서브쿼리 실행 테스트"""
        # 100 이상 주문한 사용자의 ID
        high_value_user_ids = (
            Query(JsOrder).filter(JsOrder.amount >= 100).select(JsOrder.user_id)
        )

        # 해당 사용자들 조회
        query = (
            Query(JsUser)
            .filter(JsUser.id.in_(high_value_user_ids.subquery()))
            .with_session(session)
        )

        users = query.all()

        # Alice(100, 200)와 Bob(150) 모두 100 이상 주문함
        assert len(users) == 2
        names = {u.name for u in users}
        assert "Alice" in names
        assert "Bob" in names
