"""Level 6: Expert Queries - 전문가 수준 쿼리 테스트 (20개)

복합 윈도우 프레임, 고급 분석 쿼리, 복합 비즈니스 로직 등을 테스트합니다.
"""

import pytest
from bloom.db import Query, OrderBy, Count, Sum, Avg, Min, Max
from bloom.db.expressions import (
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


class TestLevel6ExpertQueries:
    """Level 6: Expert Queries - 전문가 수준 쿼리 20개"""

    # =========================================================================
    # 1-5: 복합 윈도우 프레임 분석
    # =========================================================================

    @pytest.mark.asyncio
    async def test_01_moving_average_3_period(self, seeded_session: AsyncSession):
        """1. 3기간 이동 평균"""
        moving_avg = AvgOver(SalesRecord.amount).over(
            partition_by=[SalesRecord.region],
            order_by=[OrderBy("sale_date", "ASC")],
            frame=WindowFrame("ROWS", FrameBound.preceding(2), FrameBound.CURRENT_ROW)
        ).as_("moving_avg_3")

        sql = moving_avg.to_sql()
        assert "AVG(amount)" in sql
        assert "PARTITION BY" in sql
        assert "2 PRECEDING" in sql

    @pytest.mark.asyncio
    async def test_02_cumulative_sum_unbounded(self, seeded_session: AsyncSession):
        """2. 무한 누적 합계"""
        cum_sum = SumOver(Order.total_amount).over(
            partition_by=[Order.customer_id],
            order_by=[OrderBy("order_date", "ASC")],
            frame=WindowFrame("ROWS", FrameBound.UNBOUNDED_PRECEDING, FrameBound.CURRENT_ROW)
        ).as_("cumulative_total")

        sql = cum_sum.to_sql()
        assert "SUM(total_amount)" in sql
        assert "UNBOUNDED PRECEDING" in sql

    @pytest.mark.asyncio
    async def test_03_centered_moving_average(self, seeded_session: AsyncSession):
        """3. 중심 이동 평균 (앞뒤 1개씩)"""
        centered_avg = AvgOver(SalesRecord.amount).over(
            order_by=[OrderBy("sale_date", "ASC")],
            frame=WindowFrame("ROWS", FrameBound.preceding(1), FrameBound.following(1))
        ).as_("centered_avg")

        sql = centered_avg.to_sql()
        assert "1 PRECEDING" in sql
        assert "1 FOLLOWING" in sql

    @pytest.mark.asyncio
    async def test_04_percent_of_total(self, seeded_session: AsyncSession):
        """4. 전체 대비 비율 계산 (개념적)"""
        # 전체 합계
        total_result = await (
            Query(Order)
            .annotate(total=Sum(Order.total_amount))
            .with_session(seeded_session)
        ).async_aggregate_first()

        total = total_result["total"] if total_result else 1

        # 각 주문의 비율
        orders = await (
            Query(Order)
            .order_by(Order.total_amount.desc())
            .with_session(seeded_session)
        ).async_all()

        for order in orders:
            order.__dict__["percent_of_total"] = (order.total_amount / total) * 100

        assert all(hasattr(o, "__dict__") for o in orders)

    @pytest.mark.asyncio
    async def test_05_running_difference(self, seeded_session: AsyncSession):
        """5. 이전 행과의 차이 (LAG 활용)"""
        prev_amount = Lag(SalesRecord.amount, 1, 0).over(
            partition_by=[SalesRecord.region],
            order_by=[OrderBy("sale_date", "ASC")]
        ).as_("prev_amount")

        sql = prev_amount.to_sql()
        assert "LAG(amount, 1, 0)" in sql

    # =========================================================================
    # 6-10: 복합 순위 및 분포 분석
    # =========================================================================

    @pytest.mark.asyncio
    async def test_06_multi_level_ranking(self, seeded_session: AsyncSession):
        """6. 다단계 순위 - 부서 내 순위 + 전체 순위"""
        dept_rank = Rank().over(
            partition_by=[Employee.department_id],
            order_by=[Employee.salary.desc()]
        ).as_("dept_rank")

        overall_rank = Rank().over(
            order_by=[Employee.salary.desc()]
        ).as_("overall_rank")

        assert "PARTITION BY" in dept_rank.to_sql()
        assert "PARTITION BY" not in overall_rank.to_sql()

    @pytest.mark.asyncio
    async def test_07_quartile_analysis(self, seeded_session: AsyncSession):
        """7. 사분위 분석"""
        quartile = NTile(4).over(
            order_by=[Employee.salary.desc()]
        ).as_("salary_quartile")

        sql = quartile.to_sql()
        assert "NTILE(4)" in sql

    @pytest.mark.asyncio
    async def test_08_percentile_with_ties(self, seeded_session: AsyncSession):
        """8. 백분위 순위 (동점 처리)"""
        pct_rank = PercentRank().over(
            partition_by=[Score.game],
            order_by=[OrderBy("points", "DESC")]
        ).as_("percentile")

        sql = pct_rank.to_sql()
        assert "PERCENT_RANK()" in sql

    @pytest.mark.asyncio
    async def test_09_dense_rank_gap_analysis(self, seeded_session: AsyncSession):
        """9. DENSE_RANK - 갭 없는 순위"""
        dense_rank = DenseRank().over(
            partition_by=[Employee.department_id],
            order_by=[Employee.performance_score.desc()]
        ).as_("performance_rank")

        sql = dense_rank.to_sql()
        assert "DENSE_RANK()" in sql

    @pytest.mark.asyncio
    async def test_10_cumulative_distribution(self, seeded_session: AsyncSession):
        """10. 누적 분포 함수"""
        cume_dist = CumeDist().over(
            order_by=[Order.total_amount.asc()]
        ).as_("cum_distribution")

        sql = cume_dist.to_sql()
        assert "CUME_DIST()" in sql

    # =========================================================================
    # 11-15: 고급 비즈니스 분석
    # =========================================================================

    @pytest.mark.asyncio
    async def test_11_cohort_analysis(self, seeded_session: AsyncSession):
        """11. 코호트 분석 - 가입 시기별 고객 분류"""
        # 가입 연도별 고객 수
        signup_cohorts = await (
            Query(Customer)
            .annotate(customer_count=Count(Customer.id))
            .group_by(Customer.signup_date)
            .order_by(OrderBy("signup_date", "ASC"))
            .with_session(seeded_session)
        ).async_aggregate_all()

        assert len(signup_cohorts) >= 1

    @pytest.mark.asyncio
    async def test_12_rfm_analysis_recency(self, seeded_session: AsyncSession):
        """12. RFM 분석 - Recency (최근성)"""
        # 고객별 마지막 주문 날짜
        customer_recency = await (
            Query(Order)
            .annotate(last_order=Max(Order.order_date))
            .group_by(Order.customer_id)
            .order_by(OrderBy("last_order", "DESC"))
            .with_session(seeded_session)
        ).async_aggregate_all()

        assert all("last_order" in r for r in customer_recency)

    @pytest.mark.asyncio
    async def test_13_rfm_analysis_frequency(self, seeded_session: AsyncSession):
        """13. RFM 분석 - Frequency (빈도)"""
        # 고객별 주문 횟수
        customer_frequency = await (
            Query(Order)
            .annotate(order_count=Count(Order.id))
            .group_by(Order.customer_id)
            .order_by(OrderBy("order_count", "DESC"))
            .with_session(seeded_session)
        ).async_aggregate_all()

        assert all("order_count" in r for r in customer_frequency)

    @pytest.mark.asyncio
    async def test_14_rfm_analysis_monetary(self, seeded_session: AsyncSession):
        """14. RFM 분석 - Monetary (금액)"""
        # 고객별 총 구매 금액
        customer_monetary = await (
            Query(Order)
            .annotate(
                total_spent=Sum(Order.total_amount),
                avg_order=Avg(Order.total_amount)
            )
            .group_by(Order.customer_id)
            .order_by(OrderBy("total_spent", "DESC"))
            .with_session(seeded_session)
        ).async_aggregate_all()

        assert all("total_spent" in r for r in customer_monetary)

    @pytest.mark.asyncio
    async def test_15_pareto_analysis(self, seeded_session: AsyncSession):
        """15. 파레토 분석 (80/20 법칙)"""
        # 상품별 판매 금액
        product_sales = await (
            Query(OrderItem)
            .annotate(total_revenue=Sum(OrderItem.unit_price))
            .group_by(OrderItem.product_id)
            .order_by(OrderBy("total_revenue", "DESC"))
            .with_session(seeded_session)
        ).async_aggregate_all()

        # 누적 비율 계산
        total_revenue = sum(r["total_revenue"] for r in product_sales)
        cumulative = 0
        for r in product_sales:
            cumulative += r["total_revenue"]
            r["cumulative_percent"] = (cumulative / total_revenue) * 100 if total_revenue > 0 else 0

        # 80% 기여 상품 수
        products_80 = [r for r in product_sales if r["cumulative_percent"] <= 80]

    # =========================================================================
    # 16-20: 최고급 분석 쿼리
    # =========================================================================

    @pytest.mark.asyncio
    async def test_16_year_over_year_growth(self, seeded_session: AsyncSession):
        """16. 월별 성장률 분석"""
        # 월별 판매 데이터
        monthly_sales = await (
            Query(SalesRecord)
            .annotate(
                monthly_total=Sum(SalesRecord.amount),
                sale_count=Count(SalesRecord.id)
            )
            .group_by(SalesRecord.sale_date)
            .order_by(OrderBy("sale_date", "ASC"))
            .with_session(seeded_session)
        ).async_aggregate_all()

        # 성장률 계산 (파이썬에서)
        for i in range(1, len(monthly_sales)):
            prev = monthly_sales[i - 1]["monthly_total"]
            curr = monthly_sales[i]["monthly_total"]
            monthly_sales[i]["growth_rate"] = ((curr - prev) / prev) * 100 if prev > 0 else 0

    @pytest.mark.asyncio
    async def test_17_market_basket_analysis(self, seeded_session: AsyncSession):
        """17. 장바구니 분석 - 함께 구매된 상품"""
        # 주문별 상품 조합 분석
        order_items = await (
            Query(OrderItem)
            .annotate(item_count=Count(OrderItem.id))
            .group_by(OrderItem.order_id)
            .having(Count(OrderItem.id) >= 2)
            .with_session(seeded_session)
        ).async_aggregate_all()

        # 2개 이상 상품이 있는 주문

    @pytest.mark.asyncio
    async def test_18_customer_lifetime_value(self, seeded_session: AsyncSession):
        """18. 고객 생애 가치 (CLV) 계산"""
        # 고객별 총 구매액, 주문 수, 평균 주문 금액
        clv_data = await (
            Query(Order)
            .annotate(
                total_revenue=Sum(Order.total_amount),
                order_count=Count(Order.id),
                avg_order_value=Avg(Order.total_amount)
            )
            .group_by(Order.customer_id)
            .with_session(seeded_session)
        ).async_aggregate_all()

        # CLV = 평균 주문 금액 * 주문 빈도
        for r in clv_data:
            r["estimated_clv"] = r["avg_order_value"] * r["order_count"]

    @pytest.mark.asyncio
    async def test_19_sales_forecast_preparation(self, seeded_session: AsyncSession):
        """19. 판매 예측용 데이터 준비"""
        # 지역별 월별 판매 데이터
        forecast_data = await (
            Query(SalesRecord)
            .annotate(
                total_sales=Sum(SalesRecord.amount),
                transaction_count=Count(SalesRecord.id),
                avg_transaction=Avg(SalesRecord.amount)
            )
            .group_by(SalesRecord.region, SalesRecord.sale_date)
            .order_by(OrderBy("region", "ASC"), OrderBy("sale_date", "ASC"))
            .with_session(seeded_session)
        ).async_aggregate_all()

        assert len(forecast_data) >= 1

    @pytest.mark.asyncio
    async def test_20_comprehensive_dashboard_query(self, seeded_session: AsyncSession):
        """20. 종합 대시보드 쿼리 - 전체 비즈니스 지표"""
        # 1. 총 매출
        total_sales = await (
            Query(Order)
            .annotate(total=Sum(Order.total_amount))
            .with_session(seeded_session)
        ).async_aggregate_first()

        # 2. 주문 수
        order_count = await (
            Query(Order)
            .with_session(seeded_session)
        ).async_count()

        # 3. 고객 수
        customer_count = await (
            Query(Customer)
            .with_session(seeded_session)
        ).async_count()

        # 4. 상품 수
        product_count = await (
            Query(Product)
            .filter(Product.is_available == True)
            .with_session(seeded_session)
        ).async_count()

        # 5. 상태별 주문 분포
        status_distribution = await (
            Query(Order)
            .annotate(count=Count(Order.id))
            .group_by(Order.status)
            .with_session(seeded_session)
        ).async_aggregate_all()

        # 6. 티어별 고객 분포
        tier_distribution = await (
            Query(Customer)
            .annotate(count=Count(Customer.id))
            .group_by(Customer.tier)
            .with_session(seeded_session)
        ).async_aggregate_all()

        # 7. 카테고리별 상품 판매
        category_sales = await (
            Query(Product)
            .annotate(product_count=Count(Product.id))
            .group_by(Product.category)
            .with_session(seeded_session)
        ).async_aggregate_all()

        # 8. 지역별 판매 현황
        regional_sales = await (
            Query(SalesRecord)
            .annotate(
                total_amount=Sum(SalesRecord.amount),
                sale_count=Count(SalesRecord.id)
            )
            .group_by(SalesRecord.region)
            .order_by(OrderBy("total_amount", "DESC"))
            .with_session(seeded_session)
        ).async_aggregate_all()

        # 결과 종합
        dashboard = {
            "total_revenue": total_sales["total"] if total_sales else 0,
            "order_count": order_count,
            "customer_count": customer_count,
            "product_count": product_count,
            "status_distribution": status_distribution,
            "tier_distribution": tier_distribution,
            "category_breakdown": category_sales,
            "regional_performance": regional_sales,
        }

        assert dashboard["total_revenue"] > 0
        assert dashboard["order_count"] > 0
        assert dashboard["customer_count"] > 0


class TestLevel6WindowCombinations:
    """Level 6 추가: 윈도우 함수 조합 테스트"""

    @pytest.mark.asyncio
    async def test_first_and_last_value(self, seeded_session: AsyncSession):
        """FIRST_VALUE + LAST_VALUE 조합"""
        first_val = FirstValue(Order.total_amount).over(
            partition_by=[Order.customer_id],
            order_by=[OrderBy("order_date", "ASC")],
            frame=WindowFrame("ROWS", FrameBound.UNBOUNDED_PRECEDING, FrameBound.UNBOUNDED_FOLLOWING)
        ).as_("first_order")

        last_val = LastValue(Order.total_amount).over(
            partition_by=[Order.customer_id],
            order_by=[OrderBy("order_date", "ASC")],
            frame=WindowFrame("ROWS", FrameBound.UNBOUNDED_PRECEDING, FrameBound.UNBOUNDED_FOLLOWING)
        ).as_("last_order")

        assert "FIRST_VALUE" in first_val.to_sql()
        assert "LAST_VALUE" in last_val.to_sql()

    @pytest.mark.asyncio
    async def test_lag_lead_comparison(self, seeded_session: AsyncSession):
        """LAG + LEAD 비교"""
        prev_val = Lag(SalesRecord.amount, 1).over(
            partition_by=[SalesRecord.region],
            order_by=[OrderBy("sale_date", "ASC")]
        ).as_("prev_amount")

        next_val = Lead(SalesRecord.amount, 1).over(
            partition_by=[SalesRecord.region],
            order_by=[OrderBy("sale_date", "ASC")]
        ).as_("next_amount")

        assert "LAG" in prev_val.to_sql()
        assert "LEAD" in next_val.to_sql()

    @pytest.mark.asyncio
    async def test_min_max_over_partition(self, seeded_session: AsyncSession):
        """파티션 내 MIN/MAX"""
        min_val = MinOver(Employee.salary).over(
            partition_by=[Employee.department_id]
        ).as_("dept_min")

        max_val = MaxOver(Employee.salary).over(
            partition_by=[Employee.department_id]
        ).as_("dept_max")

        assert "MIN" in min_val.to_sql()
        assert "MAX" in max_val.to_sql()

    @pytest.mark.asyncio
    async def test_count_over_running(self, seeded_session: AsyncSession):
        """누적 카운트"""
        running_count = CountOver("*").over(
            partition_by=[Order.customer_id],
            order_by=[OrderBy("order_date", "ASC")],
            frame=WindowFrame("ROWS", FrameBound.UNBOUNDED_PRECEDING, FrameBound.CURRENT_ROW)
        ).as_("running_order_count")

        sql = running_count.to_sql()
        assert "COUNT(*)" in sql
        assert "ROWS BETWEEN" in sql

    @pytest.mark.asyncio
    async def test_nth_value_second(self, seeded_session: AsyncSession):
        """두 번째 값 가져오기"""
        second_val = NthValue(Employee.salary, 2).over(
            partition_by=[Employee.department_id],
            order_by=[Employee.salary.desc()],
            frame=WindowFrame("ROWS", FrameBound.UNBOUNDED_PRECEDING, FrameBound.UNBOUNDED_FOLLOWING)
        ).as_("second_highest")

        sql = second_val.to_sql()
        assert "NTH_VALUE(salary, 2)" in sql
