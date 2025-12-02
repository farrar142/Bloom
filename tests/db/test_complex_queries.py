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
# 1. 기본 CRUD 쿼리 (1-10)
# =============================================================================


class TestBasicCRUDQueries:
    """기본 CRUD 쿼리 테스트"""

    def test_01_select_all_users(self, session):
        """Q1: 모든 사용자 조회"""
        query = Query(User).with_session(session)
        users = query.all()
        assert len(users) == 20

    def test_02_select_by_id(self, session):
        """Q2: ID로 단일 조회"""
        query = Query(User).filter(User.id == 1).with_session(session)
        user = query.first()
        assert user is not None
        assert user.id == 1
        assert user.name == "User1"

    def test_03_select_specific_columns(self, session):
        """Q3: 특정 컬럼만 조회"""
        query = Query(User).select(User.id, User.name).with_session(session)
        sql, _ = query.build()
        assert '"id"' in sql
        assert '"name"' in sql

    def test_04_select_one_user(self, session):
        """Q4: 정확히 하나의 결과 조회"""
        query = (
            Query(User).filter(User.email == "user5@example.com").with_session(session)
        )
        user = query.one()
        assert user.id == 5

    def test_05_select_one_or_none(self, session):
        """Q5: 하나 또는 None 조회"""
        query = (
            Query(User)
            .filter(User.email == "nonexistent@example.com")
            .with_session(session)
        )
        user = query.one_or_none()
        assert user is None

    def test_06_count_users(self, session):
        """Q6: 레코드 수 조회"""
        query = Query(User).with_session(session)
        count = query.count()
        assert count == 20

    def test_07_exists_check(self, session):
        """Q7: 존재 여부 확인"""
        exists = (
            Query(User).filter(User.status == "active").with_session(session).exists()
        )
        assert exists is True

        not_exists = (
            Query(User).filter(User.status == "deleted").with_session(session).exists()
        )
        assert not_exists is False

    def test_08_update_user(self, session):
        """Q8: 레코드 업데이트"""
        updated = (
            Query(User)
            .filter(User.id == 1)
            .with_session(session)
            .update(name="UpdatedUser1")
        )
        assert updated == 1

        user = Query(User).filter(User.id == 1).with_session(session).first()
        assert user is not None
        assert user.name == "UpdatedUser1"

    def test_09_delete_user(self, session):
        """Q9: 레코드 삭제"""
        # 먼저 inactive 사용자 수 확인
        count_before = (
            Query(User).filter(User.status == "inactive").with_session(session).count()
        )

        # 삭제
        deleted = (
            Query(User).filter(User.status == "inactive").with_session(session).delete()
        )
        assert deleted == count_before

        # 삭제 확인
        count_after = (
            Query(User).filter(User.status == "inactive").with_session(session).count()
        )
        assert count_after == 0

    def test_10_filter_by_kwargs(self, session):
        """Q10: 키워드 인자로 필터링"""
        query = (
            Query(User)
            .filter_by(department="Engineering", status="active")
            .with_session(session)
        )
        users = query.all()
        for user in users:
            assert user.department == "Engineering"
            assert user.status == "active"


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


# =============================================================================
# 3. 복합 조건 및 정렬/페이징 (26-35)
# =============================================================================


class TestCompoundConditionsAndPaging:
    """복합 조건 및 정렬/페이징 테스트"""

    def test_26_and_conditions(self, session):
        """Q26: AND 복합 조건"""
        users = (
            Query(User)
            .filter((User.department == "Engineering") & (User.status == "active"))
            .with_session(session)
            .all()
        )
        for user in users:
            assert user.department == "Engineering"
            assert user.status == "active"

    def test_27_or_conditions(self, session):
        """Q27: OR 복합 조건"""
        users = (
            Query(User)
            .filter((User.role == "admin") | (User.role == "manager"))
            .with_session(session)
            .all()
        )
        for user in users:
            assert user.role in ["admin", "manager"]

    def test_28_nested_conditions(self, session):
        """Q28: 중첩 복합 조건"""
        users = (
            Query(User)
            .filter(
                (User.department == "Engineering")
                & ((User.role == "admin") | (User.role == "manager"))
            )
            .with_session(session)
            .all()
        )
        for user in users:
            assert user.department == "Engineering"
            assert user.role in ["admin", "manager"]

    def test_29_multiple_filter_calls(self, session):
        """Q29: 여러 filter 호출"""
        users = (
            Query(User)
            .filter(User.status == "active")
            .filter(User.age >= 25)
            .filter(User.salary >= 60000)
            .with_session(session)
            .all()
        )
        for user in users:
            assert user.status == "active"
            assert user.age >= 25
            assert user.salary >= 60000

    def test_30_order_by_asc(self, session):
        """Q30: 오름차순 정렬"""
        users = Query(User).order_by(User.age.asc()).with_session(session).all()
        ages = [u.age for u in users]
        assert ages == sorted(ages)

    def test_31_order_by_desc(self, session):
        """Q31: 내림차순 정렬"""
        users = Query(User).order_by(User.salary.desc()).with_session(session).all()
        salaries = [u.salary for u in users]
        assert salaries == sorted(salaries, reverse=True)

    def test_32_multiple_order_by(self, session):
        """Q32: 복수 정렬"""
        users = (
            Query(User)
            .order_by(User.department.asc(), User.salary.desc())
            .with_session(session)
            .all()
        )
        # 부서별로 그룹화 후 각 그룹 내 급여가 내림차순인지 확인
        from itertools import groupby

        for dept, group in groupby(users, key=lambda u: u.department):
            salaries = [u.salary for u in group]
            assert salaries == sorted(salaries, reverse=True)

    def test_33_limit(self, session):
        """Q33: LIMIT"""
        users = Query(User).limit(5).with_session(session).all()
        assert len(users) == 5

    def test_34_offset(self, session):
        """Q34: OFFSET (LIMIT과 함께 사용)"""
        all_users = Query(User).order_by(User.id.asc()).with_session(session).all()
        # SQLite에서는 OFFSET 사용 시 LIMIT도 필요
        offset_users = (
            Query(User)
            .order_by(User.id.asc())
            .limit(100)
            .offset(5)
            .with_session(session)
            .all()
        )

        assert offset_users[0].id == all_users[5].id

    def test_35_pagination(self, session):
        """Q35: 페이지네이션 (LIMIT + OFFSET)"""
        page_size = 5
        page_number = 2

        page = (
            Query(User)
            .order_by(User.id.asc())
            .limit(page_size)
            .offset((page_number - 1) * page_size)
            .with_session(session)
            .all()
        )
        assert len(page) == page_size
        assert page[0].id == 6  # 두 번째 페이지 첫 번째 항목


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
        assert count.to_sql() == "COUNT(id)"

        count_alias = Count(Order.id).as_("order_count")
        assert count_alias.to_sql() == "COUNT(id) AS order_count"

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
        assert "AVG(amount)" in sql

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


# =============================================================================
# 5. GROUP BY / HAVING (51-60)
# =============================================================================


class TestGroupByHaving:
    """GROUP BY / HAVING 테스트"""

    def test_51_simple_group_by(self, session):
        """Q51: 단순 GROUP BY"""
        results = (
            Query(User)
            .annotate(count=Count(User.id))
            .group_by(User.department)
            .with_session(session)
            .aggregate_all()
        )
        assert len(results) == 4  # Engineering, Sales, Marketing, HR

    def test_52_group_by_multiple_columns(self, session):
        """Q52: 복수 컬럼 GROUP BY"""
        results = (
            Query(User)
            .annotate(count=Count(User.id))
            .group_by(User.department, User.role)
            .with_session(session)
            .aggregate_all()
        )
        for r in results:
            assert "department" in r
            assert "role" in r
            assert "count" in r

    def test_53_having_greater_than(self, session):
        """Q53: HAVING > 조건"""
        results = (
            Query(Order)
            .annotate(count=Count(Order.id))
            .group_by(Order.user_id)
            .having(Count(Order.id) > 2)
            .with_session(session)
            .aggregate_all()
        )
        for r in results:
            assert r["count"] > 2

    def test_54_having_with_sum(self, session):
        """Q54: HAVING SUM 조건"""
        results = (
            Query(Order)
            .annotate(total=Sum(Order.amount))
            .group_by(Order.user_id)
            .having(Sum(Order.amount) >= 200)
            .with_session(session)
            .aggregate_all()
        )
        for r in results:
            assert r["total"] >= 200

    def test_55_having_with_avg(self, session):
        """Q55: HAVING AVG 조건"""
        results = (
            Query(Review)
            .annotate(avg_rating=Avg(Review.rating))
            .group_by(Review.product_id)
            .having(Avg(Review.rating) >= 3)
            .with_session(session)
            .aggregate_all()
        )
        for r in results:
            assert r["avg_rating"] >= 3

    def test_56_having_less_than(self, session):
        """Q56: HAVING < 조건"""
        results = (
            Query(Inventory)
            .annotate(total_qty=Sum(Inventory.quantity))
            .group_by(Inventory.product_id)
            .having(Sum(Inventory.quantity) < 200)
            .with_session(session)
            .aggregate_all()
        )
        for r in results:
            assert r["total_qty"] < 200

    def test_57_having_equal(self, session):
        """Q57: HAVING = 조건"""
        results = (
            Query(Order)
            .annotate(count=Count(Order.id))
            .group_by(Order.status)
            .having(Count(Order.id) == 10)
            .with_session(session)
            .aggregate_all()
        )
        for r in results:
            assert r["count"] == 10

    def test_58_having_compound_and(self, session):
        """Q58: HAVING 복합 AND 조건"""
        results = (
            Query(Order)
            .annotate(count=Count(Order.id), total=Sum(Order.amount))
            .group_by(Order.user_id)
            .having((Count(Order.id) >= 2) & (Sum(Order.amount) >= 100))
            .with_session(session)
            .aggregate_all()
        )
        for r in results:
            assert r["count"] >= 2
            assert r["total"] >= 100

    def test_59_having_compound_or(self, session):
        """Q59: HAVING 복합 OR 조건"""
        results = (
            Query(Order)
            .annotate(count=Count(Order.id), total=Sum(Order.amount))
            .group_by(Order.user_id)
            .having((Count(Order.id) >= 5) | (Sum(Order.amount) >= 500))
            .with_session(session)
            .aggregate_all()
        )
        for r in results:
            assert r["count"] >= 5 or r["total"] >= 500

    def test_60_group_by_with_order_by(self, session):
        """Q60: GROUP BY + ORDER BY"""
        results = (
            Query(Order)
            .annotate(count=Count(Order.id))
            .group_by(Order.status)
            .order_by(OrderBy("count", "DESC"))
            .with_session(session)
            .aggregate_all()
        )
        counts = [r["count"] for r in results]
        assert counts == sorted(counts, reverse=True)


# =============================================================================
# 6. JOIN 쿼리 (61-75)
# =============================================================================


class TestJoinQueries:
    """JOIN 쿼리 테스트"""

    def test_61_inner_join_basic(self, session):
        """Q61: 기본 INNER JOIN"""
        query = Query(Order).join(User, on(Order.user_id, User.id))
        sql, _ = query.build()
        assert 'INNER JOIN "users"' in sql
        assert "ON" in sql

    def test_62_left_join_basic(self, session):
        """Q62: 기본 LEFT JOIN"""
        query = Query(User).left_join(Order, on(User.id, Order.user_id))
        sql, _ = query.build()
        assert 'LEFT JOIN "orders"' in sql

    def test_63_right_join_basic(self, session):
        """Q63: 기본 RIGHT JOIN"""
        query = Query(Order).right_join(User, on(Order.user_id, User.id))
        sql, _ = query.build()
        assert 'RIGHT JOIN "users"' in sql

    def test_64_full_join_basic(self, session):
        """Q64: 기본 FULL OUTER JOIN"""
        query = Query(User).full_join(Order, on(User.id, Order.user_id))
        sql, _ = query.build()
        assert 'FULL OUTER JOIN "orders"' in sql

    def test_65_cross_join(self, session):
        """Q65: CROSS JOIN"""
        query = Query(User).cross_join(Product)
        sql, _ = query.build()
        assert 'CROSS JOIN "products"' in sql

    def test_66_join_with_alias(self, session):
        """Q66: 별칭이 있는 JOIN"""
        query = Query(Order).join(User, on(Order.user_id, User.id), alias="u")
        sql, _ = query.build()
        assert "AS u" in sql

    def test_67_multiple_joins(self, session):
        """Q67: 복수 JOIN"""
        query = (
            Query(Order)
            .join(User, on(Order.user_id, User.id))
            .join(Product, on(Order.product_id, Product.id))
        )
        sql, _ = query.build()
        assert 'INNER JOIN "users"' in sql
        assert 'INNER JOIN "products"' in sql

    def test_68_join_with_filter(self, session):
        """Q68: JOIN + WHERE 필터"""
        query = (
            Query(Order)
            .join(User, on(Order.user_id, User.id))
            .filter(Order.status == "delivered")
        )
        sql, _ = query.build()
        assert 'INNER JOIN "users"' in sql
        assert "WHERE" in sql

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
        # manager_id로 상사 조회
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
        """Q71: JOIN 체이닝"""
        query = (
            Query(Order)
            .join(User, on(Order.user_id, User.id))
            .join(Product, on(Order.product_id, Product.id))
            .left_join(Review, on(Order.product_id, Review.product_id))
        )
        sql, _ = query.build()
        assert sql.count("JOIN") == 3

    def test_72_join_with_aggregate(self, session):
        """Q72: JOIN + 집계"""
        query = (
            Query(Order)
            .join(User, on(Order.user_id, User.id))
            .annotate(total=Sum(Order.amount))
            .group_by(Order.user_id)
        )
        sql, _ = query.build()
        assert "SUM(amount)" in sql
        assert "GROUP BY" in sql

    def test_73_join_with_having(self, session):
        """Q73: JOIN + HAVING"""
        query = (
            Query(Order)
            .join(User, on(Order.user_id, User.id))
            .annotate(count=Count(Order.id))
            .group_by(Order.user_id)
            .having(Count(Order.id) >= 2)
        )
        sql, _ = query.build()
        assert "HAVING" in sql

    def test_74_mixed_join_types(self, session):
        """Q74: 혼합 JOIN 타입"""
        query = (
            Query(User)
            .left_join(Order, on(User.id, Order.user_id))
            .join(Product, on(Order.product_id, Product.id))
        )
        sql, _ = query.build()
        assert "LEFT JOIN" in sql
        assert "INNER JOIN" in sql

    def test_75_join_condition_with_condition_group(self, session):
        """Q75: ConditionGroup으로 복합 JOIN 조건"""
        # 복합 조건: user_id 매칭 AND status가 active
        query = Query(Order).join(
            User, (Order.user_id == User.id) & (User.status == "active")
        )
        sql, params = query.build()
        assert 'INNER JOIN "users"' in sql
        assert "ON" in sql


# =============================================================================
# 7. 서브쿼리 (76-90)
# =============================================================================


class TestSubqueries:
    """서브쿼리 테스트"""

    def test_76_in_subquery(self, session):
        """Q76: IN 서브쿼리"""
        # 활성 사용자의 주문 조회
        active_users = (
            Query(User).filter(User.status == "active").select(User.id).subquery()
        )
        query = Query(Order).filter(Order.user_id.in_(active_users))
        sql, _ = query.build()
        assert "IN (SELECT" in sql

    def test_77_not_in_subquery(self, session):
        """Q77: NOT IN 서브쿼리"""
        inactive_users = (
            Query(User).filter(User.status == "inactive").select(User.id).subquery()
        )
        query = Query(Order).filter(Order.user_id.not_in(inactive_users))
        sql, _ = query.build()
        assert "NOT IN (SELECT" in sql

    def test_78_exists_subquery(self, session):
        """Q78: EXISTS 서브쿼리"""
        has_orders = Query(Order).filter(Order.user_id == User.id).subquery().exists()
        query = Query(User).filter(has_orders)
        sql, _ = query.build()
        assert "EXISTS (SELECT" in sql

    def test_79_not_exists_subquery(self, session):
        """Q79: NOT EXISTS 서브쿼리"""
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
        """Q81: 중첩 서브쿼리"""
        inner = (
            Query(Review)
            .filter(Review.rating >= 4)
            .select(Review.product_id)
            .subquery()
        )
        outer = Query(Product).filter(Product.id.in_(inner))
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
        assert "COUNT(id)" in sql
        assert "GROUP BY" in sql
        assert "HAVING" in sql

    def test_83_scalar_subquery(self, session):
        """Q83: 스칼라 서브쿼리"""
        avg_amount = Query(Order).annotate(avg=Avg(Order.amount)).subquery().scalar()
        sql, _ = avg_amount.to_sql()
        assert "AVG(amount)" in sql

    def test_84_subquery_in_filter(self, session):
        """Q84: filter에서 서브쿼리 사용"""
        premium_products = (
            Query(Product).filter(Product.price >= 100).select(Product.id).subquery()
        )
        query = Query(Order).filter(Order.product_id.in_(premium_products))
        sql, _ = query.build()
        assert "IN (SELECT" in sql

    def test_85_correlated_subquery(self, session):
        """Q85: 상관 서브쿼리"""
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
        """Q86: JOIN 포함 서브쿼리"""
        orders_with_user = (
            Query(Order)
            .join(User, on(Order.user_id, User.id))
            .filter(User.status == "active")
            .select(Order.id)
            .subquery()
        )
        sql, _ = orders_with_user.to_sql()
        assert "JOIN" in sql

    def test_87_multiple_subqueries(self, session):
        """Q87: 복수 서브쿼리"""
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
        )
        sql, _ = query.build()
        assert sql.count("IN (SELECT") == 2

    def test_88_subquery_combined_with_exists(self, session):
        """Q88: EXISTS와 IN 서브쿼리 조합"""
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

        query = Query(Order).filter(
            (Order.user_id.in_(active_users)) & (Order.status == "delivered")
        )
        sql, _ = query.build()
        assert "IN (SELECT" in sql
        assert "AND" in sql or "status" in sql.lower()

    def test_90_subquery_or_condition(self, session):
        """Q90: 서브쿼리와 일반 조건 OR"""
        vip_users = Query(User).filter(User.role == "admin").select(User.id).subquery()

        query = Query(Order).filter(
            (Order.user_id.in_(vip_users)) | (Order.amount >= 500)
        )
        sql, _ = query.build()
        assert "OR" in sql


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
            .join(User, on(Order.user_id, User.id))
            .join(Product, on(Order.product_id, Product.id))
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
        assert "COUNT(id)" in sql
        assert "SUM(amount)" in sql
        assert "AVG(amount)" in sql
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
