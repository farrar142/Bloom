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
# 7. 서브쿼리 (76-90)
# =============================================================================


class TestSubqueries:
    """서브쿼리 테스트"""

    def test_76_in_subquery(self, session):
        """Q76: IN 서브쿼리 - 활성 사용자의 주문 조회"""
        active_users = (
            Query(User).filter(User.status == "active").select(User.id).subquery()
        )
        query = (
            Query(Order).filter(Order.user_id.in_(active_users)).with_session(session)
        )
        sql, _ = query.build()
        assert "IN (SELECT" in sql
        # 실제 실행
        results = query.all()
        assert len(results) > 0

    def test_77_not_in_subquery(self, session):
        """Q77: NOT IN 서브쿼리 - 비활성 사용자 제외"""
        inactive_users = (
            Query(User).filter(User.status == "inactive").select(User.id).subquery()
        )
        query = (
            Query(Order)
            .filter(Order.user_id.not_in(inactive_users))
            .with_session(session)
        )
        sql, _ = query.build()
        assert "NOT IN (SELECT" in sql
        # 실제 실행
        results = query.all()
        assert len(results) > 0

    def test_78_exists_subquery(self, session):
        """Q78: EXISTS 서브쿼리 - SQL 생성 확인"""
        has_orders = Query(Order).filter(Order.user_id == User.id).subquery().exists()
        query = Query(User).filter(has_orders)
        sql, _ = query.build()
        assert "EXISTS (SELECT" in sql

    def test_79_not_exists_subquery(self, session):
        """Q79: NOT EXISTS 서브쿼리 - SQL 생성 확인"""
        no_orders = (
            Query(Order).filter(Order.user_id == User.id).subquery().not_exists()
        )
        query = Query(User).filter(no_orders)
        sql, _ = query.build()
        assert "NOT EXISTS (SELECT" in sql

    def test_80_subquery_with_alias(self, session):
        """Q80: 별칭이 있는 서브쿼리"""
        subquery = (
            Query(Order)
            .filter(Order.status == "delivered")
            .select(Order.user_id)
            .subquery(alias="delivered_orders")
        )
        sql, _ = subquery.to_sql()
        assert "AS delivered_orders" in sql

    def test_81_nested_subquery(self, session):
        """Q81: 중첩 서브쿼리 - SQL 생성 확인"""
        inner = (
            Query(Review)
            .filter(Review.rating >= 4)
            .select(Review.product_id)
            .subquery()
        )
        outer = Query(Product).filter(Product.id.in_(inner)).select(Product.id)
        query = Query(Order).filter(Order.product_id.in_(outer.subquery()))
        sql, _ = query.build()
        assert sql.count("SELECT") >= 2

    def test_82_subquery_with_aggregate(self, session):
        """Q82: 집계 포함 서브쿼리"""
        high_volume_users = (
            Query(Order)
            .annotate(count=Count(Order.id))
            .group_by(Order.user_id)
            .having(Count(Order.id) >= 3)
            .select(Order.user_id)
            .subquery()
        )
        sql, _ = high_volume_users.to_sql()
        assert "COUNT(" in sql and "id" in sql  # COUNT("orders"."id")
        assert "GROUP BY" in sql
        assert "HAVING" in sql

    def test_83_scalar_subquery(self, session):
        """Q83: 스칼라 서브쿼리"""
        avg_amount = Query(Order).annotate(avg=Avg(Order.amount)).subquery().scalar()
        sql, _ = avg_amount.to_sql()
        assert "AVG(" in sql and "amount" in sql  # AVG("orders"."amount")

    def test_84_subquery_in_filter(self, session):
        """Q84: filter에서 서브쿼리 사용 - 프리미엄 상품 주문"""
        premium_products = (
            Query(Product).filter(Product.price >= 100).select(Product.id).subquery()
        )
        query = (
            Query(Order)
            .filter(Order.product_id.in_(premium_products))
            .with_session(session)
        )
        sql, _ = query.build()
        assert "IN (SELECT" in sql
        # 실제 실행
        results = query.all()
        assert isinstance(results, list)

    def test_85_correlated_subquery(self, session):
        """Q85: 상관 서브쿼리 SQL 확인"""
        # 각 사용자의 최근 주문
        latest_order = (
            Query(Order)
            .filter(Order.user_id == User.id)
            .order_by(Order.order_date.desc())
            .limit(1)
            .subquery()
        )
        sql, _ = latest_order.to_sql()
        assert "ORDER BY" in sql
        assert "LIMIT" in sql

    def test_86_subquery_with_join(self, session):
        """Q86: JOIN 포함 서브쿼리 SQL"""
        orders_with_user = (
            Query(Order)
            .join(User)
            .on(Order.user_id, User.id)
            .filter(User.status == "active")
            .select(Order.id)
            .subquery()
        )
        sql, _ = orders_with_user.to_sql()
        assert "JOIN" in sql

    def test_87_multiple_subqueries(self, session):
        """Q87: 복수 서브쿼리 - 활성 사용자의 프리미엄 상품 주문"""
        active_users = (
            Query(User).filter(User.status == "active").select(User.id).subquery()
        )
        premium_products = (
            Query(Product).filter(Product.price >= 100).select(Product.id).subquery()
        )

        query = (
            Query(Order)
            .filter(Order.user_id.in_(active_users))
            .filter(Order.product_id.in_(premium_products))
            .with_session(session)
        )
        sql, _ = query.build()
        assert sql.count("IN (SELECT") == 2
        # 실제 실행
        results = query.all()
        assert isinstance(results, list)

    def test_88_subquery_combined_with_exists(self, session):
        """Q88: EXISTS와 IN 서브쿼리 조합 - SQL 생성 확인"""
        has_review = (
            Query(Review).filter(Review.product_id == Product.id).subquery().exists()
        )
        in_stock = (
            Query(Inventory)
            .filter(Inventory.quantity > 0)
            .select(Inventory.product_id)
            .subquery()
        )

        query = Query(Product).filter(has_review).filter(Product.id.in_(in_stock))
        sql, _ = query.build()
        assert "EXISTS" in sql
        assert "IN (SELECT" in sql

    def test_89_subquery_and_condition(self, session):
        """Q89: 서브쿼리와 일반 조건 AND"""
        active_users = (
            Query(User).filter(User.status == "active").select(User.id).subquery()
        )

        query = (
            Query(Order)
            .filter((Order.user_id.in_(active_users)) & (Order.status == "delivered"))
            .with_session(session)
        )
        sql, _ = query.build()
        assert "IN (SELECT" in sql
        assert "AND" in sql or "status" in sql.lower()
        # 실제 실행
        results = query.all()
        assert all(r.status == "delivered" for r in results)

    def test_90_subquery_or_condition(self, session):
        """Q90: 서브쿼리와 일반 조건 OR"""
        vip_users = Query(User).filter(User.role == "admin").select(User.id).subquery()

        query = (
            Query(Order)
            .filter((Order.user_id.in_(vip_users)) | (Order.amount >= 500))
            .with_session(session)
        )
        sql, _ = query.build()
        assert "OR" in sql
        # 실제 실행
        results = query.all()
        assert isinstance(results, list)
