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
# 4. 집계 함수 (36-50)
# =============================================================================


class TestAggregateFunctions:
    """집계 함수 테스트"""

    def test_36_count_aggregate(self, session):
        """Q36: COUNT 집계"""
        result = (
            Query(Order)
            .annotate(total=Count(Order.id))
            .with_session(session)
            .aggregate_first()
        )
        assert result is not None
        assert result["total"] == 50

    def test_37_sum_aggregate(self, session):
        """Q37: SUM 집계"""
        result = (
            Query(Order)
            .annotate(total_amount=Sum(Order.amount))
            .with_session(session)
            .aggregate_first()
        )
        assert result is not None
        assert result["total_amount"] > 0

    def test_38_avg_aggregate(self, session):
        """Q38: AVG 집계"""
        result = (
            Query(Order)
            .annotate(avg_amount=Avg(Order.amount))
            .with_session(session)
            .aggregate_first()
        )
        assert result is not None
        assert result["avg_amount"] > 0

    def test_39_min_aggregate(self, session):
        """Q39: MIN 집계"""
        result = (
            Query(Product)
            .annotate(min_price=Min(Product.price))
            .with_session(session)
            .aggregate_first()
        )
        assert result is not None
        assert result["min_price"] == 15.0  # 10 + (1 * 5)

    def test_40_max_aggregate(self, session):
        """Q40: MAX 집계"""
        result = (
            Query(Product)
            .annotate(max_price=Max(Product.price))
            .with_session(session)
            .aggregate_first()
        )
        assert result is not None
        assert result["max_price"] == 160.0  # 10 + (30 * 5)

    def test_41_multiple_aggregates(self, session):
        """Q41: 복수 집계"""
        result = (
            Query(Order)
            .annotate(
                count=Count(Order.id),
                total=Sum(Order.amount),
                avg=Avg(Order.amount),
                min_amt=Min(Order.amount),
                max_amt=Max(Order.amount),
            )
            .with_session(session)
            .aggregate_first()
        )
        assert result is not None
        assert "count" in result
        assert "total" in result
        assert "avg" in result
        assert "min_amt" in result
        assert "max_amt" in result

    def test_42_count_star(self, session):
        """Q42: COUNT(*) 집계"""
        result = (
            Query(User)
            .annotate(total=Count("*"))
            .with_session(session)
            .aggregate_first()
        )
        assert result is not None
        assert result["total"] == 20

    def test_43_aggregate_with_filter(self, session):
        """Q43: 필터링 후 집계"""
        result = (
            Query(Order)
            .filter(Order.status == "delivered")
            .annotate(count=Count(Order.id), total=Sum(Order.amount))
            .with_session(session)
            .aggregate_first()
        )
        assert result is not None
        assert result["count"] > 0

    def test_44_aggregate_with_alias(self, session):
        """Q44: 별칭이 있는 집계"""
        result = (
            Query(Product)
            .annotate(product_count=Count(Product.id).as_("total_products"))
            .with_session(session)
            .aggregate_first()
        )
        assert result is not None
        assert "total_products" in result

    def test_45_aggregate_expression_sql(self, session):
        """Q45: 집계 함수 SQL 생성 확인"""
        count = Count(Order.id)
        sql = count.to_sql()
        assert "COUNT(" in sql and "id" in sql  # COUNT("orders"."id")

        count_alias = Count(Order.id).as_("order_count")
        sql_alias = count_alias.to_sql()
        assert "COUNT(" in sql_alias and "order_count" in sql_alias

    def test_46_sum_by_category(self, session):
        """Q46: 카테고리별 합계"""
        results = (
            Query(Product)
            .annotate(total_price=Sum(Product.price))
            .group_by(Product.category)
            .with_session(session)
            .aggregate_all()
        )
        assert len(results) > 0
        for r in results:
            assert "category" in r
            assert "total_price" in r

    def test_47_avg_by_department(self, session):
        """Q47: 부서별 평균"""
        results = (
            Query(User)
            .annotate(avg_salary=Avg(User.salary))
            .group_by(User.department)
            .with_session(session)
            .aggregate_all()
        )
        for r in results:
            assert r["avg_salary"] > 0

    def test_48_count_distinct_simulation(self, session):
        """Q48: 고유값 카운트 (GROUP BY로 시뮬레이션)"""
        # 주문한 사용자 수 (user_id 기준)
        results = (
            Query(Order)
            .annotate(order_count=Count(Order.id))
            .group_by(Order.user_id)
            .with_session(session)
            .aggregate_all()
        )
        unique_users = len(results)
        assert unique_users > 0

    def test_49_aggregate_in_subquery_sql(self, session):
        """Q49: 서브쿼리에서 집계 SQL 생성"""
        subquery = Query(Order).annotate(avg_amount=Avg(Order.amount)).subquery()
        sql, _ = subquery.to_sql()
        assert "AVG(" in sql and "amount" in sql  # AVG("orders"."amount")

    def test_50_mixed_aggregates_and_columns(self, session):
        """Q50: 집계와 컬럼 혼합"""
        results = (
            Query(Order)
            .annotate(
                order_count=Count(Order.id),
                total_amount=Sum(Order.amount),
            )
            .group_by(Order.user_id, Order.status)
            .with_session(session)
            .aggregate_all()
        )
        for r in results:
            assert "user_id" in r
            assert "status" in r
            assert "order_count" in r
            assert "total_amount" in r
