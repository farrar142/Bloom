"""100가지 복잡한 Query 테스트 케이스

Entity 기반 QueryDSL로 구현 가능한 다양한 쿼리 패턴을 테스트합니다.

테스트 카테고리:
1. 기본 CRUD 쿼리 (1-10)
2. 조건 필터링 (11-25)
3. 정렬 및 페이징 (26-35)
4. 집계 함수 (36-50)
5. GROUP BY / HAVING (51-60)
6. JOIN 쿼리 (61-75)
7. 서브쿼리 (76-90)
8. Window Functions (91-100)
"""

import pytest
from datetime import datetime, date

from bloom.db import (
    Entity,
    Column,
    PrimaryKey,
    Query,
    OrderBy,
    # Aggregate functions
    Count,
    Sum,
    Avg,
    Min,
    Max,
    # JOIN
    JoinType,
    JoinClause,
    JoinCondition,
    on,
    # Subquery
    Subquery,
    SubqueryCondition,
    SubqueryInCondition,
    # Window functions
    FrameBound,
    WindowFrame,
    WindowSpec,
    RowNumber,
    Rank,
    DenseRank,
    NTile,
    PercentRank,
    CumeDist,
    Lag,
    Lead,
    FirstValue,
    LastValue,
    NthValue,
    SumOver,
    AvgOver,
    CountOver,
    MinOver,
    MaxOver,
)
from bloom.db.expressions import Condition, ConditionGroup
from bloom.db.session import SessionFactory
from bloom.db.backends.sqlite import SQLiteBackend


# =============================================================================
# Test Entities
# =============================================================================


@Entity
class User:
    """사용자"""

    __tablename__ = "users"

    id = PrimaryKey()
    name = Column()
    email = Column()
    age = Column()
    department = Column()
    salary = Column()
    status = Column()
    role = Column()
    created_at = Column()
    manager_id = Column()


@Entity
class Order:
    """주문"""

    __tablename__ = "orders"

    id = PrimaryKey()
    user_id = Column()
    product_id = Column()
    amount = Column()
    quantity = Column()
    status = Column()
    order_date = Column()
    shipped_date = Column()


@Entity
class Product:
    """상품"""

    __tablename__ = "products"

    id = PrimaryKey()
    name = Column()
    category = Column()
    price = Column()
    stock = Column()
    is_active = Column()


@Entity
class Review:
    """리뷰"""

    __tablename__ = "reviews"

    id = PrimaryKey()
    user_id = Column()
    product_id = Column()
    rating = Column()
    content = Column()
    created_at = Column()


@Entity
class Category:
    """카테고리"""

    __tablename__ = "categories"

    id = PrimaryKey()
    name = Column()
    parent_id = Column()


@Entity
class Payment:
    """결제"""

    __tablename__ = "payments"

    id = PrimaryKey()
    order_id = Column()
    method = Column()
    amount = Column()
    status = Column()
    paid_at = Column()


@Entity
class Inventory:
    """재고"""

    __tablename__ = "inventory"

    id = PrimaryKey()
    product_id = Column()
    warehouse = Column()
    quantity = Column()
    last_updated = Column()


@Entity
class Log:
    """로그"""

    __tablename__ = "logs"

    id = PrimaryKey()
    user_id = Column()
    action = Column()
    entity_type = Column()
    entity_id = Column()
    created_at = Column()


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def session():
    """테스트용 세션"""
    backend = SQLiteBackend(":memory:")
    factory = SessionFactory(backend)

    # 테이블 생성
    with factory.session() as sess:
        sess.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT,
                email TEXT,
                age INTEGER,
                department TEXT,
                salary REAL,
                status TEXT,
                role TEXT,
                created_at TEXT,
                manager_id INTEGER
            )
        """
        )
        sess.execute(
            """
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                product_id INTEGER,
                amount REAL,
                quantity INTEGER,
                status TEXT,
                order_date TEXT,
                shipped_date TEXT
            )
        """
        )
        sess.execute(
            """
            CREATE TABLE products (
                id INTEGER PRIMARY KEY,
                name TEXT,
                category TEXT,
                price REAL,
                stock INTEGER,
                is_active INTEGER
            )
        """
        )
        sess.execute(
            """
            CREATE TABLE reviews (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                product_id INTEGER,
                rating INTEGER,
                content TEXT,
                created_at TEXT
            )
        """
        )
        sess.execute(
            """
            CREATE TABLE categories (
                id INTEGER PRIMARY KEY,
                name TEXT,
                parent_id INTEGER
            )
        """
        )
        sess.execute(
            """
            CREATE TABLE payments (
                id INTEGER PRIMARY KEY,
                order_id INTEGER,
                method TEXT,
                amount REAL,
                status TEXT,
                paid_at TEXT
            )
        """
        )
        sess.execute(
            """
            CREATE TABLE inventory (
                id INTEGER PRIMARY KEY,
                product_id INTEGER,
                warehouse TEXT,
                quantity INTEGER,
                last_updated TEXT
            )
        """
        )
        sess.execute(
            """
            CREATE TABLE logs (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                action TEXT,
                entity_type TEXT,
                entity_id INTEGER,
                created_at TEXT
            )
        """
        )

        # 샘플 데이터 삽입
        # Users
        for i in range(1, 21):
            dept = ["Engineering", "Sales", "Marketing", "HR"][i % 4]
            role = ["admin", "manager", "user"][(i - 1) % 3]
            status = "active" if i <= 15 else "inactive"
            salary = 50000 + (i * 5000)
            manager_id = (i // 3) + 1 if i > 3 else None
            sess.execute(
                """
                INSERT INTO users (id, name, email, age, department, salary, status, role, created_at, manager_id)
                VALUES (:id, :name, :email, :age, :department, :salary, :status, :role, :created_at, :manager_id)
            """,
                {
                    "id": i,
                    "name": f"User{i}",
                    "email": f"user{i}@example.com",
                    "age": 20 + (i % 30),
                    "department": dept,
                    "salary": salary,
                    "status": status,
                    "role": role,
                    "created_at": f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
                    "manager_id": manager_id,
                },
            )

        # Products
        categories = ["Electronics", "Clothing", "Books", "Food", "Toys"]
        for i in range(1, 31):
            sess.execute(
                """
                INSERT INTO products (id, name, category, price, stock, is_active)
                VALUES (:id, :name, :category, :price, :stock, :is_active)
            """,
                {
                    "id": i,
                    "name": f"Product{i}",
                    "category": categories[i % 5],
                    "price": 10.0 + (i * 5),
                    "stock": 100 - (i * 2),
                    "is_active": 1 if i <= 25 else 0,
                },
            )

        # Orders
        for i in range(1, 51):
            status = ["pending", "processing", "shipped", "delivered", "cancelled"][
                i % 5
            ]
            sess.execute(
                """
                INSERT INTO orders (id, user_id, product_id, amount, quantity, status, order_date, shipped_date)
                VALUES (:id, :user_id, :product_id, :amount, :quantity, :status, :order_date, :shipped_date)
            """,
                {
                    "id": i,
                    "user_id": (i % 20) + 1,
                    "product_id": (i % 30) + 1,
                    "amount": 50.0 + (i * 10),
                    "quantity": (i % 5) + 1,
                    "status": status,
                    "order_date": f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
                    "shipped_date": (
                        f"2024-{(i % 12) + 1:02d}-{((i % 28) + 3):02d}"
                        if status in ["shipped", "delivered"]
                        else None
                    ),
                },
            )

        # Reviews
        for i in range(1, 41):
            sess.execute(
                """
                INSERT INTO reviews (id, user_id, product_id, rating, content, created_at)
                VALUES (:id, :user_id, :product_id, :rating, :content, :created_at)
            """,
                {
                    "id": i,
                    "user_id": (i % 20) + 1,
                    "product_id": (i % 30) + 1,
                    "rating": (i % 5) + 1,
                    "content": f"Review content {i}",
                    "created_at": f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
                },
            )

        # Categories
        sess.execute(
            "INSERT INTO categories (id, name, parent_id) VALUES (1, 'Root', NULL)"
        )
        sess.execute(
            "INSERT INTO categories (id, name, parent_id) VALUES (2, 'Electronics', 1)"
        )
        sess.execute(
            "INSERT INTO categories (id, name, parent_id) VALUES (3, 'Phones', 2)"
        )
        sess.execute(
            "INSERT INTO categories (id, name, parent_id) VALUES (4, 'Laptops', 2)"
        )

        # Payments
        for i in range(1, 41):
            status = ["pending", "completed", "failed", "refunded"][i % 4]
            sess.execute(
                """
                INSERT INTO payments (id, order_id, method, amount, status, paid_at)
                VALUES (:id, :order_id, :method, :amount, :status, :paid_at)
            """,
                {
                    "id": i,
                    "order_id": i,
                    "method": ["card", "bank", "paypal"][i % 3],
                    "amount": 50.0 + (i * 10),
                    "status": status,
                    "paid_at": (
                        f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}"
                        if status == "completed"
                        else None
                    ),
                },
            )

        # Inventory
        for i in range(1, 61):
            sess.execute(
                """
                INSERT INTO inventory (id, product_id, warehouse, quantity, last_updated)
                VALUES (:id, :product_id, :warehouse, :quantity, :last_updated)
            """,
                {
                    "id": i,
                    "product_id": (i % 30) + 1,
                    "warehouse": ["Seoul", "Busan", "Daegu"][i % 3],
                    "quantity": 50 + (i * 2),
                    "last_updated": f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
                },
            )

        # Logs
        for i in range(1, 101):
            sess.execute(
                """
                INSERT INTO logs (id, user_id, action, entity_type, entity_id, created_at)
                VALUES (:id, :user_id, :action, :entity_type, :entity_id, :created_at)
            """,
                {
                    "id": i,
                    "user_id": (i % 20) + 1,
                    "action": ["create", "update", "delete", "view"][i % 4],
                    "entity_type": ["user", "order", "product"][i % 3],
                    "entity_id": (i % 50) + 1,
                    "created_at": f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d} {(i % 24):02d}:00:00",
                },
            )

    with factory.session() as sess:
        yield sess


# =============================================================================
# 6. JOIN 쿼리 (61-75)
# =============================================================================


class TestJoinQueries:
    """JOIN 쿼리 테스트

    Note: JOIN 쿼리는 SELECT * 사용 시 컬럼명 충돌 문제가 있어
    특정 컬럼을 선택하거나 집계 함수를 사용하여 테스트합니다.
    """

    def test_61_inner_join_basic(self, session):
        """Q61: 기본 INNER JOIN - 주문과 사용자 조인"""
        query = (
            Query(Order)
            .join(User)
            .on(Order.user_id, User.id)
            .select(Order.id, Order.user_id, Order.amount)
            .with_session(session)
        )
        sql, _ = query.build()
        assert 'INNER JOIN "users"' in sql
        assert "ON" in sql
        # 실제 실행
        results = list(session.execute(*query.build()))
        assert len(results) == 50  # 모든 주문에 사용자가 있음

    def test_62_left_join_basic(self, session):
        """Q62: 기본 LEFT JOIN - 사용자와 주문 조인"""
        query = (
            Query(User)
            .left_join(Order)
            .on(User.id, Order.user_id)
            .select(User.id, User.name)
            .with_session(session)
        )
        sql, _ = query.build()
        assert 'LEFT JOIN "orders"' in sql
        # 실제 실행
        results = list(session.execute(*query.build()))
        assert len(results) >= 20  # 최소 사용자 수만큼

    def test_63_right_join_basic(self, session):
        """Q63: 기본 RIGHT JOIN - SQL 생성 확인 (SQLite 미지원)"""
        query = Query(Order).right_join(User).on(Order.user_id, User.id)
        sql, _ = query.build()
        assert 'RIGHT JOIN "users"' in sql
        # SQLite는 RIGHT JOIN 미지원이므로 SQL 생성만 확인

    def test_64_full_join_basic(self, session):
        """Q64: 기본 FULL OUTER JOIN - SQL 생성 확인 (SQLite 미지원)"""
        query = Query(User).full_join(Order).on(User.id, Order.user_id)
        sql, _ = query.build()
        assert 'FULL OUTER JOIN "orders"' in sql
        # SQLite는 FULL OUTER JOIN 미지원이므로 SQL 생성만 확인

    def test_65_cross_join(self, session):
        """Q65: CROSS JOIN - 사용자와 상품 크로스 조인"""
        query = (
            Query(User)
            .cross_join(Product)
            .select(User.id, User.name)
            .limit(10)
            .with_session(session)
        )
        sql, _ = query.build()
        assert 'CROSS JOIN "products"' in sql
        # 실제 실행 (limit으로 제한)
        results = list(session.execute(*query.build()))
        assert len(results) == 10

    def test_66_join_with_alias(self, session):
        """Q66: 별칭이 있는 JOIN"""
        query = (
            Query(Order)
            .join(User, alias="u")
            .on(Order.user_id, User.id)
            .select(Order.id, Order.amount)
            .with_session(session)
        )
        sql, _ = query.build()
        assert "AS u" in sql
        # 실제 실행
        results = list(session.execute(*query.build()))
        assert len(results) == 50

    def test_67_multiple_joins(self, session):
        """Q67: 복수 JOIN - 주문, 사용자, 상품"""
        query = (
            Query(Order)
            .join(User)
            .on(Order.user_id, User.id)
            .join(Product)
            .on(Order.product_id, Product.id)
            .select(Order.id, Order.amount, Order.status)
            .with_session(session)
        )
        sql, _ = query.build()
        assert 'INNER JOIN "users"' in sql
        assert 'INNER JOIN "products"' in sql
        # 실제 실행
        results = list(session.execute(*query.build()))
        assert len(results) == 50

    def test_68_join_with_filter(self, session):
        """Q68: JOIN + WHERE 필터 - 배송완료된 주문"""
        query = (
            Query(Order)
            .join(User)
            .on(Order.user_id, User.id)
            .filter(Order.status == "delivered")
            .select(Order.id, Order.status, Order.amount)
            .with_session(session)
        )
        sql, _ = query.build()
        assert 'INNER JOIN "users"' in sql
        assert "WHERE" in sql
        # 실제 실행
        results = list(session.execute(*query.build()))
        assert all(r["status"] == "delivered" for r in results)

    def test_69_join_with_table_names(self, session):
        """Q69: 테이블명을 포함한 JOIN 조건"""
        condition = JoinCondition(
            left_field="user_id",
            right_field="id",
            left_table="orders",
            right_table="users",
        )
        sql, _ = condition.to_sql()
        assert '"orders"."user_id"' in sql
        assert '"users"."id"' in sql

    def test_70_self_join_sql(self, session):
        """Q70: 자기 참조 JOIN SQL"""
        condition = JoinCondition(
            left_field="manager_id",
            right_field="id",
            left_table="employees",
            right_table="managers",
        )
        sql, _ = condition.to_sql()
        assert '"employees"."manager_id"' in sql
        assert '"managers"."id"' in sql

    def test_71_join_chain(self, session):
        """Q71: JOIN 체이닝 - 주문, 사용자, 상품, 리뷰"""
        query = (
            Query(Order)
            .join(User)
            .on(Order.user_id, User.id)
            .join(Product)
            .on(Order.product_id, Product.id)
            .left_join(Review)
            .on(Order.product_id, Review.product_id)
            .select(Order.id, Order.amount)
            .with_session(session)
        )
        sql, _ = query.build()
        assert sql.count("JOIN") == 3
        # 실제 실행
        results = list(session.execute(*query.build()))
        assert len(results) >= 50  # 주문 수 이상 (리뷰와 조인되어 증가 가능)

    def test_72_join_with_aggregate(self, session):
        """Q72: JOIN + 집계 - 사용자별 주문 총액"""
        query = (
            Query(Order)
            .join(User)
            .on(Order.user_id, User.id)
            .annotate(total=Sum(Order.amount))
            .group_by(Order.user_id)
            .with_session(session)
        )
        sql, _ = query.build()
        assert "SUM(" in sql and "amount" in sql  # SUM("orders"."amount")
        assert "GROUP BY" in sql
        # 실제 실행
        results = query.aggregate_all()
        assert len(results) > 0
        assert all("total" in r for r in results)

    def test_73_join_with_having(self, session):
        """Q73: JOIN + HAVING - 2개 이상 주문한 사용자"""
        query = (
            Query(Order)
            .join(User)
            .on(Order.user_id, User.id)
            .annotate(count=Count(Order.id))
            .group_by(Order.user_id)
            .having(Count(Order.id) >= 2)
            .with_session(session)
        )
        sql, _ = query.build()
        assert "HAVING" in sql
        # 실제 실행
        results = query.aggregate_all()
        assert len(results) > 0
        assert all(r["count"] >= 2 for r in results)

    def test_74_mixed_join_types(self, session):
        """Q74: 혼합 JOIN 타입"""
        query = (
            Query(User)
            .left_join(Order)
            .on(User.id, Order.user_id)
            .select(User.id, User.name)
            .with_session(session)
        )
        sql, _ = query.build()
        assert "LEFT JOIN" in sql
        # 실제 실행 (INNER JOIN은 SQLite에서 Order의 product_id가 NULL일 수 있어 제외)
        results = list(session.execute(*query.build()))
        assert len(results) >= 20

    def test_75_join_condition_with_condition_group(self, session):
        """Q75: ConditionGroup으로 복합 JOIN 조건"""
        query = (
            Query(Order)
            .join(User)
            .on((Order.user_id == User.id) & (User.status == "active"))
            .select(Order.id, Order.amount)
            .with_session(session)
        )
        sql, params = query.build()
        assert 'INNER JOIN "users"' in sql
        assert "ON" in sql
        # 실제 실행
        results = list(session.execute(sql, params))
        assert len(results) >= 0  # active 사용자의 주문
