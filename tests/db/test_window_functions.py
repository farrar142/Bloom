"""Tests for Window Functions"""

import pytest

from bloom.db import (
    Entity,
    Column,
    PrimaryKey,
    Query,
    OrderBy,
    # Window functions
    FrameBound,
    WindowFrame,
    WindowSpec,
    WindowFunction,
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
from bloom.db.session import SessionFactory
from bloom.db.backends.sqlite import SQLiteBackend


# =============================================================================
# Test Entities
# =============================================================================


@Entity
class WfUser:
    """사용자 엔티티 (Window Function 테스트용)"""

    __tablename__ = "wf_user"

    id = PrimaryKey()
    name = Column()
    department = Column()


@Entity
class WfSale:
    """매출 엔티티 (Window Function 테스트용)"""

    __tablename__ = "wf_sale"

    id = PrimaryKey()
    user_id = Column()
    amount = Column()
    sale_date = Column()


@Entity
class WfScore:
    """점수 엔티티 (Window Function 테스트용)"""

    __tablename__ = "wf_score"

    id = PrimaryKey()
    user_id = Column()
    subject = Column()
    score = Column()


# =============================================================================
# FrameBound Tests
# =============================================================================


class TestFrameBound:
    """FrameBound 테스트"""

    def test_constants(self):
        """상수 값 테스트"""
        assert FrameBound.UNBOUNDED_PRECEDING == "UNBOUNDED PRECEDING"
        assert FrameBound.CURRENT_ROW == "CURRENT ROW"
        assert FrameBound.UNBOUNDED_FOLLOWING == "UNBOUNDED FOLLOWING"

    def test_preceding(self):
        """N PRECEDING 테스트"""
        assert FrameBound.preceding(1) == "1 PRECEDING"
        assert FrameBound.preceding(3) == "3 PRECEDING"

    def test_following(self):
        """N FOLLOWING 테스트"""
        assert FrameBound.following(1) == "1 FOLLOWING"
        assert FrameBound.following(5) == "5 FOLLOWING"


# =============================================================================
# WindowFrame Tests
# =============================================================================


class TestWindowFrame:
    """WindowFrame 테스트"""

    def test_default_frame(self):
        """기본 프레임 테스트"""
        frame = WindowFrame()
        sql = frame.to_sql()
        assert sql == "RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW"

    def test_rows_frame(self):
        """ROWS 프레임 테스트"""
        frame = WindowFrame(
            frame_type="ROWS",
            start=FrameBound.UNBOUNDED_PRECEDING,
            end=FrameBound.UNBOUNDED_FOLLOWING,
        )
        sql = frame.to_sql()
        assert sql == "ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING"

    def test_sliding_window(self):
        """슬라이딩 윈도우 테스트"""
        frame = WindowFrame(
            frame_type="ROWS",
            start=FrameBound.preceding(2),
            end=FrameBound.following(2),
        )
        sql = frame.to_sql()
        assert sql == "ROWS BETWEEN 2 PRECEDING AND 2 FOLLOWING"


# =============================================================================
# WindowSpec Tests
# =============================================================================


class TestWindowSpec:
    """WindowSpec 테스트"""

    def test_empty_spec(self):
        """빈 스펙 테스트"""
        spec = WindowSpec()
        sql = spec.to_sql()
        assert sql == "OVER ()"

    def test_partition_by_only(self):
        """PARTITION BY만 있는 경우"""
        spec = WindowSpec(partition_by=["user_id"])
        sql = spec.to_sql()
        assert 'PARTITION BY "user_id"' in sql

    def test_order_by_only(self):
        """ORDER BY만 있는 경우"""
        spec = WindowSpec(order_by=[OrderBy("created_at", "DESC")])
        sql = spec.to_sql()
        assert "ORDER BY created_at DESC" in sql

    def test_partition_and_order(self):
        """PARTITION BY + ORDER BY"""
        spec = WindowSpec(
            partition_by=["department"],
            order_by=[OrderBy("salary", "DESC")],
        )
        sql = spec.to_sql()
        assert 'PARTITION BY "department"' in sql
        assert "ORDER BY salary DESC" in sql

    def test_with_frame(self):
        """프레임 포함 테스트"""
        spec = WindowSpec(
            order_by=[OrderBy("date", "ASC")],
            frame=WindowFrame("ROWS", FrameBound.preceding(1), FrameBound.CURRENT_ROW),
        )
        sql = spec.to_sql()
        assert "ROWS BETWEEN 1 PRECEDING AND CURRENT ROW" in sql

    def test_partition_by_with_field_expression(self):
        """FieldExpression으로 partition_by"""
        spec = WindowSpec(partition_by=[WfSale.user_id])
        sql = spec.to_sql()
        assert 'PARTITION BY "user_id"' in sql


# =============================================================================
# Ranking Functions Tests
# =============================================================================


class TestRankingFunctions:
    """순위 함수 테스트"""

    def test_row_number_basic(self):
        """ROW_NUMBER 기본 테스트"""
        wf = RowNumber()
        assert wf.to_sql() == "ROW_NUMBER()"

    def test_row_number_with_over(self):
        """ROW_NUMBER with OVER"""
        wf = RowNumber().over(order_by=[OrderBy("created_at", "ASC")])
        sql = wf.to_sql()
        assert "ROW_NUMBER()" in sql
        assert "OVER" in sql
        assert "ORDER BY created_at ASC" in sql

    def test_row_number_with_alias(self):
        """ROW_NUMBER with alias"""
        wf = RowNumber().over(order_by=[OrderBy("id", "ASC")]).as_("rn")
        sql = wf.to_sql()
        assert "AS rn" in sql

    def test_rank_basic(self):
        """RANK 기본 테스트"""
        wf = Rank().over(order_by=[OrderBy("score", "DESC")])
        sql = wf.to_sql()
        assert "RANK()" in sql
        assert "ORDER BY score DESC" in sql

    def test_dense_rank_basic(self):
        """DENSE_RANK 기본 테스트"""
        wf = DenseRank().over(order_by=[OrderBy("points", "DESC")])
        sql = wf.to_sql()
        assert "DENSE_RANK()" in sql

    def test_ntile(self):
        """NTILE 테스트"""
        wf = NTile(4).over(order_by=[OrderBy("score", "DESC")])
        sql = wf.to_sql()
        assert "NTILE(4)" in sql

    def test_percent_rank(self):
        """PERCENT_RANK 테스트"""
        wf = PercentRank().over(order_by=[OrderBy("amount", "ASC")])
        sql = wf.to_sql()
        assert "PERCENT_RANK()" in sql

    def test_cume_dist(self):
        """CUME_DIST 테스트"""
        wf = CumeDist().over(order_by=[OrderBy("value", "ASC")])
        sql = wf.to_sql()
        assert "CUME_DIST()" in sql

    def test_rank_with_partition(self):
        """RANK with PARTITION BY"""
        wf = Rank().over(
            partition_by=["department"],
            order_by=[OrderBy("salary", "DESC")],
        )
        sql = wf.to_sql()
        assert "RANK()" in sql
        assert 'PARTITION BY "department"' in sql
        assert "ORDER BY salary DESC" in sql


# =============================================================================
# Value Functions Tests
# =============================================================================


class TestValueFunctions:
    """값 함수 테스트"""

    def test_lag_basic(self):
        """LAG 기본 테스트"""
        wf = Lag("amount").over(order_by=[OrderBy("date", "ASC")])
        sql = wf.to_sql()
        assert "LAG(amount)" in sql

    def test_lag_with_offset(self):
        """LAG with offset"""
        wf = Lag("amount", offset=2).over(order_by=[OrderBy("date", "ASC")])
        sql = wf.to_sql()
        assert "LAG(amount, 2)" in sql

    def test_lag_with_default(self):
        """LAG with default value"""
        wf = Lag("amount", offset=1, default=0).over(order_by=[OrderBy("date", "ASC")])
        sql = wf.to_sql()
        assert "LAG(amount, 1, 0)" in sql

    def test_lag_with_field_expression(self):
        """LAG with FieldExpression"""
        wf = Lag(WfSale.amount).over(order_by=[OrderBy("sale_date", "ASC")])
        sql = wf.to_sql()
        assert "LAG(amount)" in sql

    def test_lead_basic(self):
        """LEAD 기본 테스트"""
        wf = Lead("price").over(order_by=[OrderBy("date", "ASC")])
        sql = wf.to_sql()
        assert "LEAD(price)" in sql

    def test_lead_with_offset_and_default(self):
        """LEAD with offset and default"""
        wf = Lead("value", offset=2, default=-1).over(order_by=[OrderBy("seq", "ASC")])
        sql = wf.to_sql()
        assert "LEAD(value, 2, -1)" in sql

    def test_first_value(self):
        """FIRST_VALUE 테스트"""
        wf = FirstValue("amount").over(
            partition_by=["user_id"],
            order_by=[OrderBy("date", "ASC")],
        )
        sql = wf.to_sql()
        assert "FIRST_VALUE(amount)" in sql
        assert 'PARTITION BY "user_id"' in sql

    def test_last_value(self):
        """LAST_VALUE 테스트"""
        wf = LastValue("amount").over(
            partition_by=["user_id"],
            order_by=[OrderBy("date", "ASC")],
            frame=WindowFrame(
                "ROWS",
                FrameBound.UNBOUNDED_PRECEDING,
                FrameBound.UNBOUNDED_FOLLOWING,
            ),
        )
        sql = wf.to_sql()
        assert "LAST_VALUE(amount)" in sql
        assert "ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING" in sql

    def test_nth_value(self):
        """NTH_VALUE 테스트"""
        wf = NthValue("score", n=3).over(order_by=[OrderBy("rank", "ASC")])
        sql = wf.to_sql()
        assert "NTH_VALUE(score, 3)" in sql


# =============================================================================
# Aggregate Window Functions Tests
# =============================================================================


class TestAggregateWindowFunctions:
    """집계 윈도우 함수 테스트"""

    def test_sum_over(self):
        """SUM OVER 테스트"""
        wf = SumOver("amount").over(partition_by=["user_id"])
        sql = wf.to_sql()
        assert "SUM(amount)" in sql
        assert 'PARTITION BY "user_id"' in sql

    def test_sum_over_running_total(self):
        """SUM OVER 누적 합계"""
        wf = (
            SumOver("amount")
            .over(
                partition_by=["user_id"],
                order_by=[OrderBy("date", "ASC")],
            )
            .as_("running_total")
        )
        sql = wf.to_sql()
        assert "SUM(amount)" in sql
        assert "ORDER BY date ASC" in sql
        assert "AS running_total" in sql

    def test_avg_over(self):
        """AVG OVER 테스트"""
        wf = (
            AvgOver("price")
            .over(
                partition_by=["category"],
                frame=WindowFrame(
                    "ROWS", FrameBound.preceding(2), FrameBound.CURRENT_ROW
                ),
            )
            .as_("moving_avg")
        )
        sql = wf.to_sql()
        assert "AVG(price)" in sql
        assert "ROWS BETWEEN 2 PRECEDING AND CURRENT ROW" in sql
        assert "AS moving_avg" in sql

    def test_count_over(self):
        """COUNT OVER 테스트"""
        wf = CountOver("*").over(partition_by=["department"]).as_("dept_count")
        sql = wf.to_sql()
        assert "COUNT(*)" in sql
        assert 'PARTITION BY "department"' in sql
        assert "AS dept_count" in sql

    def test_count_over_with_field(self):
        """COUNT OVER with field"""
        wf = CountOver(WfSale.id).over(partition_by=["user_id"])
        sql = wf.to_sql()
        assert "COUNT(id)" in sql

    def test_min_over(self):
        """MIN OVER 테스트"""
        wf = MinOver("price").over(partition_by=["category"])
        sql = wf.to_sql()
        assert "MIN(price)" in sql

    def test_max_over(self):
        """MAX OVER 테스트"""
        wf = MaxOver("price").over(partition_by=["category"])
        sql = wf.to_sql()
        assert "MAX(price)" in sql


# =============================================================================
# Complex Window Function Tests
# =============================================================================


class TestComplexWindowFunctions:
    """복잡한 윈도우 함수 조합 테스트"""

    def test_multiple_partitions(self):
        """여러 파티션 컬럼"""
        wf = RowNumber().over(
            partition_by=["department", "year"],
            order_by=[OrderBy("salary", "DESC")],
        )
        sql = wf.to_sql()
        assert 'PARTITION BY "department", "year"' in sql

    def test_multiple_order_by(self):
        """여러 정렬 컬럼"""
        wf = Rank().over(
            order_by=[OrderBy("score", "DESC"), OrderBy("name", "ASC")],
        )
        sql = wf.to_sql()
        assert "ORDER BY score DESC, name ASC" in sql

    def test_field_expression_in_over(self):
        """FieldExpression으로 OVER 설정"""
        wf = RowNumber().over(
            partition_by=[WfSale.user_id],
            order_by=[WfSale.amount.desc()],
        )
        sql = wf.to_sql()
        assert 'PARTITION BY "user_id"' in sql
        assert "ORDER BY amount DESC" in sql

    def test_output_name_with_alias(self):
        """output_name with alias"""
        wf = RowNumber().as_("rn")
        assert wf.output_name == "rn"

    def test_output_name_without_alias(self):
        """output_name without alias"""
        wf = RowNumber()
        assert wf.output_name == "row_number"


# =============================================================================
# Integration Tests
# =============================================================================


class TestWindowFunctionIntegration:
    """윈도우 함수 통합 테스트 (SQL 생성 확인)"""

    def test_row_number_full_sql(self):
        """ROW_NUMBER 전체 SQL 생성"""
        wf = (
            RowNumber()
            .over(
                partition_by=["user_id"],
                order_by=[OrderBy("created_at", "DESC")],
            )
            .as_("rn")
        )
        sql = wf.to_sql()
        expected_parts = [
            "ROW_NUMBER()",
            'PARTITION BY "user_id"',
            "ORDER BY created_at DESC",
            "AS rn",
        ]
        for part in expected_parts:
            assert part in sql

    def test_running_total_sql(self):
        """누적 합계 SQL 생성"""
        wf = (
            SumOver("amount")
            .over(
                partition_by=["user_id"],
                order_by=[OrderBy("date", "ASC")],
                frame=WindowFrame(
                    "ROWS", FrameBound.UNBOUNDED_PRECEDING, FrameBound.CURRENT_ROW
                ),
            )
            .as_("running_total")
        )
        sql = wf.to_sql()
        assert "SUM(amount)" in sql
        assert "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW" in sql

    def test_moving_average_sql(self):
        """이동 평균 SQL 생성"""
        wf = (
            AvgOver("price")
            .over(
                order_by=[OrderBy("date", "ASC")],
                frame=WindowFrame(
                    "ROWS", FrameBound.preceding(6), FrameBound.CURRENT_ROW
                ),
            )
            .as_("ma7")
        )
        sql = wf.to_sql()
        assert "AVG(price)" in sql
        assert "ROWS BETWEEN 6 PRECEDING AND CURRENT ROW" in sql
        assert "AS ma7" in sql

    def test_lag_lead_comparison(self):
        """LAG/LEAD 비교"""
        lag = Lag("value", 1, 0).over(order_by=[OrderBy("seq", "ASC")])
        lead = Lead("value", 1, 0).over(order_by=[OrderBy("seq", "ASC")])

        lag_sql = lag.to_sql()
        lead_sql = lead.to_sql()

        assert "LAG(value, 1, 0)" in lag_sql
        assert "LEAD(value, 1, 0)" in lead_sql

    def test_percentile_quartile(self):
        """백분위/사분위 계산"""
        quartile = NTile(4).over(order_by=[OrderBy("score", "DESC")]).as_("quartile")
        percent = PercentRank().over(order_by=[OrderBy("score", "DESC")]).as_("pct")

        assert "NTILE(4)" in quartile.to_sql()
        assert "PERCENT_RANK()" in percent.to_sql()
