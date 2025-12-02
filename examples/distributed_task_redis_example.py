"""
Redis 분산 태스크 예제

이 예제는 Redis 브로커를 사용하여 프로듀서와 워커를 분리 실행합니다.
실제 프로덕션 환경처럼 별도의 프로세스에서 워커를 실행합니다.

실행 방법:
1. Redis 서버 실행 (기본 포트 6379)
   $ docker run -d -p 6379:6379 redis:latest

2. 터미널 1: 워커 실행
   $ cd bloom
   $ uv run python examples/distributed_task_redis_example.py worker

3. 터미널 2: 프로듀서 실행 (태스크 제출)
   $ cd bloom
   $ uv run python examples/distributed_task_redis_example.py producer

또는 bloom worker CLI 사용:
   $ uv run bloom worker examples.distributed_task_redis_example:app.queue
"""

import asyncio
import logging
import sys
import time
from datetime import datetime

from bloom import Application, Component
from bloom.core.decorators import Factory, PostConstruct, PreDestroy
from bloom.core.lazy import Lazy
from bloom.task import Task
from bloom.task.distributed import DistributedTaskBackend
from bloom.task.broker.redis import RedisBroker

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# =============================================================================
# Redis 설정
# =============================================================================

REDIS_URL = "redis://192.168.0.17:6379/0"


# =============================================================================
# 태스크 서비스 정의
# =============================================================================


@Component
class OrderService:
    """주문 처리 서비스"""

    @Task
    def process_order(self, order_id: int, items: list[dict]) -> dict:
        """주문 처리"""
        print(f"[OrderService] 주문 처리 시작: #{order_id}")
        time.sleep(1)  # 처리 시간 시뮬레이션

        total = sum(item["price"] * item["quantity"] for item in items)
        result = {
            "order_id": order_id,
            "items_count": len(items),
            "total": total,
            "status": "completed",
            "processed_at": datetime.now().isoformat(),
        }
        print(f"[OrderService] 주문 완료: #{order_id} - 총액: {total:,}원")
        return result

    @Task(name="cancel_order")
    def cancel_order(self, order_id: int, reason: str) -> dict:
        """주문 취소"""
        print(f"[OrderService] 주문 취소: #{order_id} - 사유: {reason}")
        time.sleep(0.5)
        return {
            "order_id": order_id,
            "status": "cancelled",
            "reason": reason,
            "cancelled_at": datetime.now().isoformat(),
        }


@Component
class PaymentService:
    """결제 처리 서비스"""

    @Task
    def process_payment(self, order_id: int, amount: float, method: str) -> dict:
        """결제 처리"""
        print(f"[PaymentService] 결제 처리: #{order_id} - {amount:,.0f}원 ({method})")
        time.sleep(1.5)  # 결제 처리 시뮬레이션

        # 결제 성공 시뮬레이션
        result = {
            "order_id": order_id,
            "amount": amount,
            "method": method,
            "transaction_id": f"TXN-{order_id}-{int(time.time())}",
            "status": "paid",
            "paid_at": datetime.now().isoformat(),
        }
        print(f"[PaymentService] 결제 완료: {result['transaction_id']}")
        return result

    @Task(name="refund_payment", max_retries=3)
    def refund_payment(self, transaction_id: str, amount: float) -> dict:
        """환불 처리 (재시도 포함)"""
        print(f"[PaymentService] 환불 처리: {transaction_id} - {amount:,.0f}원")
        time.sleep(1)
        return {
            "transaction_id": transaction_id,
            "refund_amount": amount,
            "status": "refunded",
            "refunded_at": datetime.now().isoformat(),
        }


@Component
class InventoryService:
    """재고 관리 서비스"""

    @Task(name="update_inventory")
    def update_inventory(self, product_id: int, quantity_change: int) -> dict:
        """재고 업데이트"""
        action = "감소" if quantity_change < 0 else "증가"
        print(
            f"[InventoryService] 재고 {action}: 상품 #{product_id} ({abs(quantity_change)}개)"
        )
        time.sleep(0.3)
        return {
            "product_id": product_id,
            "quantity_change": quantity_change,
            "updated_at": datetime.now().isoformat(),
        }


# =============================================================================
# 분산 태스크 백엔드 설정
# =============================================================================


@Component
class TaskBackendFactory:
    """DistributedTaskBackend Factory - 별도 클래스로 분리하여 순환 방지"""

    pass


@Component
class TaskLifecycleManager:
    """태스크 백엔드 생명주기 관리

    async @PostConstruct/@PreDestroy는 ASGI lifespan 또는
    await app.ready_async()에서 자동으로 실행됩니다.
    """

    backend: Lazy[DistributedTaskBackend]  # Lazy로 지연 주입 (투명 프록시)

    @Factory
    def task_backend(self) -> DistributedTaskBackend:
        """Redis 브로커를 사용하는 분산 태스크 백엔드"""
        broker = RedisBroker(REDIS_URL)
        return DistributedTaskBackend(broker, worker_count=4)

    @PostConstruct
    async def start_backend(self):
        """백엔드 시작 (Redis 연결)"""
        # .get() 불필요! 투명 프록시로 직접 접근
        await self.backend.start()

    @PreDestroy
    async def stop_backend(self):
        """백엔드 종료 (Redis 연결 해제)"""
        await self.backend.shutdown()


# =============================================================================
# 애플리케이션 생성
# =============================================================================

app = (
    Application("redis-task-example")
    .scan(OrderService)
    .scan(PaymentService)
    .scan(InventoryService)
    .scan(TaskBackendFactory)
    .scan(TaskLifecycleManager)
)


# =============================================================================
# 프로듀서 (태스크 제출)
# =============================================================================


async def run_producer():
    """태스크 제출 예제"""
    print("=" * 60)
    print("Redis 분산 태스크 예제 - Producer")
    print("=" * 60)
    print()

    # async @PostConstruct 포함 초기화 (Redis 연결 등)
    await app.ready_async()

    # 서비스 인스턴스 가져오기
    order_service = app.manager.get_instance(OrderService)
    payment_service = app.manager.get_instance(PaymentService)
    inventory_service = app.manager.get_instance(InventoryService)

    # 주문 데이터
    order_id = 1001
    items = [
        {"product_id": 1, "name": "노트북", "price": 1500000, "quantity": 1},
        {"product_id": 2, "name": "마우스", "price": 50000, "quantity": 2},
    ]
    total_amount = sum(item["price"] * item["quantity"] for item in items)

    results = []

    # 1. 재고 감소
    print("[1] 재고 감소 태스크 제출")
    for item in items:
        result = await inventory_service.update_inventory.delay_async(
            item["product_id"], -item["quantity"]
        )
        print(f"    상품 #{item['product_id']}: 태스크 ID = {result.task_id[:8]}...")
        results.append(("inventory", result))

    # 2. 주문 처리
    print("\n[2] 주문 처리 태스크 제출")
    order_result = await order_service.process_order.delay_async(order_id, items)
    print(f"    주문 #{order_id}: 태스크 ID = {order_result.task_id[:8]}...")
    results.append(("order", order_result))

    # 3. 결제 처리
    print("\n[3] 결제 처리 태스크 제출")
    payment_result = await payment_service.process_payment.delay_async(
        order_id, total_amount, "credit_card"
    )
    print(f"    결제: 태스크 ID = {payment_result.task_id[:8]}...")
    results.append(("payment", payment_result))

    print()
    print("-" * 60)
    print("태스크 제출 완료!")
    print("워커가 실행 중이면 결과를 기다립니다...")
    print("-" * 60)
    print()

    # 결과 대기
    print("[결과 확인]")
    for name, result in results:
        try:
            value = await result.get(timeout=30)
            print(f"    {name}: 성공 - {value}")
        except TimeoutError:
            print(f"    {name}: 타임아웃 (워커가 실행 중인지 확인하세요)")
        except Exception as e:
            print(f"    {name}: 실패 - {e}")

    # async @PreDestroy 실행 (Redis 연결 해제)
    await app.shutdown_async()

    print()
    print("=" * 60)
    print("프로듀서 완료!")
    print("=" * 60)


# =============================================================================
# 워커 (태스크 처리)
# =============================================================================


async def run_worker():
    """워커 실행"""
    print("=" * 60)
    print("Redis 분산 태스크 예제 - Worker")
    print("=" * 60)
    print()
    print(f"Redis: {REDIS_URL}")
    print("Ctrl+C로 종료")
    print()

    # async 생명주기 핸들러 포함 초기화 (TaskLifecycleManager.start_backend)
    await app.ready_async()

    backend = app.manager.get_instance(DistributedTaskBackend)

    try:
        await backend.start_worker(app.manager)

        # 무한 대기 (Ctrl+C로 종료)
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n종료 중...")
    finally:
        # async 종료 핸들러 실행 (TaskLifecycleManager.stop_backend)
        await app.shutdown_async()
        print("워커 종료 완료")


# =============================================================================
# 메인 엔트리포인트
# =============================================================================


def main():
    if len(sys.argv) < 2:
        print("사용법: python distributed_task_redis_example.py [producer|worker]")
        print()
        print("옵션:")
        print("  producer  - 태스크를 Redis 큐에 제출")
        print("  worker    - Redis 큐에서 태스크를 가져와 처리")
        print()
        print("또는 bloom worker CLI 사용:")
        print("  uv run bloom worker examples.distributed_task_redis_example:app.queue")
        sys.exit(1)

    mode = sys.argv[1].lower()

    if mode == "producer":
        asyncio.run(run_producer())
    elif mode == "worker":
        asyncio.run(run_worker())
    else:
        print(f"알 수 없는 모드: {mode}")
        print("'producer' 또는 'worker'를 지정하세요.")
        sys.exit(1)


if __name__ == "__main__":
    main()
