"""Trigger - 스케줄 트리거 정의

Trigger는 스케줄된 작업의 실행 시점을 결정합니다.

종류:
    - FixedRateTrigger: 시작 시점 기준 고정 간격
    - FixedDelayTrigger: 완료 시점 기준 고정 지연
    - CronTrigger: cron 표현식 기반
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any


class Trigger(ABC):
    """트리거 추상 클래스"""

    @abstractmethod
    def next_execution_time(self, last_execution: datetime | None = None) -> datetime:
        """
        다음 실행 시간 계산

        Args:
            last_execution: 마지막 실행 시간 (없으면 첫 실행)

        Returns:
            다음 실행 시간
        """
        pass

    @abstractmethod
    def __repr__(self) -> str:
        pass


class FixedRateTrigger(Trigger):
    """
    고정 간격 트리거

    이전 작업의 시작 시점부터 고정 간격으로 실행합니다.

    Example:
        FixedRateTrigger(seconds=30)  # 30초마다
        FixedRateTrigger(minutes=5)   # 5분마다
        FixedRateTrigger(hours=1)     # 1시간마다
    """

    def __init__(
        self,
        seconds: float = 0,
        minutes: float = 0,
        hours: float = 0,
        initial_delay: float = 0,
    ):
        total_seconds = seconds + minutes * 60 + hours * 3600
        if total_seconds <= 0:
            raise ValueError("Interval must be positive")

        self._interval = timedelta(seconds=total_seconds)
        self._initial_delay = initial_delay

    @property
    def interval(self) -> timedelta:
        return self._interval

    @property
    def initial_delay(self) -> float:
        return self._initial_delay

    def next_execution_time(self, last_execution: datetime | None = None) -> datetime:
        now = datetime.now()
        if last_execution is None:
            # 첫 실행: initial_delay가 0이면 즉시 실행 (과거 시간 반환)
            if self._initial_delay == 0:
                return now - timedelta(seconds=1)  # 과거 시간으로 즉시 트리거
            return now + timedelta(seconds=self._initial_delay)
        # 이후: 마지막 실행 + 간격
        return last_execution + self._interval

    def __repr__(self) -> str:
        return f"FixedRateTrigger(interval={self._interval})"


class FixedDelayTrigger(Trigger):
    """
    고정 지연 트리거

    이전 작업의 완료 시점부터 고정 지연 후 실행합니다.

    Example:
        FixedDelayTrigger(seconds=10)  # 완료 후 10초 후
    """

    def __init__(
        self,
        seconds: float = 0,
        minutes: float = 0,
        hours: float = 0,
        initial_delay: float = 0,
    ):
        total_seconds = seconds + minutes * 60 + hours * 3600
        if total_seconds <= 0:
            raise ValueError("Delay must be positive")

        self._delay = timedelta(seconds=total_seconds)
        self._initial_delay = initial_delay

    @property
    def delay(self) -> timedelta:
        return self._delay

    @property
    def initial_delay(self) -> float:
        return self._initial_delay

    def next_execution_time(self, last_completion: datetime | None = None) -> datetime:
        now = datetime.now()
        if last_completion is None:
            # 첫 실행: initial_delay가 0이면 즉시 실행
            if self._initial_delay == 0:
                return now - timedelta(seconds=1)  # 과거 시간으로 즉시 트리거
            return now + timedelta(seconds=self._initial_delay)
        return last_completion + self._delay

    def __repr__(self) -> str:
        return f"FixedDelayTrigger(delay={self._delay})"


class CronTrigger(Trigger):
    """
    Cron 표현식 트리거

    5개 필드: 분 시 일 월 요일

    Example:
        CronTrigger("0 * * * *")      # 매시 0분
        CronTrigger("*/5 * * * *")    # 5분마다
        CronTrigger("0 9 * * 1-5")    # 평일 9시
    """

    def __init__(self, expression: str):
        self._expression = expression
        self._fields = self._parse(expression)

    @property
    def expression(self) -> str:
        return self._expression

    def _parse(self, expression: str) -> list[str]:
        fields = expression.strip().split()
        if len(fields) != 5:
            raise ValueError(
                f"Cron expression must have 5 fields (minute hour day month weekday), got {len(fields)}"
            )
        return fields

    def _match_field(self, field: str, value: int, max_value: int) -> bool:
        """필드가 값과 매치되는지 확인"""
        if field == "*":
            return True

        # */n 형식
        if field.startswith("*/"):
            step = int(field[2:])
            return value % step == 0

        # 범위 (1-5)
        if "-" in field:
            start, end = map(int, field.split("-"))
            return start <= value <= end

        # 리스트 (1,3,5)
        if "," in field:
            values = [int(v) for v in field.split(",")]
            return value in values

        # 단일 값
        return int(field) == value

    def next_execution_time(self, last_execution: datetime | None = None) -> datetime:
        now = datetime.now()
        if last_execution is None:
            start = now
        else:
            start = max(now, last_execution)

        # 다음 분부터 시작 (현재 분은 이미 지남)
        candidate = start.replace(second=0, microsecond=0) + timedelta(minutes=1)

        # 최대 1년까지 검색
        max_iterations = 365 * 24 * 60
        for _ in range(max_iterations):
            if self._matches(candidate):
                return candidate
            candidate += timedelta(minutes=1)

        raise RuntimeError("Could not find next execution time within 1 year")

    def _matches(self, dt: datetime) -> bool:
        """datetime이 cron 표현식과 매치되는지 확인"""
        minute, hour, day, month, weekday = self._fields

        return (
            self._match_field(minute, dt.minute, 59)
            and self._match_field(hour, dt.hour, 23)
            and self._match_field(day, dt.day, 31)
            and self._match_field(month, dt.month, 12)
            and self._match_field(weekday, dt.weekday(), 6)  # 0=Monday
        )

    def __repr__(self) -> str:
        return f"CronTrigger('{self._expression}')"
