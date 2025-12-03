"""Complex Query Tests - Common fixtures and entities

난이도별 쿼리 테스트를 위한 공통 fixture 및 엔티티 정의
"""

import pytest
from typing import AsyncGenerator
from datetime import datetime, timedelta
from decimal import Decimal

from bloom.db import (
    Entity,
    Column,
    PrimaryKey,
    StringColumn,
    IntegerColumn,
    BooleanColumn,
    DecimalColumn,
    DateTimeColumn,
    ManyToOne,
    OneToMany,
    FetchType,
)
from bloom.db.backends.sqlite import SQLiteBackend
from bloom.db.session import SessionFactory, AsyncSession


# =============================================================================
# Test Entities - 복잡한 쿼리 테스트를 위한 엔티티
# =============================================================================


@Entity
class Department:
    """부서 엔티티"""

    id = PrimaryKey[int](auto_increment=True)
    name = StringColumn(nullable=False)
    code = StringColumn(nullable=False, unique=True)
    budget = IntegerColumn(default=0)
    is_active = BooleanColumn(default=True)

    employees = OneToMany["Employee"](
        target="Employee",
        foreign_key="department_id",
        fetch=FetchType.LAZY,
    )


@Entity
class Employee:
    """직원 엔티티"""

    id = PrimaryKey[int](auto_increment=True)
    name = StringColumn(nullable=False)
    email = StringColumn(nullable=False, unique=True)
    salary = IntegerColumn(default=0)
    hire_date = StringColumn(nullable=True)  # YYYY-MM-DD 형식
    is_manager = BooleanColumn(default=False)
    age = IntegerColumn(default=30)
    performance_score = IntegerColumn(default=50)  # 0-100

    department_id = IntegerColumn(nullable=True)
    department = ManyToOne["Department"](
        target=Department,
        foreign_key="department_id",
        fetch=FetchType.LAZY,
    )

    manager_id = IntegerColumn(nullable=True)  # 자기 참조


@Entity
class Product:
    """상품 엔티티"""

    id = PrimaryKey[int](auto_increment=True)
    name = StringColumn(nullable=False)
    category = StringColumn(nullable=False)
    price = IntegerColumn(default=0)
    stock = IntegerColumn(default=0)
    is_available = BooleanColumn(default=True)
    rating = IntegerColumn(default=0)  # 0-5 (정수로 저장)


@Entity
class Customer:
    """고객 엔티티"""

    id = PrimaryKey[int](auto_increment=True)
    name = StringColumn(nullable=False)
    email = StringColumn(nullable=False, unique=True)
    tier = StringColumn(default="bronze")  # bronze, silver, gold, platinum
    total_spent = IntegerColumn(default=0)
    signup_date = StringColumn(nullable=True)
    is_vip = BooleanColumn(default=False)


@Entity
class Order:
    """주문 엔티티"""

    id = PrimaryKey[int](auto_increment=True)
    order_date = StringColumn(nullable=False)
    status = StringColumn(default="pending")  # pending, confirmed, shipped, delivered
    total_amount = IntegerColumn(default=0)
    discount = IntegerColumn(default=0)

    customer_id = IntegerColumn(nullable=False)
    customer = ManyToOne["Customer"](
        target=Customer,
        foreign_key="customer_id",
        fetch=FetchType.LAZY,
    )


@Entity
class OrderItem:
    """주문 항목 엔티티"""

    id = PrimaryKey[int](auto_increment=True)
    quantity = IntegerColumn(default=1)
    unit_price = IntegerColumn(default=0)

    order_id = IntegerColumn(nullable=False)
    order = ManyToOne["Order"](
        target=Order,
        foreign_key="order_id",
        fetch=FetchType.LAZY,
    )

    product_id = IntegerColumn(nullable=False)
    product = ManyToOne["Product"](
        target=Product,
        foreign_key="product_id",
        fetch=FetchType.LAZY,
    )


@Entity
class SalesRecord:
    """판매 기록 (시계열 데이터)"""

    id = PrimaryKey[int](auto_increment=True)
    sale_date = StringColumn(nullable=False)
    amount = IntegerColumn(default=0)
    region = StringColumn(nullable=False)
    salesperson_id = IntegerColumn(nullable=True)


@Entity
class Score:
    """점수 테이블 (랭킹 테스트용)"""

    id = PrimaryKey[int](auto_increment=True)
    player_name = StringColumn(nullable=False)
    game = StringColumn(nullable=False)
    points = IntegerColumn(default=0)
    play_date = StringColumn(nullable=True)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sqlite_backend() -> SQLiteBackend:
    """SQLite 메모리 백엔드"""
    return SQLiteBackend(":memory:")


@pytest.fixture
def session_factory(sqlite_backend: SQLiteBackend) -> SessionFactory:
    """세션 팩토리"""
    return SessionFactory(sqlite_backend)


@pytest.fixture
async def async_session(
    session_factory: SessionFactory,
) -> AsyncGenerator[AsyncSession, None]:
    """비동기 세션 (테이블 자동 생성 포함)"""
    session = await session_factory.create_async()
    try:
        await _create_tables(session)
        yield session
    finally:
        try:
            await session.rollback()
        except Exception:
            pass
        try:
            await session._connection.close()
        except Exception:
            pass


async def _create_tables(session: AsyncSession) -> None:
    """테스트용 테이블 생성"""

    # Department
    await session._connection.execute(
        """
        CREATE TABLE IF NOT EXISTS department (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT NOT NULL UNIQUE,
            budget INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        )
        """
    )

    # Employee
    await session._connection.execute(
        """
        CREATE TABLE IF NOT EXISTS employee (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            salary INTEGER DEFAULT 0,
            hire_date TEXT,
            is_manager INTEGER DEFAULT 0,
            age INTEGER DEFAULT 30,
            performance_score INTEGER DEFAULT 50,
            department_id INTEGER,
            manager_id INTEGER,
            FOREIGN KEY (department_id) REFERENCES department(id),
            FOREIGN KEY (manager_id) REFERENCES employee(id)
        )
        """
    )

    # Product
    await session._connection.execute(
        """
        CREATE TABLE IF NOT EXISTS product (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price INTEGER DEFAULT 0,
            stock INTEGER DEFAULT 0,
            is_available INTEGER DEFAULT 1,
            rating INTEGER DEFAULT 0
        )
        """
    )

    # Customer
    await session._connection.execute(
        """
        CREATE TABLE IF NOT EXISTS customer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            tier TEXT DEFAULT 'bronze',
            total_spent INTEGER DEFAULT 0,
            signup_date TEXT,
            is_vip INTEGER DEFAULT 0
        )
        """
    )

    # Order
    await session._connection.execute(
        """
        CREATE TABLE IF NOT EXISTS "order" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_date TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            total_amount INTEGER DEFAULT 0,
            discount INTEGER DEFAULT 0,
            customer_id INTEGER NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customer(id)
        )
        """
    )

    # OrderItem
    await session._connection.execute(
        """
        CREATE TABLE IF NOT EXISTS orderitem (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quantity INTEGER DEFAULT 1,
            unit_price INTEGER DEFAULT 0,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            FOREIGN KEY (order_id) REFERENCES "order"(id),
            FOREIGN KEY (product_id) REFERENCES product(id)
        )
        """
    )

    # SalesRecord
    await session._connection.execute(
        """
        CREATE TABLE IF NOT EXISTS salesrecord (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_date TEXT NOT NULL,
            amount INTEGER DEFAULT 0,
            region TEXT NOT NULL,
            salesperson_id INTEGER
        )
        """
    )

    # Score
    await session._connection.execute(
        """
        CREATE TABLE IF NOT EXISTS score (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name TEXT NOT NULL,
            game TEXT NOT NULL,
            points INTEGER DEFAULT 0,
            play_date TEXT
        )
        """
    )

    await session.commit()


# =============================================================================
# Data Seeding Fixtures
# =============================================================================


@pytest.fixture
async def seeded_session(async_session: AsyncSession) -> AsyncSession:
    """샘플 데이터가 미리 삽입된 세션"""
    await _seed_departments(async_session)
    await async_session.commit()  # Department FK 의존성 해결
    
    await _seed_employees(async_session)
    await async_session.commit()  # Employee FK 의존성 해결
    
    await _seed_products(async_session)
    await async_session.commit()  # Product FK 의존성 해결
    
    await _seed_customers(async_session)
    await async_session.commit()  # Customer FK 의존성 해결
    
    await _seed_orders(async_session)
    # _seed_orders 내부에서 order commit 후 order_items 추가
    
    await _seed_sales_records(async_session)
    await _seed_scores(async_session)
    await async_session.commit()
    return async_session


async def _seed_departments(session: AsyncSession) -> None:
    """부서 샘플 데이터"""
    departments = [
        Department(),
        Department(),
        Department(),
        Department(),
        Department(),
    ]

    for i, dept in enumerate(departments):
        names = ["Engineering", "Sales", "Marketing", "HR", "Finance"]
        codes = ["ENG", "SAL", "MKT", "HR", "FIN"]
        budgets = [500000, 300000, 200000, 150000, 400000]
        dept.name = names[i]
        dept.code = codes[i]
        dept.budget = budgets[i]
        dept.is_active = i != 3  # HR은 비활성
        session.add(dept)


async def _seed_employees(session: AsyncSession) -> None:
    """직원 샘플 데이터"""
    # 1단계: 매니저 없는 직원들 먼저 삽입 (id 1-12, 13)
    managers_data = [
        ("Alice Kim", "alice@example.com", 80000, "2020-01-15", True, 35, 95, 1, None),  # id=1
        ("Bob Lee", "bob@example.com", 65000, "2021-03-20", False, 28, 75, 1, None),  # id=2, 나중에 manager_id 업데이트
        ("Carol Park", "carol@example.com", 70000, "2019-06-10", True, 42, 88, 2, None),  # id=3
        ("David Choi", "david@example.com", 55000, "2022-01-05", False, 25, 60, 2, None),  # id=4
        ("Eve Jung", "eve@example.com", 72000, "2020-08-12", False, 31, 82, 1, None),  # id=5
        ("Frank Oh", "frank@example.com", 58000, "2021-11-30", False, 29, 70, 3, None),  # id=6
        ("Grace Han", "grace@example.com", 85000, "2018-04-22", True, 45, 92, 3, None),  # id=7
        ("Henry Yoo", "henry@example.com", 62000, "2022-06-15", False, 27, 65, 2, None),  # id=8
        ("Iris Shin", "iris@example.com", 68000, "2020-09-01", False, 33, 78, 1, None),  # id=9
        ("Jack Kwon", "jack@example.com", 75000, "2019-12-10", True, 38, 85, 5, None),  # id=10
        ("Kate Moon", "kate@example.com", 52000, "2023-02-28", False, 24, 55, 5, None),  # id=11
        ("Leo Baek", "leo@example.com", 90000, "2017-07-01", True, 48, 98, 1, None),  # id=12
        ("Mia Song", "mia@example.com", 48000, "2023-05-10", False, 23, 45, None, None),  # id=13
        ("Noah Jang", "noah@example.com", 63000, "2021-08-20", False, 30, 72, 2, None),  # id=14
        ("Olivia Ryu", "olivia@example.com", 71000, "2020-04-05", False, 34, 80, 3, None),  # id=15
    ]

    for data in managers_data:
        emp = Employee()
        emp.name, emp.email, emp.salary, emp.hire_date, emp.is_manager, emp.age, emp.performance_score, emp.department_id, emp.manager_id = data
        session.add(emp)


async def _seed_products(session: AsyncSession) -> None:
    """상품 샘플 데이터"""
    products_data = [
        ("Laptop Pro", "Electronics", 150000, 50, True, 5),
        ("Wireless Mouse", "Electronics", 3500, 200, True, 4),
        ("USB-C Hub", "Electronics", 8000, 100, True, 4),
        ("Mechanical Keyboard", "Electronics", 12000, 75, True, 5),
        ("Monitor 27inch", "Electronics", 45000, 30, True, 5),
        ("Office Chair", "Furniture", 25000, 40, True, 4),
        ("Standing Desk", "Furniture", 55000, 20, True, 5),
        ("Desk Lamp", "Furniture", 3000, 150, True, 3),
        ("Python Book", "Books", 4500, 100, True, 5),
        ("Java Book", "Books", 4800, 80, True, 4),
        ("Design Book", "Books", 3800, 60, True, 4),
        ("Notebook Set", "Stationery", 1500, 300, True, 3),
        ("Pen Set", "Stationery", 800, 500, True, 4),
        ("Webcam HD", "Electronics", 7500, 45, False, 3),
        ("Headphones", "Electronics", 18000, 0, False, 5),
    ]

    for data in products_data:
        prod = Product()
        prod.name, prod.category, prod.price, prod.stock, prod.is_available, prod.rating = data
        session.add(prod)


async def _seed_customers(session: AsyncSession) -> None:
    """고객 샘플 데이터"""
    customers_data = [
        ("Customer A", "custa@example.com", "platinum", 1500000, "2019-01-10", True),
        ("Customer B", "custb@example.com", "gold", 800000, "2020-03-15", True),
        ("Customer C", "custc@example.com", "silver", 350000, "2021-06-20", False),
        ("Customer D", "custd@example.com", "bronze", 50000, "2022-01-05", False),
        ("Customer E", "custe@example.com", "gold", 650000, "2020-08-12", True),
        ("Customer F", "custf@example.com", "silver", 280000, "2021-11-30", False),
        ("Customer G", "custg@example.com", "bronze", 80000, "2022-04-22", False),
        ("Customer H", "custh@example.com", "platinum", 2200000, "2018-07-15", True),
        ("Customer I", "custi@example.com", "bronze", 25000, "2023-02-28", False),
        ("Customer J", "custj@example.com", "silver", 420000, "2021-05-10", False),
    ]

    for data in customers_data:
        cust = Customer()
        cust.name, cust.email, cust.tier, cust.total_spent, cust.signup_date, cust.is_vip = data
        session.add(cust)


async def _seed_orders(session: AsyncSession) -> None:
    """주문 샘플 데이터"""
    orders_data = [
        ("2023-01-15", "delivered", 250000, 5000, 1),
        ("2023-02-20", "delivered", 180000, 0, 1),
        ("2023-03-10", "shipped", 95000, 2000, 2),
        ("2023-04-05", "confirmed", 320000, 10000, 3),
        ("2023-04-15", "pending", 45000, 0, 4),
        ("2023-05-01", "delivered", 520000, 15000, 1),
        ("2023-05-20", "shipped", 75000, 0, 5),
        ("2023-06-10", "delivered", 150000, 3000, 2),
        ("2023-06-25", "confirmed", 88000, 0, 6),
        ("2023-07-05", "pending", 200000, 5000, 7),
        ("2023-07-15", "delivered", 350000, 8000, 8),
        ("2023-08-01", "shipped", 125000, 0, 3),
        ("2023-08-20", "delivered", 95000, 2000, 5),
        ("2023-09-10", "confirmed", 180000, 0, 9),
        ("2023-09-25", "pending", 65000, 1000, 10),
    ]

    for data in orders_data:
        order = Order()
        order.order_date, order.status, order.total_amount, order.discount, order.customer_id = data
        session.add(order)

    await session.commit()

    # Order Items
    items_data = [
        (1, 1, 1, 150000),
        (1, 2, 2, 50000),
        (2, 1, 1, 150000),
        (2, 6, 1, 30000),
        (3, 2, 5, 17500),
        (3, 3, 2, 16000),
        (4, 7, 1, 55000),
        (4, 5, 2, 90000),
        (4, 9, 10, 45000),
        (5, 12, 30, 45000),
        (6, 1, 2, 300000),
        (6, 4, 3, 36000),
        (7, 8, 5, 15000),
        (7, 11, 10, 38000),
        (8, 5, 1, 45000),
        (8, 6, 2, 50000),
        (9, 9, 8, 36000),
        (9, 10, 5, 24000),
        (10, 7, 2, 110000),
        (11, 1, 1, 150000),
        (11, 4, 2, 24000),
        (11, 3, 5, 40000),
        (12, 2, 10, 35000),
        (12, 13, 50, 40000),
        (13, 6, 1, 25000),
        (13, 8, 10, 30000),
        (14, 5, 2, 90000),
        (14, 9, 10, 45000),
        (15, 12, 20, 30000),
        (15, 11, 5, 19000),
    ]

    for data in items_data:
        item = OrderItem()
        item.order_id, item.product_id, item.quantity, item.unit_price = data
        session.add(item)


async def _seed_sales_records(session: AsyncSession) -> None:
    """판매 기록 샘플 데이터"""
    sales_data = [
        ("2023-01-05", 150000, "Seoul", 1),
        ("2023-01-10", 80000, "Busan", 2),
        ("2023-01-15", 120000, "Seoul", 1),
        ("2023-01-20", 95000, "Daegu", 3),
        ("2023-02-01", 200000, "Seoul", 1),
        ("2023-02-10", 65000, "Busan", 2),
        ("2023-02-15", 180000, "Seoul", 4),
        ("2023-02-20", 110000, "Daegu", 3),
        ("2023-03-01", 250000, "Seoul", 1),
        ("2023-03-10", 90000, "Busan", 2),
        ("2023-03-15", 140000, "Seoul", 4),
        ("2023-03-20", 75000, "Daegu", 3),
        ("2023-04-01", 300000, "Seoul", 1),
        ("2023-04-10", 85000, "Busan", 2),
        ("2023-04-15", 160000, "Seoul", 4),
        ("2023-04-20", 95000, "Incheon", 5),
        ("2023-05-01", 280000, "Seoul", 1),
        ("2023-05-10", 100000, "Busan", 2),
        ("2023-05-15", 190000, "Seoul", 4),
        ("2023-05-20", 120000, "Incheon", 5),
    ]

    for data in sales_data:
        sale = SalesRecord()
        sale.sale_date, sale.amount, sale.region, sale.salesperson_id = data
        session.add(sale)


async def _seed_scores(session: AsyncSession) -> None:
    """점수 샘플 데이터 (랭킹 테스트용)"""
    scores_data = [
        ("Player1", "Chess", 1500, "2023-01-10"),
        ("Player2", "Chess", 1500, "2023-01-12"),
        ("Player3", "Chess", 1450, "2023-01-15"),
        ("Player4", "Chess", 1600, "2023-01-20"),
        ("Player5", "Chess", 1550, "2023-01-25"),
        ("Player1", "Go", 2000, "2023-02-01"),
        ("Player2", "Go", 1800, "2023-02-05"),
        ("Player3", "Go", 1900, "2023-02-10"),
        ("Player1", "Poker", 500, "2023-03-01"),
        ("Player2", "Poker", 750, "2023-03-05"),
        ("Player3", "Poker", 500, "2023-03-10"),
        ("Player4", "Poker", 600, "2023-03-15"),
        ("Player5", "Poker", 750, "2023-03-20"),
        ("Player6", "Poker", 800, "2023-03-25"),
        ("Player1", "Chess", 1520, "2023-04-01"),
        ("Player2", "Chess", 1480, "2023-04-05"),
        ("Player3", "Chess", 1470, "2023-04-10"),
        ("Player4", "Chess", 1620, "2023-04-15"),
        ("Player5", "Chess", 1580, "2023-04-20"),
        ("Player6", "Chess", 1400, "2023-04-25"),
    ]

    for data in scores_data:
        score = Score()
        score.player_name, score.game, score.points, score.play_date = data
        session.add(score)
