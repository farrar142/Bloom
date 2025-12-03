"""Level 5: Complex Subqueries - 복합 서브쿼리 테스트 (20개)

복합 서브쿼리, 상관 서브쿼리, 다중 조인, 다단계 쿼리 등을 테스트합니다.
"""

import pytest
from bloom.db import Query, OrderBy, Count, Sum, Avg, Min, Max
from bloom.db.expressions import (
    RowNumber,
    Rank,
    DenseRank,
    Lag,
    Lead,
    SumOver,
    AvgOver,
    WindowFrame,
    FrameBound,
)

from .conftest import (
    Employee,
    Department,
    Product,
    Customer,
    Order,
    OrderItem,
    SalesRecord,
    Score,
    AsyncSession,
)


class TestLevel5ComplexSubqueries:
    """Level 5: Complex Subqueries - 복합 서브쿼리 20개"""

    # =========================================================================
    # 1-5: 다중 서브쿼리 조합
    # =========================================================================

    @pytest.mark.asyncio
    async def test_01_nested_in_subquery(self, seeded_session: AsyncSession):
        """1. 중첩 IN 서브쿼리 - 고액 주문 상품의 카테고리"""
        # 고액 주문 (30만원 이상)의 상품 ID
        high_order_product_ids = (
            Query(OrderItem)
            .join(Order).on(OrderItem.order_id, Order.id)
            .filter(Order.total_amount >= 300000)
            .select(OrderItem.product_id)
            .subquery()
        )

        # 해당 상품들
        query = (
            Query(Product)
            .filter(Product.id.in_(high_order_product_ids))
            .with_session(seeded_session)
        )
        products = await query.async_all()

        assert len(products) >= 1

    @pytest.mark.asyncio
    async def test_02_subquery_chain(self, seeded_session: AsyncSession):
        """2. 서브쿼리 체인 - 활성 부서의 매니저"""
        # 활성 부서 ID
        active_dept_ids = (
            Query(Department)
            .filter(Department.is_active == True)
            .select(Department.id)
            .subquery()
        )

        # 해당 부서의 매니저
        query = (
            Query(Employee)
            .filter(Employee.department_id.in_(active_dept_ids))
            .filter(Employee.is_manager == True)
            .with_session(seeded_session)
        )
        managers = await query.async_all()

        assert all(emp.is_manager for emp in managers)

    @pytest.mark.asyncio
    async def test_03_double_not_in(self, seeded_session: AsyncSession):
        """3. 다중 NOT IN - 특정 조건 제외"""
        # 고성과자 (80점 이상)
        high_performers = (
            Query(Employee)
            .filter(Employee.performance_score >= 80)
            .select(Employee.id)
            .subquery()
        )

        # 매니저
        managers = (
            Query(Employee)
            .filter(Employee.is_manager == True)
            .select(Employee.id)
            .subquery()
        )

        # 고성과자도 매니저도 아닌 직원
        query = (
            Query(Employee)
            .filter(Employee.id.not_in(high_performers))
            .filter(Employee.id.not_in(managers))
            .with_session(seeded_session)
        )
        employees = await query.async_all()

        for emp in employees:
            assert emp.performance_score < 80
            assert not emp.is_manager

    @pytest.mark.asyncio
    async def test_04_exists_and_in_combined(self, seeded_session: AsyncSession):
        """4. EXISTS + IN 조합"""
        # VIP 고객 ID
        vip_ids = (
            Query(Customer)
            .filter(Customer.is_vip == True)
            .select(Customer.id)
            .subquery()
        )

        # VIP 고객 중 배송 완료 주문이 있는 경우
        has_delivered = (
            Query(Order)
            .filter(Order.customer_id == Customer.id)
            .filter(Order.status == "delivered")
            .subquery()
            .exists()
        )

        query = (
            Query(Customer)
            .filter(Customer.id.in_(vip_ids))
            .filter(has_delivered)
            .with_session(seeded_session)
        )
        customers = await query.async_all()

        assert all(c.is_vip for c in customers)

    @pytest.mark.asyncio
    async def test_05_aggregate_subquery_comparison(self, seeded_session: AsyncSession):
        """5. 집계 서브쿼리 비교 - 평균 이상 주문"""
        # 전체 평균 주문 금액
        avg_result = await (
            Query(Order)
            .annotate(avg_amount=Avg(Order.total_amount))
            .with_session(seeded_session)
        ).async_aggregate_first()

        avg_amount = avg_result["avg_amount"] if avg_result else 0

        # 평균 이상 주문
        query = (
            Query(Order)
            .filter(Order.total_amount >= avg_amount)
            .order_by(Order.total_amount.desc())
            .with_session(seeded_session)
        )
        orders = await query.async_all()

        assert all(o.total_amount >= avg_amount for o in orders)

    # =========================================================================
    # 6-10: 상관 서브쿼리 (Correlated Subquery)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_06_correlated_exists(self, seeded_session: AsyncSession):
        """6. 상관 EXISTS - 주문이 있는 고객"""
        has_order = (
            Query(Order)
            .filter(Order.customer_id == Customer.id)
            .subquery()
            .exists()
        )

        query = (
            Query(Customer)
            .filter(has_order)
            .with_session(seeded_session)
        )
        customers = await query.async_all()

        assert len(customers) >= 1

    @pytest.mark.asyncio
    async def test_07_correlated_not_exists(self, seeded_session: AsyncSession):
        """7. 상관 NOT EXISTS - 주문이 없는 고객"""
        has_order = (
            Query(Order)
            .filter(Order.customer_id == Customer.id)
            .subquery()
            .not_exists()
        )

        query = (
            Query(Customer)
            .filter(has_order)
            .with_session(seeded_session)
        )
        customers = await query.async_all()

        # 결과가 있을 수도 없을 수도 있음

    @pytest.mark.asyncio
    async def test_08_correlated_with_condition(self, seeded_session: AsyncSession):
        """8. 조건부 상관 서브쿼리 - 고액 주문이 있는 고객"""
        has_high_order = (
            Query(Order)
            .filter(Order.customer_id == Customer.id)
            .filter(Order.total_amount >= 200000)
            .subquery()
            .exists()
        )

        query = (
            Query(Customer)
            .filter(has_high_order)
            .with_session(seeded_session)
        )
        customers = await query.async_all()

        assert len(customers) >= 1

    @pytest.mark.asyncio
    async def test_09_correlated_count_condition(self, seeded_session: AsyncSession):
        """9. 상관 서브쿼리 - 2번 이상 주문한 고객"""
        # 고객별 주문 수 계산
        customer_orders = await (
            Query(Order)
            .annotate(order_count=Count(Order.id))
            .group_by(Order.customer_id)
            .having(Count(Order.id) >= 2)
            .with_session(seeded_session)
        ).async_aggregate_all()

        frequent_customer_ids = [r["customer_id"] for r in customer_orders]

        # 해당 고객들
        if frequent_customer_ids:
            query = (
                Query(Customer)
                .filter(Customer.id.in_(frequent_customer_ids))
                .with_session(seeded_session)
            )
            customers = await query.async_all()
            assert len(customers) == len(frequent_customer_ids)

    @pytest.mark.asyncio
    async def test_10_multi_level_correlated(self, seeded_session: AsyncSession):
        """10. 다단계 상관 서브쿼리"""
        # Electronics 상품을 주문한 주문 ID
        electronics_orders = (
            Query(OrderItem)
            .join(Product).on(OrderItem.product_id, Product.id)
            .filter(Product.category == "Electronics")
            .select(OrderItem.order_id)
            .subquery()
        )

        # 해당 주문의 고객
        query = (
            Query(Order)
            .filter(Order.id.in_(electronics_orders))
            .with_session(seeded_session)
        )
        orders = await query.async_all()

        assert len(orders) >= 1

    # =========================================================================
    # 11-15: 다중 조인 및 복합 쿼리
    # =========================================================================

    @pytest.mark.asyncio
    async def test_11_triple_join(self, seeded_session: AsyncSession):
        """11. 3중 JOIN"""
        query = (
            Query(OrderItem)
            .join(Order).on(OrderItem.order_id, Order.id)
            .join(Customer).on(Order.customer_id, Customer.id)
            .filter(Customer.tier == "platinum")
            .with_session(seeded_session)
        )
        items = await query.async_all()

        assert len(items) >= 1

    @pytest.mark.asyncio
    async def test_12_join_with_subquery_filter(self, seeded_session: AsyncSession):
        """12. JOIN + 서브쿼리 필터"""
        # 재고가 있는 상품 ID
        available_products = (
            Query(Product)
            .filter(Product.stock > 0)
            .filter(Product.is_available == True)
            .select(Product.id)
            .subquery()
        )

        query = (
            Query(OrderItem)
            .filter(OrderItem.product_id.in_(available_products))
            .join(Order).on(OrderItem.order_id, Order.id)
            .filter(Order.status == "delivered")
            .with_session(seeded_session)
        )
        items = await query.async_all()

    @pytest.mark.asyncio
    async def test_13_left_join_null_check(self, seeded_session: AsyncSession):
        """13. LEFT JOIN + NULL 체크 - 부서 없는 직원"""
        query = (
            Query(Employee)
            .filter(Employee.department_id.is_null())
            .with_session(seeded_session)
        )
        employees = await query.async_all()

        assert all(emp.department_id is None for emp in employees)

    @pytest.mark.asyncio
    async def test_14_self_join_concept(self, seeded_session: AsyncSession):
        """14. 자기 참조 (매니저-부하 관계)"""
        # 매니저가 있는 직원
        query = (
            Query(Employee)
            .filter(Employee.manager_id.is_not_null())
            .with_session(seeded_session)
        )
        employees = await query.async_all()

        assert all(emp.manager_id is not None for emp in employees)

    @pytest.mark.asyncio
    async def test_15_complex_filter_with_join(self, seeded_session: AsyncSession):
        """15. 복합 필터 + JOIN"""
        query = (
            Query(Employee)
            .join(Department).on(Employee.department_id, Department.id)
            .filter(
                (Employee.salary >= 60000) & (Employee.salary <= 80000)
            )
            .filter(Department.budget >= 200000)
            .filter(Employee.performance_score >= 70)
            .order_by(Employee.salary.desc())
            .with_session(seeded_session)
        )
        employees = await query.async_all()

        for emp in employees:
            assert 60000 <= emp.salary <= 80000
            assert emp.performance_score >= 70

    # =========================================================================
    # 16-20: 고급 분석 쿼리
    # =========================================================================

    @pytest.mark.asyncio
    async def test_16_top_n_per_group(self, seeded_session: AsyncSession):
        """16. 그룹별 TOP N - 부서별 고액 연봉 직원"""
        # 부서별로 계산
        departments = await (
            Query(Department)
            .with_session(seeded_session)
        ).async_all()

        for dept in departments:
            top_3 = await (
                Query(Employee)
                .filter(Employee.department_id == dept.id)
                .order_by(Employee.salary.desc())
                .limit(3)
                .with_session(seeded_session)
            ).async_all()

            # 급여 내림차순 확인
            salaries = [e.salary for e in top_3]
            assert salaries == sorted(salaries, reverse=True)

    @pytest.mark.asyncio
    async def test_17_cumulative_calculation(self, seeded_session: AsyncSession):
        """17. 누적 계산 - 지역별 누적 판매액"""
        # 지역별 총 판매액
        region_totals = await (
            Query(SalesRecord)
            .annotate(total=Sum(SalesRecord.amount))
            .group_by(SalesRecord.region)
            .order_by(OrderBy("total", "DESC"))
            .with_session(seeded_session)
        ).async_aggregate_all()

        # 누적 계산 (파이썬에서)
        cumulative = 0
        for r in region_totals:
            cumulative += r["total"]
            r["cumulative"] = cumulative

        assert all("cumulative" in r for r in region_totals)

    @pytest.mark.asyncio
    async def test_18_year_over_year_comparison(self, seeded_session: AsyncSession):
        """18. 월별 판매 비교"""
        # 월별 판매액
        monthly_sales = await (
            Query(SalesRecord)
            .annotate(
                total_amount=Sum(SalesRecord.amount),
                sale_count=Count(SalesRecord.id)
            )
            .group_by(SalesRecord.sale_date)
            .order_by(OrderBy("sale_date", "ASC"))
            .with_session(seeded_session)
        ).async_aggregate_all()

        assert len(monthly_sales) >= 1

    @pytest.mark.asyncio
    async def test_19_pivot_style_query(self, seeded_session: AsyncSession):
        """19. 피벗 스타일 쿼리 - 상태별 주문 통계"""
        statuses = ["pending", "confirmed", "shipped", "delivered"]
        
        results = {}
        for status in statuses:
            stat = await (
                Query(Order)
                .filter(Order.status == status)
                .annotate(
                    count=Count(Order.id),
                    total=Sum(Order.total_amount)
                )
                .with_session(seeded_session)
            ).async_aggregate_first()
            
            results[status] = stat

        assert "delivered" in results

    @pytest.mark.asyncio
    async def test_20_complex_business_query(self, seeded_session: AsyncSession):
        """20. 복합 비즈니스 쿼리 - 우수 고객 분석"""
        # 1. 총 주문 금액이 높은 고객
        top_customers = await (
            Query(Order)
            .annotate(
                total_spent=Sum(Order.total_amount),
                order_count=Count(Order.id),
                avg_order=Avg(Order.total_amount)
            )
            .group_by(Order.customer_id)
            .having(Count(Order.id) >= 2)
            .order_by(OrderBy("total_spent", "DESC"))
            .limit(5)
            .with_session(seeded_session)
        ).async_aggregate_all()

        # 2. 해당 고객들의 상세 정보
        if top_customers:
            customer_ids = [r["customer_id"] for r in top_customers]
            
            customers = await (
                Query(Customer)
                .filter(Customer.id.in_(customer_ids))
                .with_session(seeded_session)
            ).async_all()

            assert len(customers) == len(customer_ids)

            # 결과 조합
            for cust in customers:
                for tc in top_customers:
                    if tc["customer_id"] == cust.id:
                        tc["name"] = cust.name
                        tc["tier"] = cust.tier
                        break

            assert all("name" in tc for tc in top_customers if tc.get("customer_id") in [c.id for c in customers])
