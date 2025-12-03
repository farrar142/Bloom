"""Level 4: Window Functions - 윈도우 함수 테스트 (20개)

ROW_NUMBER, RANK, DENSE_RANK, LAG, LEAD, NTILE 등의 윈도우 함수를 테스트합니다.
"""

import pytest
from bloom.db import Query, OrderBy
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
    Order,
    SalesRecord,
    Score,
    AsyncSession,
)


class TestLevel4WindowFunctions:
    """Level 4: Window Functions - 윈도우 함수 20개"""

    # =========================================================================
    # 1-5: 순위 함수 (Ranking Functions)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_01_row_number_basic(self, seeded_session: AsyncSession):
        """1. ROW_NUMBER - 기본 행 번호"""
        row_num = RowNumber().over(
            order_by=[OrderBy("salary", "DESC")]
        ).as_("row_num")

        sql = row_num.to_sql()
        assert "ROW_NUMBER()" in sql
        assert "ORDER BY salary DESC" in sql
        assert "AS row_num" in sql

    @pytest.mark.asyncio
    async def test_02_row_number_partition(self, seeded_session: AsyncSession):
        """2. ROW_NUMBER - PARTITION BY"""
        row_num = RowNumber().over(
            partition_by=[Employee.department_id],
            order_by=[Employee.salary.desc()]
        ).as_("dept_rank")

        sql = row_num.to_sql()
        assert "ROW_NUMBER()" in sql
        assert "PARTITION BY" in sql
        assert "ORDER BY" in sql

    @pytest.mark.asyncio
    async def test_03_rank_basic(self, seeded_session: AsyncSession):
        """3. RANK - 동순위 시 다음 순위 건너뜀"""
        rank = Rank().over(
            order_by=[OrderBy("points", "DESC")]
        ).as_("rank")

        sql = rank.to_sql()
        assert "RANK()" in sql
        assert "ORDER BY points DESC" in sql

    @pytest.mark.asyncio
    async def test_04_dense_rank(self, seeded_session: AsyncSession):
        """4. DENSE_RANK - 동순위 시 건너뛰지 않음"""
        dense_rank = DenseRank().over(
            partition_by=[Score.game],
            order_by=[OrderBy("points", "DESC")]
        ).as_("dense_rank")

        sql = dense_rank.to_sql()
        assert "DENSE_RANK()" in sql
        assert "PARTITION BY" in sql

    @pytest.mark.asyncio
    async def test_05_ntile(self, seeded_session: AsyncSession):
        """5. NTILE - n개 그룹으로 분할"""
        quartile = NTile(4).over(
            order_by=[Employee.salary.desc()]
        ).as_("quartile")

        sql = quartile.to_sql()
        assert "NTILE(4)" in sql
        assert "ORDER BY" in sql

    # =========================================================================
    # 6-10: 백분위 및 분포 함수
    # =========================================================================

    @pytest.mark.asyncio
    async def test_06_percent_rank(self, seeded_session: AsyncSession):
        """6. PERCENT_RANK - 백분위 순위"""
        pct_rank = PercentRank().over(
            order_by=[Employee.performance_score.desc()]
        ).as_("percentile")

        sql = pct_rank.to_sql()
        assert "PERCENT_RANK()" in sql

    @pytest.mark.asyncio
    async def test_07_cume_dist(self, seeded_session: AsyncSession):
        """7. CUME_DIST - 누적 분포"""
        cume_dist = CumeDist().over(
            partition_by=[Employee.department_id],
            order_by=[Employee.salary.asc()]
        ).as_("cumulative_dist")

        sql = cume_dist.to_sql()
        assert "CUME_DIST()" in sql

    @pytest.mark.asyncio
    async def test_08_ntile_decile(self, seeded_session: AsyncSession):
        """8. NTILE(10) - 10분위"""
        decile = NTile(10).over(
            order_by=[Order.total_amount.desc()]
        ).as_("decile")

        sql = decile.to_sql()
        assert "NTILE(10)" in sql

    @pytest.mark.asyncio
    async def test_09_rank_with_ties(self, seeded_session: AsyncSession):
        """9. RANK - 동점 처리"""
        # Chess 게임에서 동점자 순위
        rank = Rank().over(
            partition_by=[Score.game],
            order_by=[OrderBy("points", "DESC")]
        ).as_("game_rank")

        sql = rank.to_sql()
        assert "RANK()" in sql
        assert "PARTITION BY" in sql

    @pytest.mark.asyncio
    async def test_10_dense_rank_multiple_partition(self, seeded_session: AsyncSession):
        """10. DENSE_RANK - 다중 파티션"""
        dense_rank = DenseRank().over(
            partition_by=[SalesRecord.region, SalesRecord.salesperson_id],
            order_by=[OrderBy("amount", "DESC")]
        ).as_("region_salesperson_rank")

        sql = dense_rank.to_sql()
        assert "DENSE_RANK()" in sql

    # =========================================================================
    # 11-15: 값 함수 (LAG, LEAD, FIRST/LAST_VALUE)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_11_lag_basic(self, seeded_session: AsyncSession):
        """11. LAG - 이전 행 값"""
        prev_amount = Lag(SalesRecord.amount, 1, 0).over(
            partition_by=[SalesRecord.region],
            order_by=[OrderBy("sale_date", "ASC")]
        ).as_("prev_amount")

        sql = prev_amount.to_sql()
        assert "LAG(amount, 1, 0)" in sql

    @pytest.mark.asyncio
    async def test_12_lead_basic(self, seeded_session: AsyncSession):
        """12. LEAD - 다음 행 값"""
        next_amount = Lead(SalesRecord.amount, 1).over(
            order_by=[OrderBy("sale_date", "ASC")]
        ).as_("next_amount")

        sql = next_amount.to_sql()
        # Lead는 offset 1이 기본값이므로 생략될 수 있음
        assert "LEAD(amount" in sql

    @pytest.mark.asyncio
    async def test_13_lag_offset_2(self, seeded_session: AsyncSession):
        """13. LAG - 2행 이전 값"""
        prev_2_amount = Lag(SalesRecord.amount, 2, 0).over(
            partition_by=[SalesRecord.region],
            order_by=[OrderBy("sale_date", "ASC")]
        ).as_("prev_2_amount")

        sql = prev_2_amount.to_sql()
        assert "LAG(amount, 2, 0)" in sql

    @pytest.mark.asyncio
    async def test_14_first_value(self, seeded_session: AsyncSession):
        """14. FIRST_VALUE - 윈도우 내 첫 번째 값"""
        first_order = FirstValue(Order.total_amount).over(
            partition_by=[Order.customer_id],
            order_by=[OrderBy("order_date", "ASC")]
        ).as_("first_order_amount")

        sql = first_order.to_sql()
        assert "FIRST_VALUE(total_amount)" in sql

    @pytest.mark.asyncio
    async def test_15_last_value(self, seeded_session: AsyncSession):
        """15. LAST_VALUE - 윈도우 내 마지막 값"""
        last_order = LastValue(Order.total_amount).over(
            partition_by=[Order.customer_id],
            order_by=[OrderBy("order_date", "ASC")],
            frame=WindowFrame("ROWS", FrameBound.UNBOUNDED_PRECEDING, FrameBound.UNBOUNDED_FOLLOWING)
        ).as_("last_order_amount")

        sql = last_order.to_sql()
        assert "LAST_VALUE(total_amount)" in sql
        assert "ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING" in sql

    # =========================================================================
    # 16-20: 윈도우 집계 함수
    # =========================================================================

    @pytest.mark.asyncio
    async def test_16_sum_over(self, seeded_session: AsyncSession):
        """16. SUM OVER - 누적 합계"""
        running_total = SumOver(SalesRecord.amount).over(
            partition_by=[SalesRecord.region],
            order_by=[OrderBy("sale_date", "ASC")]
        ).as_("running_total")

        sql = running_total.to_sql()
        assert "SUM(amount)" in sql
        assert "OVER" in sql

    @pytest.mark.asyncio
    async def test_17_avg_over(self, seeded_session: AsyncSession):
        """17. AVG OVER - 윈도우 평균"""
        avg_amount = AvgOver(Order.total_amount).over(
            partition_by=[Order.customer_id]
        ).as_("customer_avg")

        sql = avg_amount.to_sql()
        assert "AVG(total_amount)" in sql
        assert "PARTITION BY" in sql

    @pytest.mark.asyncio
    async def test_18_count_over(self, seeded_session: AsyncSession):
        """18. COUNT OVER - 파티션 내 개수"""
        order_count = CountOver("*").over(
            partition_by=[Order.customer_id]
        ).as_("customer_order_count")

        sql = order_count.to_sql()
        assert "COUNT(*)" in sql

    @pytest.mark.asyncio
    async def test_19_min_max_over(self, seeded_session: AsyncSession):
        """19. MIN/MAX OVER - 윈도우 내 최소/최대"""
        min_salary = MinOver(Employee.salary).over(
            partition_by=[Employee.department_id]
        ).as_("dept_min_salary")

        max_salary = MaxOver(Employee.salary).over(
            partition_by=[Employee.department_id]
        ).as_("dept_max_salary")

        assert "MIN(salary)" in min_salary.to_sql()
        assert "MAX(salary)" in max_salary.to_sql()

    @pytest.mark.asyncio
    async def test_20_nth_value(self, seeded_session: AsyncSession):
        """20. NTH_VALUE - N번째 값"""
        second_highest = NthValue(Employee.salary, 2).over(
            partition_by=[Employee.department_id],
            order_by=[Employee.salary.desc()],
            frame=WindowFrame("ROWS", FrameBound.UNBOUNDED_PRECEDING, FrameBound.UNBOUNDED_FOLLOWING)
        ).as_("second_highest_salary")

        sql = second_highest.to_sql()
        assert "NTH_VALUE(salary, 2)" in sql


class TestLevel4WindowFrames:
    """Level 4 추가: Window Frame 테스트"""

    @pytest.mark.asyncio
    async def test_window_frame_rows(self, seeded_session: AsyncSession):
        """윈도우 프레임 - ROWS"""
        frame = WindowFrame("ROWS", FrameBound.UNBOUNDED_PRECEDING, FrameBound.CURRENT_ROW)
        assert frame.to_sql() == "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW"

    @pytest.mark.asyncio
    async def test_window_frame_range(self, seeded_session: AsyncSession):
        """윈도우 프레임 - RANGE"""
        frame = WindowFrame("RANGE", FrameBound.UNBOUNDED_PRECEDING, FrameBound.UNBOUNDED_FOLLOWING)
        assert frame.to_sql() == "RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING"

    @pytest.mark.asyncio
    async def test_window_frame_n_preceding(self, seeded_session: AsyncSession):
        """윈도우 프레임 - N PRECEDING"""
        frame = WindowFrame("ROWS", FrameBound.preceding(3), FrameBound.CURRENT_ROW)
        assert frame.to_sql() == "ROWS BETWEEN 3 PRECEDING AND CURRENT ROW"

    @pytest.mark.asyncio
    async def test_window_frame_n_following(self, seeded_session: AsyncSession):
        """윈도우 프레임 - N FOLLOWING"""
        frame = WindowFrame("ROWS", FrameBound.CURRENT_ROW, FrameBound.following(2))
        assert frame.to_sql() == "ROWS BETWEEN CURRENT ROW AND 2 FOLLOWING"

    @pytest.mark.asyncio
    async def test_moving_average_frame(self, seeded_session: AsyncSession):
        """이동 평균 프레임 (3일)"""
        moving_avg = AvgOver(SalesRecord.amount).over(
            partition_by=[SalesRecord.region],
            order_by=[OrderBy("sale_date", "ASC")],
            frame=WindowFrame("ROWS", FrameBound.preceding(2), FrameBound.CURRENT_ROW)
        ).as_("moving_avg_3")

        sql = moving_avg.to_sql()
        assert "AVG(amount)" in sql
        assert "ROWS BETWEEN 2 PRECEDING AND CURRENT ROW" in sql
