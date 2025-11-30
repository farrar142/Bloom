"""Bloom Framework 분산 태스크 예제

Redis 또는 InMemory 브로커를 통한 분산 태스크 처리 예제입니다.

실행 방법:
    # 1. 워커 실행 (별도 터미널)
    uv run bloom worker examples.distributed_task_example:app.queue -c 4

    # 또는 Python -m으로 실행
    uv run python -m bloom worker examples.distributed_task_example:app.queue

    # 2. 태스크 제출 (다른 터미널)
    uv run python examples/distributed_task_example.py

아키텍처:
    ┌─────────────────┐          ┌─────────────────┐
    │  Producer       │          │  Worker         │
    │  (이 스크립트)  │          │  (bloom worker) │
    │                 │          │                 │
    │  delay() 호출   │          │  태스크 실행    │
    └────────┬────────┘          └────────┬────────┘
             │                            │
             ▼                            ▼
        ┌────────────────────────────────────┐
        │          InMemory Broker           │
        │   (또는 RedisBroker for prod)      │
        └────────────────────────────────────┘
"""

import asyncio
import time
from datetime import datetime

from bloom import Application, Component
from bloom.core.decorators import Factory
from bloom.task import (
    Task,
    DistributedTaskBackend,
    InMemoryBroker,
    # RedisBroker,  # 프로덕션용
)


# ============================================================================
# 1. 태스크 백엔드 설정
# ============================================================================


@Component
class TaskConfig:
    """분산 태스크 시스템 설정"""

    @Factory
    def task_backend(self) -> DistributedTaskBackend:
        """분산 태스크 백엔드 생성

        개발 환경: InMemoryBroker
        프로덕션: RedisBroker
        """
        # 개발용 인메모리 브로커
        broker = InMemoryBroker()

        # 프로덕션용 Redis 브로커
        # broker = RedisBroker("redis://localhost:6379/0")

        return DistributedTaskBackend(
            broker=broker,
            queue="default",
            worker_count=4,
        )


# ============================================================================
# 2. 이메일 서비스
# ============================================================================


@Component
class EmailService:
    """이메일 발송 서비스"""

    @Task(name="send_email")
    def send_email(self, to: str, subject: str, body: str) -> dict:
        """이메일 발송 (시뮬레이션)"""
        time.sleep(0.5)  # 발송 시뮬레이션
        result = {
            "to": to,
            "subject": subject,
            "sent_at": datetime.now().isoformat(),
            "status": "sent",
        }
        print(f"[EmailService] 이메일 발송 완료: {to}")
        return result

    @Task(name="send_bulk_email", max_retries=3)
    def send_bulk_email(self, recipients: list[str], subject: str) -> dict:
        """대량 이메일 발송"""
        sent = 0
        for recipient in recipients:
            time.sleep(0.2)
            sent += 1
            print(f"[EmailService] 발송 중... ({sent}/{len(recipients)})")

        return {
            "total": len(recipients),
            "sent": sent,
            "completed_at": datetime.now().isoformat(),
        }


# ============================================================================
# 3. 리포트 서비스
# ============================================================================


@Component
class ReportService:
    """리포트 생성 서비스"""

    @Task(name="generate_report")
    async def generate_report(self, report_type: str, date: str) -> dict:
        """리포트 생성 (비동기)"""
        print(f"[ReportService] 리포트 생성 시작: {report_type} - {date}")
        await asyncio.sleep(2)  # 무거운 작업 시뮬레이션

        result = {
            "type": report_type,
            "date": date,
            "generated_at": datetime.now().isoformat(),
            "data": {
                "users": 1500,
                "orders": 230,
                "revenue": 45000.0,
            },
        }
        print(f"[ReportService] 리포트 생성 완료: {report_type}")
        return result


# ============================================================================
# 4. 알림 서비스
# ============================================================================


@Component
class NotificationService:
    """알림 서비스"""

    @Task(name="send_push_notification")
    def send_push(self, user_id: int, title: str, message: str) -> dict:
        """푸시 알림 발송"""
        time.sleep(0.3)
        result = {
            "user_id": user_id,
            "title": title,
            "sent_at": datetime.now().isoformat(),
            "status": "delivered",
        }
        print(f"[NotificationService] 푸시 발송 완료: user={user_id}")
        return result


# ============================================================================
# 애플리케이션 초기화 (모듈 레벨 - 워커에서 import 가능)
# ============================================================================

# 현재 모듈
import sys

_current_module = sys.modules[__name__]

# Application 생성 및 초기화
app = Application("distributed-task-example")
app.scan(_current_module).ready()


# ============================================================================
# 태스크 제출 (Producer)
# ============================================================================


async def submit_tasks():
    """태스크를 브로커에 제출"""
    print("=" * 60)
    print("분산 태스크 예제 - Producer")
    print("=" * 60)

    # 서비스 인스턴스 가져오기
    email_service = app.manager.get_instance(EmailService)
    report_service = app.manager.get_instance(ReportService)
    notification_service = app.manager.get_instance(NotificationService)

    # 백엔드 시작 (브로커 연결)
    backend = app.manager.get_instance(DistributedTaskBackend)
    await backend.start()

    print("\n[1] 이메일 태스크 제출")
    task1 = email_service.send_email.delay(
        "user@example.com",
        "환영합니다!",
        "Bloom Framework에 오신 것을 환영합니다.",
    )
    print(f"    태스크 ID: {task1.task_id}")

    print("\n[2] 대량 이메일 태스크 제출")
    task2 = email_service.send_bulk_email.delay(
        ["user1@example.com", "user2@example.com", "user3@example.com"],
        "공지사항",
    )
    print(f"    태스크 ID: {task2.task_id}")

    print("\n[3] 리포트 생성 태스크 제출")
    task3 = report_service.generate_report.delay("daily", "2024-01-15")
    print(f"    태스크 ID: {task3.task_id}")

    print("\n[4] 푸시 알림 태스크 제출")
    task4 = notification_service.send_push.delay(
        123, "새 메시지", "새 메시지가 도착했습니다."
    )
    print(f"    태스크 ID: {task4.task_id}")

    print("\n" + "-" * 60)
    print("태스크 제출 완료!")
    print("워커에서 처리 중...")
    print("-" * 60)

    # 결과 대기 (InMemoryBroker의 경우 같은 프로세스에서만 동작)
    # RedisBroker 사용 시 별도 프로세스에서 워커 실행 필요

    # 워커 시작 (같은 프로세스에서 테스트용)
    print("\n[워커 시작 (같은 프로세스)]")
    await backend.start_worker(app.manager, worker_count=2)

    # 잠시 대기 후 결과 확인
    await asyncio.sleep(5)

    print("\n[결과 확인]")
    for i, task in enumerate([task1, task2, task3, task4], 1):
        try:
            # DistributedTaskResult.get()은 비동기
            result = await task.get(timeout=10)
            print(f"    태스크 {i}: 성공 - {result}")
        except Exception as e:
            print(f"    태스크 {i}: 실패 - {e}")

    # 종료
    await backend.shutdown()

    print("\n" + "=" * 60)
    print("예제 완료!")
    print("=" * 60)


def main():
    """메인 함수"""
    asyncio.run(submit_tasks())


if __name__ == "__main__":
    main()
