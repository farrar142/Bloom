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
# 8. Window Functions (91-100)
# =============================================================================


class TestWindowFunctionsComplex:
    """Window Functions 복잡한 테스트"""

    def test_91_row_number_partition(self, session):
        """Q91: ROW_NUMBER with PARTITION"""
        wf = (
            RowNumber()
            .over(
                partition_by=[Order.user_id],
                order_by=[Order.order_date.desc()],
            )
            .as_("rn")
        )
        sql = wf.to_sql()
        assert "ROW_NUMBER()" in sql
        assert 'PARTITION BY "user_id"' in sql
        assert "ORDER BY order_date DESC" in sql
        assert "AS rn" in sql

    def test_92_rank_vs_dense_rank(self, session):
        """Q92: RANK vs DENSE_RANK 비교"""
        rank = Rank().over(order_by=[User.salary.desc()]).as_("rank")
        dense = DenseRank().over(order_by=[User.salary.desc()]).as_("dense_rank")

        assert "RANK()" in rank.to_sql()
        assert "DENSE_RANK()" in dense.to_sql()

    def test_93_running_total(self, session):
        """Q93: 누적 합계 (Running Total)"""
        running_total = (
            SumOver(Order.amount)
            .over(
                partition_by=[Order.user_id],
                order_by=[Order.order_date.asc()],
                frame=WindowFrame(
                    "ROWS", FrameBound.UNBOUNDED_PRECEDING, FrameBound.CURRENT_ROW
                ),
            )
            .as_("running_total")
        )
        sql = running_total.to_sql()
        assert "SUM(amount)" in sql
        assert "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW" in sql

    def test_94_moving_average(self, session):
        """Q94: 이동 평균 (Moving Average)"""
        ma3 = (
            AvgOver(Order.amount)
            .over(
                order_by=[Order.order_date.asc()],
                frame=WindowFrame(
                    "ROWS", FrameBound.preceding(2), FrameBound.CURRENT_ROW
                ),
            )
            .as_("ma3")
        )
        sql = ma3.to_sql()
        assert "AVG(amount)" in sql
        assert "ROWS BETWEEN 2 PRECEDING AND CURRENT ROW" in sql

    def test_95_lag_lead_comparison(self, session):
        """Q95: LAG/LEAD로 전후 비교"""
        prev_amount = (
            Lag(Order.amount, 1, 0).over(order_by=[Order.order_date.asc()]).as_("prev")
        )
        next_amount = (
            Lead(Order.amount, 1, 0).over(order_by=[Order.order_date.asc()]).as_("next")
        )

        assert "LAG(amount, 1, 0)" in prev_amount.to_sql()
        assert "LEAD(amount, 1, 0)" in next_amount.to_sql()

    def test_96_ntile_quartiles(self, session):
        """Q96: NTILE로 분위수"""
        quartile = NTile(4).over(order_by=[User.salary.desc()]).as_("quartile")
        decile = NTile(10).over(order_by=[User.salary.desc()]).as_("decile")

        assert "NTILE(4)" in quartile.to_sql()
        assert "NTILE(10)" in decile.to_sql()

    def test_97_first_last_value(self, session):
        """Q97: FIRST_VALUE/LAST_VALUE"""
        first = (
            FirstValue(Order.amount)
            .over(
                partition_by=[Order.user_id],
                order_by=[Order.order_date.asc()],
            )
            .as_("first_order_amount")
        )
        last = (
            LastValue(Order.amount)
            .over(
                partition_by=[Order.user_id],
                order_by=[Order.order_date.asc()],
                frame=WindowFrame(
                    "ROWS",
                    FrameBound.UNBOUNDED_PRECEDING,
                    FrameBound.UNBOUNDED_FOLLOWING,
                ),
            )
            .as_("last_order_amount")
        )
        assert "FIRST_VALUE(amount)" in first.to_sql()
        assert "LAST_VALUE(amount)" in last.to_sql()

    def test_98_percent_rank_cume_dist(self, session):
        """Q98: PERCENT_RANK/CUME_DIST"""
        pct = PercentRank().over(order_by=[User.salary.desc()]).as_("pct_rank")
        cume = CumeDist().over(order_by=[User.salary.desc()]).as_("cume_dist")

        assert "PERCENT_RANK()" in pct.to_sql()
        assert "CUME_DIST()" in cume.to_sql()

    def test_99_multiple_window_functions(self, session):
        """Q99: 복수 윈도우 함수"""
        rn = (
            RowNumber()
            .over(partition_by=[Order.user_id], order_by=[Order.amount.desc()])
            .as_("rn")
        )
        total = (
            SumOver(Order.amount).over(partition_by=[Order.user_id]).as_("user_total")
        )
        avg = AvgOver(Order.amount).over(partition_by=[Order.user_id]).as_("user_avg")

        rn_sql = rn.to_sql()
        total_sql = total.to_sql()
        avg_sql = avg.to_sql()

        assert "ROW_NUMBER()" in rn_sql
        assert "SUM(amount)" in total_sql
        assert "AVG(amount)" in avg_sql

    def test_100_complex_analytics_query(self, session):
        """Q100: 복잡한 분석 쿼리 (모든 기능 조합)"""
        # 복잡한 분석 쿼리 구성:
        # - 집계, GROUP BY, HAVING
        # - JOIN
        # - 서브쿼리
        # - Window Function

        # 1. 서브쿼리: 활성 사용자
        active_users = (
            Query(User).filter(User.status == "active").select(User.id).subquery()
        )

        # 2. 메인 쿼리: 주문 집계
        query = (
            Query(Order)
            .join(User)
            .on(Order.user_id, User.id)
            .join(Product)
            .on(Order.product_id, Product.id)
            .filter(Order.user_id.in_(active_users))
            .filter(Order.status.in_(["delivered", "shipped"]))
            .annotate(
                order_count=Count(Order.id),
                total_amount=Sum(Order.amount),
                avg_amount=Avg(Order.amount),
            )
            .group_by(Order.user_id, Order.status)
            .having((Count(Order.id) >= 1) & (Sum(Order.amount) >= 50))
            .order_by(OrderBy("total_amount", "DESC"))
            .limit(10)
        )

        sql, params = query.build()

        # SQL 검증
        assert "SELECT" in sql
        assert 'FROM "orders"' in sql
        assert 'INNER JOIN "users"' in sql
        assert 'INNER JOIN "products"' in sql
        assert "IN (SELECT" in sql  # 서브쿼리
        assert "COUNT(" in sql and "id" in sql  # COUNT("orders"."id")
        assert "SUM(" in sql and "amount" in sql  # SUM("orders"."amount")
        assert "AVG(" in sql  # AVG("orders"."amount")
        assert "GROUP BY" in sql
        assert "HAVING" in sql
        assert "ORDER BY" in sql
        assert "LIMIT" in sql

        # 윈도우 함수 SQL 생성
        rank = (
            Rank()
            .over(partition_by=[Order.user_id], order_by=[Order.amount.desc()])
            .as_("amount_rank")
        )
        running_total = (
            SumOver(Order.amount)
            .over(partition_by=[Order.user_id], order_by=[Order.order_date.asc()])
            .as_("running_total")
        )

        rank_sql = rank.to_sql()
        running_sql = running_total.to_sql()

        assert "RANK()" in rank_sql
        assert 'PARTITION BY "user_id"' in rank_sql
        assert "SUM(amount)" in running_sql
