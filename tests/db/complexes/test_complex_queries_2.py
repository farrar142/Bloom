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
# 2. 조건 필터링 (11-25)
# =============================================================================


class TestConditionalFiltering:
    """조건 필터링 테스트"""

    def test_11_equal_condition(self, session):
        """Q11: 동등 조건"""
        users = (
            Query(User)
            .filter(User.department == "Engineering")
            .with_session(session)
            .all()
        )
        for user in users:
            assert user.department == "Engineering"

    def test_12_not_equal_condition(self, session):
        """Q12: 부등 조건"""
        users = (
            Query(User).filter(User.status != "inactive").with_session(session).all()
        )
        for user in users:
            assert user.status != "inactive"

    def test_13_greater_than_condition(self, session):
        """Q13: 초과 조건"""
        users = Query(User).filter(User.age > 30).with_session(session).all()
        for user in users:
            assert user.age > 30

    def test_14_greater_or_equal_condition(self, session):
        """Q14: 이상 조건"""
        users = Query(User).filter(User.salary >= 80000).with_session(session).all()
        for user in users:
            assert user.salary >= 80000

    def test_15_less_than_condition(self, session):
        """Q15: 미만 조건"""
        users = Query(User).filter(User.age < 25).with_session(session).all()
        for user in users:
            assert user.age < 25

    def test_16_less_or_equal_condition(self, session):
        """Q16: 이하 조건"""
        products = (
            Query(Product).filter(Product.price <= 50).with_session(session).all()
        )
        for product in products:
            assert product.price <= 50

    def test_17_in_list_condition(self, session):
        """Q17: IN 리스트 조건"""
        users = (
            Query(User)
            .filter(User.department.in_(["Engineering", "Sales"]))
            .with_session(session)
            .all()
        )
        for user in users:
            assert user.department in ["Engineering", "Sales"]

    def test_18_not_in_list_condition(self, session):
        """Q18: NOT IN 리스트 조건"""
        users = (
            Query(User).filter(User.role.not_in(["admin"])).with_session(session).all()
        )
        for user in users:
            assert user.role != "admin"

    def test_19_between_condition(self, session):
        """Q19: BETWEEN 조건"""
        users = Query(User).filter(User.age.between(25, 35)).with_session(session).all()
        for user in users:
            assert 25 <= user.age <= 35

    def test_20_like_condition(self, session):
        """Q20: LIKE 조건"""
        users = (
            Query(User)
            .filter(User.email.like("%@example.com"))
            .with_session(session)
            .all()
        )
        for user in users:
            assert user.email.endswith("@example.com")

    def test_21_startswith_condition(self, session):
        """Q21: STARTSWITH 조건"""
        users = (
            Query(User)
            .filter(User.name.startswith("User1"))
            .with_session(session)
            .all()
        )
        for user in users:
            assert user.name.startswith("User1")

    def test_22_endswith_condition(self, session):
        """Q22: ENDSWITH 조건"""
        products = (
            Query(Product)
            .filter(Product.name.endswith("0"))
            .with_session(session)
            .all()
        )
        for product in products:
            assert product.name.endswith("0")

    def test_23_contains_condition(self, session):
        """Q23: CONTAINS 조건"""
        reviews = (
            Query(Review)
            .filter(Review.content.contains("content"))
            .with_session(session)
            .all()
        )
        for review in reviews:
            assert "content" in review.content

    def test_24_is_null_condition(self, session):
        """Q24: IS NULL 조건"""
        users = (
            Query(User).filter(User.manager_id.is_null()).with_session(session).all()
        )
        for user in users:
            assert user.manager_id is None

    def test_25_is_not_null_condition(self, session):
        """Q25: IS NOT NULL 조건"""
        users = (
            Query(User)
            .filter(User.manager_id.is_not_null())
            .with_session(session)
            .all()
        )
        for user in users:
            assert user.manager_id is not None
