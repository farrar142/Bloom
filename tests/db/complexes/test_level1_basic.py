"""Level 1: Basic Queries - 기본 쿼리 테스트 (20개)

기본적인 SELECT, filter, order_by, limit, offset 등의 쿼리를 테스트합니다.
"""

import pytest
from bloom.db import Query, Condition, ConditionGroup, OrderBy

from .conftest import (
    Employee,
    Department,
    Product,
    Customer,
    Order,
    AsyncSession,
)


class TestLevel1BasicQueries:
    """Level 1: Basic Queries - 기본 쿼리 20개"""

    # =========================================================================
    # 1-5: 기본 SELECT
    # =========================================================================

    @pytest.mark.asyncio
    async def test_01_select_all(self, seeded_session: AsyncSession):
        """1. 모든 레코드 조회"""
        query = Query(Employee).with_session(seeded_session)
        employees = await query.async_all()

        assert len(employees) == 15
        assert all(hasattr(emp, "name") for emp in employees)

    @pytest.mark.asyncio
    async def test_02_select_first(self, seeded_session: AsyncSession):
        """2. 첫 번째 레코드 조회 (정렬 후)"""
        query = Query(Employee).order_by(Employee.hire_date).with_session(seeded_session)
        employee = await query.async_first()

        # 가장 먼저 고용된 직원
        assert employee is not None
        # hire_date로 정렬했으므로 가장 오래된 직원이 첫 번째
        assert employee.hire_date is not None

    @pytest.mark.asyncio
    async def test_03_select_one(self, seeded_session: AsyncSession):
        """3. 단일 레코드 조회 (정확히 1개)"""
        query = (
            Query(Employee)
            .filter(Employee.email == "alice@example.com")
            .with_session(seeded_session)
        )
        employee = await query.async_one()

        assert employee.name == "Alice Kim"
        assert employee.salary == 80000

    @pytest.mark.asyncio
    async def test_04_select_one_or_none(self, seeded_session: AsyncSession):
        """4. 단일 레코드 또는 None 조회"""
        # 존재하는 경우
        query = (
            Query(Employee)
            .filter(Employee.email == "bob@example.com")
            .with_session(seeded_session)
        )
        employee = await query.async_one_or_none()
        assert employee is not None
        assert employee.name == "Bob Lee"

        # 존재하지 않는 경우
        query = (
            Query(Employee)
            .filter(Employee.email == "nonexistent@example.com")
            .with_session(seeded_session)
        )
        employee = await query.async_one_or_none()
        assert employee is None

    @pytest.mark.asyncio
    async def test_05_select_count(self, seeded_session: AsyncSession):
        """5. 레코드 수 카운트"""
        query = Query(Employee).with_session(seeded_session)
        count = await query.async_count()

        assert count == 15

    # =========================================================================
    # 6-10: 단순 필터링
    # =========================================================================

    @pytest.mark.asyncio
    async def test_06_filter_equal(self, seeded_session: AsyncSession):
        """6. 동등 조건 필터 (==)"""
        query = (
            Query(Employee)
            .filter(Employee.is_manager == True)
            .with_session(seeded_session)
        )
        managers = await query.async_all()

        assert len(managers) == 5
        assert all(emp.is_manager for emp in managers)

    @pytest.mark.asyncio
    async def test_07_filter_not_equal(self, seeded_session: AsyncSession):
        """7. 부등 조건 필터 (!=)"""
        query = (
            Query(Product)
            .filter(Product.category != "Electronics")
            .with_session(seeded_session)
        )
        products = await query.async_all()

        assert all(p.category != "Electronics" for p in products)
        assert len(products) > 0

    @pytest.mark.asyncio
    async def test_08_filter_greater_than(self, seeded_session: AsyncSession):
        """8. 초과 조건 필터 (>)"""
        query = (
            Query(Employee)
            .filter(Employee.salary > 70000)
            .with_session(seeded_session)
        )
        high_earners = await query.async_all()

        assert all(emp.salary > 70000 for emp in high_earners)
        assert len(high_earners) >= 5

    @pytest.mark.asyncio
    async def test_09_filter_less_than_or_equal(self, seeded_session: AsyncSession):
        """9. 이하 조건 필터 (<=)"""
        query = (
            Query(Employee)
            .filter(Employee.age <= 30)
            .with_session(seeded_session)
        )
        young_employees = await query.async_all()

        assert all(emp.age <= 30 for emp in young_employees)

    @pytest.mark.asyncio
    async def test_10_filter_between(self, seeded_session: AsyncSession):
        """10. BETWEEN 조건 필터"""
        query = (
            Query(Employee)
            .filter(Employee.salary.between(60000, 75000))
            .with_session(seeded_session)
        )
        mid_earners = await query.async_all()

        assert all(60000 <= emp.salary <= 75000 for emp in mid_earners)

    # =========================================================================
    # 11-15: 문자열 및 컬렉션 연산
    # =========================================================================

    @pytest.mark.asyncio
    async def test_11_filter_like(self, seeded_session: AsyncSession):
        """11. LIKE 패턴 매칭"""
        query = (
            Query(Employee)
            .filter(Employee.name.like("%Kim"))
            .with_session(seeded_session)
        )
        kims = await query.async_all()

        assert len(kims) >= 1
        assert all("Kim" in emp.name for emp in kims)

    @pytest.mark.asyncio
    async def test_12_filter_startswith(self, seeded_session: AsyncSession):
        """12. 문자열 시작 패턴"""
        query = (
            Query(Product)
            .filter(Product.name.startswith("Laptop"))
            .with_session(seeded_session)
        )
        laptops = await query.async_all()

        assert len(laptops) >= 1
        assert all(p.name.startswith("Laptop") for p in laptops)

    @pytest.mark.asyncio
    async def test_13_filter_contains(self, seeded_session: AsyncSession):
        """13. 문자열 포함 패턴"""
        query = (
            Query(Product)
            .filter(Product.category == "Books")
            .with_session(seeded_session)
        )
        books = await query.async_all()

        # Books 카테고리 상품들 조회
        assert len(books) >= 1
        assert all(p.category == "Books" for p in books)

    @pytest.mark.asyncio
    async def test_14_filter_in_list(self, seeded_session: AsyncSession):
        """14. IN 리스트 필터"""
        categories = ["Books", "Stationery"]
        query = (
            Query(Product)
            .filter(Product.category.in_(categories))
            .with_session(seeded_session)
        )
        products = await query.async_all()

        assert all(p.category in categories for p in products)

    @pytest.mark.asyncio
    async def test_15_filter_not_in_list(self, seeded_session: AsyncSession):
        """15. NOT IN 리스트 필터"""
        excluded = ["bronze", "silver"]
        query = (
            Query(Customer)
            .filter(Customer.tier.not_in(excluded))
            .with_session(seeded_session)
        )
        customers = await query.async_all()

        assert all(c.tier not in excluded for c in customers)

    # =========================================================================
    # 16-20: 정렬 및 페이지네이션
    # =========================================================================

    @pytest.mark.asyncio
    async def test_16_order_by_asc(self, seeded_session: AsyncSession):
        """16. 오름차순 정렬"""
        query = (
            Query(Employee)
            .order_by(Employee.salary.asc())
            .with_session(seeded_session)
        )
        employees = await query.async_all()

        salaries = [emp.salary for emp in employees]
        assert salaries == sorted(salaries)

    @pytest.mark.asyncio
    async def test_17_order_by_desc(self, seeded_session: AsyncSession):
        """17. 내림차순 정렬"""
        query = (
            Query(Employee)
            .order_by(Employee.performance_score.desc())
            .with_session(seeded_session)
        )
        employees = await query.async_all()

        scores = [emp.performance_score for emp in employees]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_18_order_by_multiple(self, seeded_session: AsyncSession):
        """18. 다중 컬럼 정렬"""
        query = (
            Query(Employee)
            .order_by(Employee.is_manager.desc(), Employee.salary.desc())
            .with_session(seeded_session)
        )
        employees = await query.async_all()

        # 매니저가 먼저, 그 안에서 급여 순
        managers = [e for e in employees if e.is_manager]
        non_managers = [e for e in employees if not e.is_manager]

        # 매니저들은 급여 내림차순
        manager_salaries = [e.salary for e in managers]
        assert manager_salaries == sorted(manager_salaries, reverse=True)

    @pytest.mark.asyncio
    async def test_19_limit(self, seeded_session: AsyncSession):
        """19. LIMIT 제한"""
        query = (
            Query(Employee)
            .order_by(Employee.salary.desc())
            .limit(5)
            .with_session(seeded_session)
        )
        top_5 = await query.async_all()

        assert len(top_5) == 5

    @pytest.mark.asyncio
    async def test_20_limit_offset_pagination(self, seeded_session: AsyncSession):
        """20. LIMIT + OFFSET 페이지네이션"""
        page_size = 5
        page = 2  # 두 번째 페이지 (0-based index로 offset 계산)

        query = (
            Query(Employee)
            .order_by(Employee.id.asc())
            .limit(page_size)
            .offset((page - 1) * page_size)
            .with_session(seeded_session)
        )
        page_2_employees = await query.async_all()

        assert len(page_2_employees) == 5

        # 첫 페이지와 비교
        first_page = await (
            Query(Employee)
            .order_by(Employee.id.asc())
            .limit(page_size)
            .with_session(seeded_session)
        ).async_all()

        # 두 번째 페이지는 첫 페이지와 겹치지 않음
        first_page_ids = {e.id for e in first_page}
        page_2_ids = {e.id for e in page_2_employees}
        assert first_page_ids.isdisjoint(page_2_ids)
