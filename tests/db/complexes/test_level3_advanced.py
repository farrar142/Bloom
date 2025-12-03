"""Level 3: Advanced Queries - 고급 쿼리 테스트 (20개)

서브쿼리, EXISTS, IN subquery, 스칼라 서브쿼리 등의 쿼리를 테스트합니다.
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
    Score,
    AsyncSession,
)


class TestLevel3AdvancedQueries:
    """Level 3: Advanced Queries - 고급 쿼리 20개"""

    # =========================================================================
    # 1-5: IN 서브쿼리
    # =========================================================================

    @pytest.mark.asyncio
    async def test_01_in_subquery_basic(self, seeded_session: AsyncSession):
        """1. 기본 IN 서브쿼리 - 주문한 고객 조회"""
        # 주문이 있는 고객 ID 서브쿼리
        order_customer_ids = (
            Query(Order)
            .select(Order.customer_id)
            .subquery()
        )

        query = (
            Query(Customer)
            .filter(Customer.id.in_(order_customer_ids))
            .with_session(seeded_session)
        )
        customers = await query.async_all()

        assert len(customers) >= 1

    @pytest.mark.asyncio
    async def test_02_in_subquery_with_filter(self, seeded_session: AsyncSession):
        """2. 조건이 있는 IN 서브쿼리 - VIP 고객의 주문"""
        vip_customer_ids = (
            Query(Customer)
            .filter(Customer.is_vip == True)
            .select(Customer.id)
            .subquery()
        )

        query = (
            Query(Order)
            .filter(Order.customer_id.in_(vip_customer_ids))
            .with_session(seeded_session)
        )
        orders = await query.async_all()

        assert len(orders) >= 1

    @pytest.mark.asyncio
    async def test_03_not_in_subquery(self, seeded_session: AsyncSession):
        """3. NOT IN 서브쿼리 - 주문 없는 고객"""
        order_customer_ids = (
            Query(Order)
            .select(Order.customer_id)
            .subquery()
        )

        query = (
            Query(Customer)
            .filter(Customer.id.not_in(order_customer_ids))
            .with_session(seeded_session)
        )
        customers = await query.async_all()

        # 주문이 없는 고객들

    @pytest.mark.asyncio
    async def test_04_in_subquery_aggregate(self, seeded_session: AsyncSession):
        """4. 집계 결과 기반 필터링 - 2번 이상 주문한 고객 (async_aggregate_all 사용)"""
        # 고객별 주문 수를 집계 쿼리로 조회
        order_counts_query = (
            Query(Order)
            .annotate(order_count=Count(Order.id))
            .group_by(Order.customer_id)
            .with_session(seeded_session)
        )
        
        # async_aggregate_all()은 딕셔너리 리스트 반환
        results = await order_counts_query.async_aggregate_all()
        # results: [{"customer_id": 1, "order_count": 3}, {"customer_id": 2, "order_count": 1}, ...]
        
        # 2번 이상 주문한 고객 ID 추출
        frequent_customer_ids = [
            r["customer_id"] for r in results if r["order_count"] >= 2
        ]
        
        # 해당 고객 조회
        query = (
            Query(Customer)
            .filter(Customer.id.in_(frequent_customer_ids))
            .with_session(seeded_session)
        )
        customers = await query.async_all()

        assert len(customers) >= 1

    @pytest.mark.asyncio
    async def test_05_in_subquery_nested(self, seeded_session: AsyncSession):
        """5. 중첩 필터 - 특정 카테고리 상품 주문 고객"""
        # Electronics 카테고리 상품 ID
        electronics_ids = (
            Query(Product)
            .filter(Product.category == "Electronics")
            .select(Product.id)
            .subquery()
        )

        # 해당 상품을 주문한 주문 ID
        orders_with_electronics = (
            Query(OrderItem)
            .filter(OrderItem.product_id.in_(electronics_ids))
            .select(OrderItem.order_id)
            .subquery()
        )

        # 해당 주문의 고객
        query = (
            Query(Order)
            .filter(Order.id.in_(orders_with_electronics))
            .with_session(seeded_session)
        )
        orders = await query.async_all()

        assert len(orders) >= 1

    # =========================================================================
    # 6-10: EXISTS 서브쿼리
    # =========================================================================

    @pytest.mark.asyncio
    async def test_06_exists_subquery(self, seeded_session: AsyncSession):
        """6. EXISTS 서브쿼리 - 직원이 있는 부서"""
        # 직원이 있는 부서 조회
        has_employees = (
            Query(Employee)
            .filter(Employee.department_id == Department.id)
            .subquery()
            .exists()
        )

        query = (
            Query(Department)
            .filter(has_employees)
            .with_session(seeded_session)
        )
        departments = await query.async_all()

        assert len(departments) >= 1

    @pytest.mark.asyncio
    async def test_07_not_exists_subquery(self, seeded_session: AsyncSession):
        """7. NOT EXISTS 서브쿼리 - 직원이 없는 부서"""
        has_employees = (
            Query(Employee)
            .filter(Employee.department_id == Department.id)
            .subquery()
            .not_exists()
        )

        query = (
            Query(Department)
            .filter(has_employees)
            .with_session(seeded_session)
        )
        departments = await query.async_all()

        # 직원이 없는 부서들 (있을 수도 없을 수도)

    @pytest.mark.asyncio
    async def test_08_exists_with_condition(self, seeded_session: AsyncSession):
        """8. 조건부 EXISTS - 배송 완료 주문이 있는 고객"""
        has_delivered_order = (
            Query(Order)
            .filter(Order.customer_id == Customer.id)
            .filter(Order.status == "delivered")
            .subquery()
            .exists()
        )

        query = (
            Query(Customer)
            .filter(has_delivered_order)
            .with_session(seeded_session)
        )
        customers = await query.async_all()

        assert len(customers) >= 1

    @pytest.mark.asyncio
    async def test_09_exists_aggregate_condition(self, seeded_session: AsyncSession):
        """9. EXISTS + 집계 조건 - 고액 주문이 있는 고객"""
        has_high_value_order = (
            Query(Order)
            .filter(Order.customer_id == Customer.id)
            .filter(Order.total_amount >= 300000)
            .subquery()
            .exists()
        )

        query = (
            Query(Customer)
            .filter(has_high_value_order)
            .with_session(seeded_session)
        )
        customers = await query.async_all()

        assert len(customers) >= 1

    @pytest.mark.asyncio
    async def test_10_exists_combined_with_filter(self, seeded_session: AsyncSession):
        """10. EXISTS + 일반 필터 조합"""
        has_orders = (
            Query(Order)
            .filter(Order.customer_id == Customer.id)
            .subquery()
            .exists()
        )

        query = (
            Query(Customer)
            .filter(Customer.is_vip == True)
            .filter(has_orders)
            .with_session(seeded_session)
        )
        vip_with_orders = await query.async_all()

        assert all(c.is_vip for c in vip_with_orders)

    # =========================================================================
    # 11-15: 스칼라 서브쿼리
    # =========================================================================

    @pytest.mark.asyncio
    async def test_11_scalar_subquery_avg(self, seeded_session: AsyncSession):
        """11. 스칼라 서브쿼리 - 평균 이상 급여 직원"""
        # 평균 급여 계산
        avg_salary_query = (
            Query(Employee)
            .annotate(avg_sal=Avg(Employee.salary))
        )
        
        # 평균 급여 먼저 계산
        avg_result = await avg_salary_query.with_session(seeded_session).async_aggregate_first()
        avg_salary = avg_result["avg_sal"] if avg_result else 0

        # 평균 이상 급여 직원
        query = (
            Query(Employee)
            .filter(Employee.salary >= avg_salary)
            .with_session(seeded_session)
        )
        employees = await query.async_all()

        assert all(emp.salary >= avg_salary for emp in employees)

    @pytest.mark.asyncio
    async def test_12_scalar_subquery_max(self, seeded_session: AsyncSession):
        """12. 최고 점수 플레이어 조회"""
        # Chess 최고 점수 계산
        max_result = await (
            Query(Score)
            .filter(Score.game == "Chess")
            .annotate(max_points=Max(Score.points))
            .with_session(seeded_session)
        ).async_aggregate_first()
        
        max_points = max_result["max_points"] if max_result else 0

        # 최고 점수 플레이어
        query = (
            Query(Score)
            .filter(Score.game == "Chess")
            .filter(Score.points == max_points)
            .with_session(seeded_session)
        )
        top_players = await query.async_all()

        assert all(s.points == max_points for s in top_players)

    @pytest.mark.asyncio
    async def test_13_subquery_with_order(self, seeded_session: AsyncSession):
        """13. 서브쿼리 + 정렬 - 최근 주문"""
        # 가장 최근 주문 날짜
        latest_query = (
            Query(Order)
            .order_by(Order.order_date.desc())
            .limit(1)
            .with_session(seeded_session)
        )
        latest_order = await latest_query.async_first()

        if latest_order:
            # 해당 날짜의 모든 주문
            query = (
                Query(Order)
                .filter(Order.order_date == latest_order.order_date)
                .with_session(seeded_session)
            )
            orders = await query.async_all()
            
            assert all(o.order_date == latest_order.order_date for o in orders)

    @pytest.mark.asyncio
    async def test_14_department_avg_comparison(self, seeded_session: AsyncSession):
        """14. 부서별 평균보다 높은 급여 직원 (개념적)"""
        # 부서별 평균 급여 계산
        dept_avgs = await (
            Query(Employee)
            .filter(Employee.department_id.is_not_null())
            .annotate(avg_sal=Avg(Employee.salary))
            .group_by(Employee.department_id)
            .with_session(seeded_session)
        ).async_aggregate_all()

        # 전체 평균보다 높은 직원
        overall_avg_result = await (
            Query(Employee)
            .annotate(avg_sal=Avg(Employee.salary))
            .with_session(seeded_session)
        ).async_aggregate_first()
        
        overall_avg = overall_avg_result["avg_sal"] if overall_avg_result else 0

        query = (
            Query(Employee)
            .filter(Employee.salary > overall_avg)
            .with_session(seeded_session)
        )
        above_avg = await query.async_all()

        assert all(emp.salary > overall_avg for emp in above_avg)

    @pytest.mark.asyncio
    async def test_15_top_n_per_category(self, seeded_session: AsyncSession):
        """15. 카테고리별 최고가 상품"""
        categories = ["Electronics", "Books", "Furniture"]
        
        for category in categories:
            max_result = await (
                Query(Product)
                .filter(Product.category == category)
                .annotate(max_price=Max(Product.price))
                .with_session(seeded_session)
            ).async_aggregate_first()

            if max_result and max_result["max_price"]:
                query = (
                    Query(Product)
                    .filter(Product.category == category)
                    .filter(Product.price == max_result["max_price"])
                    .with_session(seeded_session)
                )
                top_products = await query.async_all()
                
                assert all(p.price == max_result["max_price"] for p in top_products)

    # =========================================================================
    # 16-20: 복합 서브쿼리 및 고급 필터
    # =========================================================================

    @pytest.mark.asyncio
    async def test_16_multiple_subquery_conditions(self, seeded_session: AsyncSession):
        """16. 다중 서브쿼리 조건"""
        # 활성 부서 ID
        active_dept_ids = (
            Query(Department)
            .filter(Department.is_active == True)
            .select(Department.id)
            .subquery()
        )

        # 매니저 ID
        manager_ids = (
            Query(Employee)
            .filter(Employee.is_manager == True)
            .select(Employee.id)
            .subquery()
        )

        # 활성 부서의 직원 중 매니저가 아닌 사람
        query = (
            Query(Employee)
            .filter(Employee.department_id.in_(active_dept_ids))
            .filter(Employee.id.not_in(manager_ids))
            .with_session(seeded_session)
        )
        employees = await query.async_all()

        assert all(not emp.is_manager for emp in employees)

    @pytest.mark.asyncio
    async def test_17_subquery_with_join(self, seeded_session: AsyncSession):
        """17. 서브쿼리 + JOIN 조합"""
        # 고액 주문 (20만원 이상)
        high_value_orders = (
            Query(Order)
            .filter(Order.total_amount >= 200000)
            .select(Order.id)
            .subquery()
        )

        # 고액 주문 항목 조회 (JOIN 포함)
        query = (
            Query(OrderItem)
            .filter(OrderItem.order_id.in_(high_value_orders))
            .join(Product).on(OrderItem.product_id, Product.id)
            .with_session(seeded_session)
        )
        items = await query.async_all()

        assert len(items) >= 1

    @pytest.mark.asyncio
    async def test_18_conditional_aggregate(self, seeded_session: AsyncSession):
        """18. 조건부 집계 - 상태별 주문 통계"""
        statuses = ["pending", "confirmed", "shipped", "delivered"]
        
        for status in statuses:
            result = await (
                Query(Order)
                .filter(Order.status == status)
                .annotate(
                    cnt=Count(Order.id),
                    total=Sum(Order.total_amount)
                )
                .with_session(seeded_session)
            ).async_aggregate_first()
            
            # 결과 존재 확인

    @pytest.mark.asyncio
    async def test_19_complex_filter_chain(self, seeded_session: AsyncSession):
        """19. 복잡한 필터 체인"""
        query = (
            Query(Employee)
            .filter(Employee.salary >= 50000)
            .filter(Employee.salary <= 80000)
            .filter(Employee.age.between(25, 40))
            .filter(Employee.performance_score >= 60)
            .filter(Employee.department_id.is_not_null())
            .order_by(Employee.salary.desc())
            .limit(10)
            .with_session(seeded_session)
        )
        employees = await query.async_all()

        for emp in employees:
            assert 50000 <= emp.salary <= 80000
            assert 25 <= emp.age <= 40
            assert emp.performance_score >= 60

    @pytest.mark.asyncio
    async def test_20_aggregate_with_multiple_groups(self, seeded_session: AsyncSession):
        """20. 다중 그룹 집계"""
        query = (
            Query(Order)
            .annotate(
                order_count=Count(Order.id),
                total_amount=Sum(Order.total_amount),
                avg_amount=Avg(Order.total_amount)
            )
            .group_by(Order.customer_id, Order.status)
            .order_by(OrderBy("total_amount", "DESC"))
            .with_session(seeded_session)
        )
        results = await query.async_aggregate_all()

        assert len(results) >= 1
        for r in results:
            assert "order_count" in r
            assert "total_amount" in r
            assert "avg_amount" in r
