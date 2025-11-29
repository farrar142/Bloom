"""Bloom Framework Task 예제 앱

Celery 스타일의 @Task 데코레이터를 사용한 비동기 태스크 처리 예제입니다.

실행 방법:
    uv run python examples/task_example_app.py

기능:
    - 직접 호출: 동기적으로 태스크 실행
    - 백그라운드 실행: delay()로 비동기 실행 후 결과 대기
    - 스케줄 실행: schedule()로 주기적 실행 등록
"""

import asyncio
import time
from datetime import datetime

from bloom import Application, Component
from bloom.core.decorators import Factory
from bloom.core.advice import MethodAdvice, MethodAdviceRegistry
from bloom.task import Task, TaskBackend, AsyncioTaskBackend, TaskMethodAdvice


# ============================================================================
# 1. 태스크 백엔드 및 어드바이스 설정
# ============================================================================


@Component
class TaskConfig:
    """태스크 시스템 설정"""

    @Factory
    def task_backend(self) -> TaskBackend:
        """비동기 태스크 백엔드 생성 (최대 4개 워커)"""
        return AsyncioTaskBackend(max_workers=4)

    @Factory
    def advice_registry(
        self, backend: TaskBackend, *advices: MethodAdvice
    ) -> MethodAdviceRegistry:
        """메서드 어드바이스 레지스트리 생성"""
        registry = MethodAdviceRegistry()
        # TaskMethodAdvice 등록 (동적 인스턴스 지원)
        registry.register(TaskMethodAdvice(backend))
        # 기타 어드바이스 등록
        for advice in advices:
            registry.register(advice)
        return registry


# ============================================================================
# 2. 이메일 서비스 (태스크 사용 예제)
# ============================================================================


@Component
class EmailService:
    """이메일 발송 서비스 - @Task로 비동기 처리"""

    @Task
    def send_email(self, to: str, subject: str, body: str) -> dict:
        """이메일 발송 (시뮬레이션)

        직접 호출: result = service.send_email("user@example.com", "Hello", "Body")
        백그라운드: task_result = service.send_email.delay("user@example.com", "Hello", "Body")
        """
        # 실제로는 SMTP 발송 로직
        time.sleep(0.1)  # 발송 시뮬레이션
        return {
            "to": to,
            "subject": subject,
            "sent_at": datetime.now().isoformat(),
            "status": "sent",
        }

    @Task(name="bulk-email", max_retries=3)
    def send_bulk_email(self, recipients: list[str], subject: str, body: str) -> dict:
        """대량 이메일 발송 (재시도 3회)"""
        results = []
        for recipient in recipients:
            result = self.send_email(recipient, subject, body)
            results.append(result)
        return {
            "total": len(recipients),
            "sent": len(results),
            "status": "completed",
        }


# ============================================================================
# 3. 리포트 생성 서비스 (비동기 태스크 예제)
# ============================================================================


@Component
class ReportService:
    """리포트 생성 서비스 - 비동기 처리가 필요한 무거운 작업"""

    @Task(name="daily-report")
    async def generate_daily_report(self, date: str) -> dict:
        """일일 리포트 생성 (비동기)

        무거운 작업을 비동기로 처리:
        task_result = service.generate_daily_report.delay("2024-01-15")
        report = task_result.get(timeout=30)
        """
        await asyncio.sleep(0.5)  # 시뮬레이션
        return {
            "date": date,
            "generated_at": datetime.now().isoformat(),
            "metrics": {
                "users": 1500,
                "orders": 230,
                "revenue": 45000.0,
            },
            "status": "completed",
        }

    @Task
    async def generate_custom_report(self, start_date: str, end_date: str) -> dict:
        """커스텀 기간 리포트 생성"""
        await asyncio.sleep(0.3)
        return {
            "period": f"{start_date} ~ {end_date}",
            "generated_at": datetime.now().isoformat(),
            "status": "completed",
        }


# ============================================================================
# 4. 알림 서비스 (스케줄 태스크 예제)
# ============================================================================


@Component
class NotificationService:
    """알림 서비스 - 주기적 실행 예제"""

    @Task(name="health-check-notification")
    def check_and_notify(self) -> dict:
        """헬스체크 및 알림 (주기적 실행용)

        스케줄 등록:
        scheduled = service.check_and_notify.schedule(fixed_rate=60)  # 60초마다
        scheduled.pause()   # 일시정지
        scheduled.resume()  # 재개
        scheduled.cancel()  # 취소
        """
        return {
            "checked_at": datetime.now().isoformat(),
            "status": "healthy",
            "message": "All systems operational",
        }


# ============================================================================
# 애플리케이션 초기화 및 예제 실행
# ============================================================================


def main():
    """예제 실행"""
    print("=" * 60)
    print("Bloom Framework - Task 예제")
    print("=" * 60)

    # 현재 모듈 가져오기
    import sys

    current_module = sys.modules[__name__]

    # 애플리케이션 초기화
    app = Application("task-example")
    app.scan(current_module).ready()

    # 서비스 인스턴스 가져오기
    email_service = app.manager.get_instance(EmailService)
    report_service = app.manager.get_instance(ReportService)
    notification_service = app.manager.get_instance(NotificationService)

    # -------------------------------------------------------------------------
    # 1. 직접 호출 (동기)
    # -------------------------------------------------------------------------
    print("\n[1] 직접 호출 (동기)")
    print(email_service.send_email)
    result = email_service.send_email("user@example.com", "Hello", "Welcome!")
    print(f"   결과: {result}")

    # -------------------------------------------------------------------------
    # 2. 백그라운드 실행 (delay)
    # -------------------------------------------------------------------------
    print("\n[2] 백그라운드 실행 (delay)")
    task_result = email_service.send_email.delay(
        "async@example.com", "Async Hello", "This is async!"
    )
    print(f"   태스크 ID: {task_result.task_id}")
    print(f"   완료 여부: {task_result.ready()}")

    # 결과 대기
    result = task_result.get(timeout=5.0)
    print(f"   결과: {result}")
    print(f"   성공 여부: {task_result.successful()}")

    # -------------------------------------------------------------------------
    # 3. 대량 이메일 발송 (백그라운드)
    # -------------------------------------------------------------------------
    print("\n[3] 대량 이메일 발송")
    recipients = ["user1@example.com", "user2@example.com", "user3@example.com"]
    task_result = email_service.send_bulk_email.delay(
        recipients, "Newsletter", "Monthly update!"
    )
    result = task_result.get(timeout=10.0)
    print(f"   결과: {result}")

    # -------------------------------------------------------------------------
    # 4. 비동기 태스크 (async def)
    # -------------------------------------------------------------------------
    print("\n[4] 비동기 리포트 생성")
    task_result = report_service.generate_daily_report.delay("2024-01-15")
    report = task_result.get(timeout=10.0)
    print(f"   리포트: {report}")

    # -------------------------------------------------------------------------
    # 5. 스케줄 등록 (예제)
    # -------------------------------------------------------------------------
    print("\n[5] 스케줄 등록 (3초 후 취소)")

    # 1초마다 실행
    scheduled = notification_service.check_and_notify.schedule(fixed_rate=1.0)
    print(f"   스케줄 이름: {scheduled.name}")

    # 3초 동안 실행
    time.sleep(3.2)

    # 스케줄 취소
    scheduled.cancel()
    print("   스케줄 취소됨")

    # -------------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("예제 완료!")
    print("=" * 60)


if __name__ == "__main__":
    main()
