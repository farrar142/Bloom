"""Level 2: Intermediate Queries - 중급 쿼리 테스트 (20개)

JOIN, GROUP BY, aggregate 함수, AND/OR 조건 등의 쿼리를 테스트합니다.
"""

import pytest
from bloom.db import Query, Condition, ConditionGroup, OrderBy, Count, Sum, Avg, Min, Max

from .conftest import (
    Employee,
    Department,
    Product,
    Customer,
    Order,
    OrderItem,
    SalesRecord,
    AsyncSession,
)


class TestLevel2IntermediateQueries:
    """Level 2: Intermediate Queries - 중급 쿼리 20개"""

    # =========================================================================
    # 1-5: 복합 조건 (AND/OR)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_01_filter_multiple_and(self, seeded_session: AsyncSession):
        """1. 다중 AND 조건"""
        query = (
            Query(Employee)
            .filter(Employee.salary >= 60000)
            .filter(Employee.age <= 35)
            .filter(Employee.is_manager == False)
            .with_session(seeded_session)
        )
        employees = await query.async_all()

        assert all(
            emp.salary >= 60000 and emp.age <= 35 and not emp.is_manager
            for emp in employees
        )

    @pytest.mark.asyncio
    async def test_02_filter_or_condition(self, seeded_session: AsyncSession):
        """2. OR 조건 그룹"""
        query = (
            Query(Employee)
            .filter(
                (Employee.salary >= 80000) | (Employee.is_manager == True)
            )
            .with_session(seeded_session)
        )
        employees = await query.async_all()

        assert all(
            emp.salary >= 80000 or emp.is_manager
            for emp in employees
        )

    @pytest.mark.asyncio
    async def test_03_filter_complex_and_or(self, seeded_session: AsyncSession):
        """3. 복합 AND/OR 조건"""
        # (salary > 70000 AND age < 40) OR is_manager = True
        query = (
            Query(Employee)
            .filter(
                ((Employee.salary > 70000) & (Employee.age < 40))
                | (Employee.is_manager == True)
            )
            .with_session(seeded_session)
        )
        employees = await query.async_all()

        assert all(
            (emp.salary > 70000 and emp.age < 40) or emp.is_manager
            for emp in employees
        )

    @pytest.mark.asyncio
    async def test_04_filter_null_check(self, seeded_session: AsyncSession):
        """4. NULL 체크 (IS NULL)"""
        query = (
            Query(Employee)
            .filter(Employee.department_id.is_null())
            .with_session(seeded_session)
        )
        employees = await query.async_all()

        assert all(emp.department_id is None for emp in employees)

    @pytest.mark.asyncio
    async def test_05_filter_not_null_check(self, seeded_session: AsyncSession):
        """5. NOT NULL 체크 (IS NOT NULL)"""
        query = (
            Query(Employee)
            .filter(Employee.manager_id.is_not_null())
            .with_session(seeded_session)
        )
        employees = await query.async_all()

        assert all(emp.manager_id is not None for emp in employees)

    # =========================================================================
    # 6-10: JOIN 쿼리
    # =========================================================================

    @pytest.mark.asyncio
    async def test_06_inner_join(self, seeded_session: AsyncSession):
        """6. INNER JOIN"""
        query = (
            Query(Employee)
            .join(Department).on(Employee.department_id, Department.id)
            .filter(Department.name == "Engineering")
            .with_session(seeded_session)
        )
        engineers = await query.async_all()

        assert len(engineers) >= 1
        # Engineering 부서원만 조회됨

    @pytest.mark.asyncio
    async def test_07_left_join(self, seeded_session: AsyncSession):
        """7. LEFT JOIN (부서 없는 직원 포함)"""
        query = (
            Query(Employee)
            .left_join(Department).on(Employee.department_id, Department.id)
            .with_session(seeded_session)
        )
        employees = await query.async_all()

        # 부서가 없는 직원도 포함
        assert len(employees) == 15

    @pytest.mark.asyncio
    async def test_08_join_with_filter(self, seeded_session: AsyncSession):
        """8. JOIN + WHERE 조건"""
        query = (
            Query(Order)
            .join(Customer).on(Order.customer_id, Customer.id)
            .filter(Customer.tier == "platinum")
            .filter(Order.status == "delivered")
            .with_session(seeded_session)
        )
        orders = await query.async_all()

        # platinum 고객의 delivered 주문만
        assert all(o.status == "delivered" for o in orders)

    @pytest.mark.asyncio
    async def test_09_multiple_joins(self, seeded_session: AsyncSession):
        """9. 다중 JOIN"""
        query = (
            Query(OrderItem)
            .join(Order).on(OrderItem.order_id, Order.id)
            .join(Product).on(OrderItem.product_id, Product.id)
            .filter(Product.category == "Electronics")
            .with_session(seeded_session)
        )
        items = await query.async_all()

        assert len(items) >= 1

    @pytest.mark.asyncio
    async def test_10_join_complex_condition(self, seeded_session: AsyncSession):
        """10. JOIN ON 복합 조건"""
        query = (
            Query(Employee)
            .join(Department).on(
                (Employee.department_id == Department.id) 
                & (Department.is_active == True)
            )
            .with_session(seeded_session)
        )
        employees = await query.async_all()

        # 활성 부서의 직원만 조회

    # =========================================================================
    # 11-15: 집계 함수 (GROUP BY)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_11_count_aggregate(self, seeded_session: AsyncSession):
        """11. COUNT 집계"""
        query = (
            Query(Employee)
            .annotate(emp_count=Count(Employee.id))
            .group_by(Employee.department_id)
            .with_session(seeded_session)
        )
        results = await query.async_aggregate_all()

        assert len(results) >= 1
        assert all("emp_count" in r for r in results)

    @pytest.mark.asyncio
    async def test_12_sum_aggregate(self, seeded_session: AsyncSession):
        """12. SUM 집계"""
        query = (
            Query(Order)
            .annotate(total_sales=Sum(Order.total_amount))
            .group_by(Order.customer_id)
            .with_session(seeded_session)
        )
        results = await query.async_aggregate_all()

        assert len(results) >= 1
        assert all("total_sales" in r for r in results)

    @pytest.mark.asyncio
    async def test_13_avg_aggregate(self, seeded_session: AsyncSession):
        """13. AVG 집계"""
        query = (
            Query(Employee)
            .annotate(avg_salary=Avg(Employee.salary))
            .group_by(Employee.department_id)
            .with_session(seeded_session)
        )
        results = await query.async_aggregate_all()

        assert len(results) >= 1
        assert all("avg_salary" in r for r in results)

    @pytest.mark.asyncio
    async def test_14_min_max_aggregate(self, seeded_session: AsyncSession):
        """14. MIN/MAX 집계"""
        query = (
            Query(Product)
            .annotate(
                min_price=Min(Product.price),
                max_price=Max(Product.price)
            )
            .group_by(Product.category)
            .with_session(seeded_session)
        )
        results = await query.async_aggregate_all()

        assert len(results) >= 1
        for r in results:
            assert "min_price" in r
            assert "max_price" in r
            assert r["min_price"] <= r["max_price"]

    @pytest.mark.asyncio
    async def test_15_multiple_aggregates(self, seeded_session: AsyncSession):
        """15. 다중 집계 함수"""
        query = (
            Query(SalesRecord)
            .annotate(
                sale_count=Count(SalesRecord.id),
                total_amount=Sum(SalesRecord.amount),
                avg_amount=Avg(SalesRecord.amount)
            )
            .group_by(SalesRecord.region)
            .with_session(seeded_session)
        )
        results = await query.async_aggregate_all()

        assert len(results) >= 1
        for r in results:
            assert "sale_count" in r
            assert "total_amount" in r
            assert "avg_amount" in r

    # =========================================================================
    # 16-20: HAVING 및 복합 집계
    # =========================================================================

    @pytest.mark.asyncio
    async def test_16_having_condition(self, seeded_session: AsyncSession):
        """16. HAVING 조건"""
        query = (
            Query(Employee)
            .annotate(emp_count=Count(Employee.id))
            .group_by(Employee.department_id)
            .having(Count(Employee.id) >= 3)
            .with_session(seeded_session)
        )
        results = await query.async_aggregate_all()

        assert all(r["emp_count"] >= 3 for r in results)

    @pytest.mark.asyncio
    async def test_17_having_with_sum(self, seeded_session: AsyncSession):
        """17. HAVING + SUM 조건"""
        query = (
            Query(Order)
            .annotate(total_spent=Sum(Order.total_amount))
            .group_by(Order.customer_id)
            .having(Sum(Order.total_amount) >= 200000)
            .with_session(seeded_session)
        )
        results = await query.async_aggregate_all()

        assert all(r["total_spent"] >= 200000 for r in results)

    @pytest.mark.asyncio
    async def test_18_group_by_with_order_by(self, seeded_session: AsyncSession):
        """18. GROUP BY + ORDER BY"""
        query = (
            Query(SalesRecord)
            .annotate(total_sales=Sum(SalesRecord.amount))
            .group_by(SalesRecord.region)
            .order_by(OrderBy("total_sales", "DESC"))
            .with_session(seeded_session)
        )
        results = await query.async_aggregate_all()

        # 내림차순 정렬 확인
        totals = [r["total_sales"] for r in results]
        assert totals == sorted(totals, reverse=True)

    @pytest.mark.asyncio
    async def test_19_aggregate_with_filter(self, seeded_session: AsyncSession):
        """19. WHERE + GROUP BY + HAVING"""
        query = (
            Query(Order)
            .filter(Order.status == "delivered")
            .annotate(order_count=Count(Order.id))
            .group_by(Order.customer_id)
            .having(Count(Order.id) >= 1)
            .with_session(seeded_session)
        )
        results = await query.async_aggregate_all()

        assert all(r["order_count"] >= 1 for r in results)

    @pytest.mark.asyncio
    async def test_20_exists_check(self, seeded_session: AsyncSession):
        """20. EXISTS 체크"""
        query = (
            Query(Employee)
            .filter(Employee.salary > 70000)
            .with_session(seeded_session)
        )
        exists = await query.async_exists()

        assert exists is True

        # 존재하지 않는 조건
        query2 = (
            Query(Employee)
            .filter(Employee.salary > 1000000)
            .with_session(seeded_session)
        )
        exists2 = await query2.async_exists()

        assert exists2 is False
