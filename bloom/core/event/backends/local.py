"""bloom.core.event.backends.local - 로컬 인메모리 이벤트 버스

단일 프로세스 내에서 동작하는 인메모리 이벤트 버스입니다.
동기 및 비동기 핸들러를 모두 지원합니다.
"""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
from collections import defaultdict
from typing import Any, Callable, Awaitable, TYPE_CHECKING

from ..bus import (
    EventBus,
    EventHandler,
    SyncEventHandler,
    Subscription,
    SubscriptionGroup,
    SubscriptionMode,
)
from ..models import Event, EventResult, EventStatus, get_event_type

if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


class LocalEventBus(EventBus):
    """로컬 인메모리 이벤트 버스

    단일 프로세스 내에서 동작하는 이벤트 버스입니다.
    동기 핸들러는 즉시 실행되고, 비동기 핸들러는 백그라운드에서 실행됩니다.

    Features:
        - 동기/비동기 핸들러 분리 처리
        - 우선순위 기반 핸들러 실행
        - 조건부 핸들러 실행
        - 에러 격리 (한 핸들러 실패가 다른 핸들러에 영향 없음)
        - 이벤트 큐 기반 비동기 처리

    Examples:
        # 이벤트 버스 생성
        event_bus = LocalEventBus()
        await event_bus.start()

        # 동기 핸들러 등록 (같은 트랜잭션 내에서 처리)
        await event_bus.subscribe(
            "user.created",
            sync_handler,
            mode=SubscriptionMode.SYNC
        )

        # 비동기 핸들러 등록 (백그라운드 처리)
        await event_bus.subscribe(
            "user.created",
            async_handler,
            mode=SubscriptionMode.ASYNC
        )

        # 이벤트 발행
        await event_bus.publish(Event(event_type="user.created", payload=user))

        # 종료
        await event_bus.stop()
    """

    def __init__(
        self,
        *,
        max_queue_size: int = 10000,
        worker_count: int = 1,
        error_handler: Callable[[Event, Exception], Awaitable[None]] | None = None,
    ):
        """
        Args:
            max_queue_size: 비동기 이벤트 큐 최대 크기
            worker_count: 비동기 워커 수
            error_handler: 에러 발생 시 호출할 핸들러
        """
        self._subscriptions: dict[str, SubscriptionGroup] = defaultdict(
            lambda: SubscriptionGroup(event_type="")
        )
        self._subscription_by_id: dict[str, Subscription] = {}
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=max_queue_size)
        self._workers: list[asyncio.Task[None]] = []
        self._worker_count = worker_count
        self._running = False
        self._error_handler = error_handler
        self._lock = asyncio.Lock()

    # =========================================================================
    # Public API
    # =========================================================================

    async def publish(
        self,
        event: Event,
        *,
        wait_for_handlers: bool = False,
    ) -> list[EventResult]:
        """이벤트 발행

        1. 동기 핸들러 즉시 실행
        2. 비동기 핸들러는 큐에 추가 (또는 wait_for_handlers=True면 대기)

        Args:
            event: 발행할 이벤트
            wait_for_handlers: True면 모든 핸들러 완료까지 대기
        """
        results: list[EventResult] = []

        # 1. 동기 핸들러 실행
        sync_results = await self.publish_sync(event)
        results.extend(sync_results)

        # 2. 비동기 핸들러 처리
        group = self._subscriptions.get(event.event_type)
        if group:
            async_handlers = group.get_async_handlers()
            if async_handlers:
                if wait_for_handlers:
                    # 모든 비동기 핸들러 실행 후 대기
                    async_results = await self._execute_handlers(
                        event, async_handlers
                    )
                    results.extend(async_results)
                else:
                    # 큐에 추가 (백그라운드 처리)
                    try:
                        self._queue.put_nowait(event)
                    except asyncio.QueueFull:
                        logger.warning(
                            f"Event queue full, dropping event: {event.event_type}"
                        )

        return results

    async def publish_sync(self, event: Event) -> list[EventResult]:
        """동기 이벤트 발행 (동기 핸들러만 실행)"""
        group = self._subscriptions.get(event.event_type)
        if not group:
            return []

        sync_handlers = group.get_sync_handlers()
        return await self._execute_handlers(event, sync_handlers)

    async def subscribe(
        self,
        event_type: str | type[Event],
        handler: EventHandler | SyncEventHandler,
        *,
        mode: SubscriptionMode = SubscriptionMode.ASYNC,
        priority: int = 0,
        condition: str | None = None,
    ) -> Subscription:
        """이벤트 구독"""
        event_type_str = get_event_type(event_type)

        subscription = Subscription(
            event_type=event_type_str,
            handler=handler,
            mode=mode,
            priority=priority,
            condition=condition,
        )

        async with self._lock:
            # SubscriptionGroup 초기화
            if event_type_str not in self._subscriptions:
                self._subscriptions[event_type_str] = SubscriptionGroup(
                    event_type=event_type_str
                )

            self._subscriptions[event_type_str].add(subscription)
            self._subscription_by_id[subscription.subscription_id] = subscription

        logger.debug(
            f"Subscribed to '{event_type_str}': {subscription.handler_name} "
            f"(mode={mode.name}, priority={priority})"
        )

        return subscription

    async def unsubscribe(self, subscription: Subscription | str) -> bool:
        """구독 해제"""
        subscription_id = (
            subscription.subscription_id
            if isinstance(subscription, Subscription)
            else subscription
        )

        async with self._lock:
            if subscription_id not in self._subscription_by_id:
                return False

            sub = self._subscription_by_id.pop(subscription_id)
            group = self._subscriptions.get(sub.event_type)
            if group:
                group.remove(subscription_id)

        logger.debug(f"Unsubscribed: {sub.handler_name} from '{sub.event_type}'")
        return True

    def get_subscriptions(self, event_type: str | None = None) -> list[Subscription]:
        """구독 목록 조회"""
        if event_type:
            group = self._subscriptions.get(event_type)
            return group.subscriptions if group else []
        return list(self._subscription_by_id.values())

    async def start(self) -> None:
        """이벤트 버스 시작"""
        if self._running:
            return

        self._running = True

        # 비동기 워커 시작
        for i in range(self._worker_count):
            worker = asyncio.create_task(self._worker_loop(i))
            self._workers.append(worker)

        logger.info(f"LocalEventBus started with {self._worker_count} workers")

    async def stop(self, timeout: float = 5.0) -> None:
        """이벤트 버스 종료"""
        if not self._running:
            return

        self._running = False

        # 대기 중인 이벤트 처리
        try:
            await asyncio.wait_for(self._drain_queue(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Event queue drain timeout, some events may be lost")

        # 워커 종료
        for worker in self._workers:
            worker.cancel()

        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)

        self._workers.clear()
        logger.info("LocalEventBus stopped")

    @property
    def is_running(self) -> bool:
        """실행 중 여부"""
        return self._running

    # =========================================================================
    # Internal Methods
    # =========================================================================

    async def _worker_loop(self, worker_id: int) -> None:
        """비동기 워커 루프"""
        logger.debug(f"Worker {worker_id} started")

        while self._running:
            try:
                # 큐에서 이벤트 가져오기 (타임아웃으로 종료 체크)
                try:
                    event = await asyncio.wait_for(
                        self._queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                # 비동기 핸들러 실행
                await self._process_async_event(event)
                self._queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")

        logger.debug(f"Worker {worker_id} stopped")

    async def _process_async_event(self, event: Event) -> None:
        """비동기 이벤트 처리"""
        group = self._subscriptions.get(event.event_type)
        if not group:
            return

        async_handlers = group.get_async_handlers()
        if async_handlers:
            await self._execute_handlers(event, async_handlers)

    async def _execute_handlers(
        self,
        event: Event,
        subscriptions: list[Subscription],
    ) -> list[EventResult]:
        """핸들러 실행"""
        results: list[EventResult] = []

        for sub in subscriptions:
            result = await self._execute_single_handler(event, sub)
            results.append(result)

        return results

    async def _execute_single_handler(
        self,
        event: Event,
        subscription: Subscription,
    ) -> EventResult:
        """단일 핸들러 실행"""
        start_time = time.perf_counter()
        handler_name = subscription.handler_name or "unknown"

        try:
            # 조건 체크
            if subscription.condition and not self._check_condition(
                event, subscription.condition
            ):
                return EventResult(
                    event_id=event.event_id,
                    status=EventStatus.COMPLETED,
                    handler_name=handler_name,
                    result=None,
                )

            # 핸들러 실행
            handler = subscription.handler
            if asyncio.iscoroutinefunction(handler):
                result = await handler(event)
            else:
                # 동기 함수는 run_in_executor로 실행하지 않고 직접 호출
                # (같은 트랜잭션 컨텍스트 유지를 위해)
                result = handler(event)

            duration_ms = (time.perf_counter() - start_time) * 1000

            return EventResult(
                event_id=event.event_id,
                status=EventStatus.COMPLETED,
                handler_name=handler_name,
                result=result,
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"Handler '{handler_name}' failed for event '{event.event_type}': {e}\n"
                f"{traceback.format_exc()}"
            )

            # 에러 핸들러 호출
            if self._error_handler:
                try:
                    await self._error_handler(event, e)
                except Exception as handler_error:
                    logger.error(f"Error handler failed: {handler_error}")

            return EventResult(
                event_id=event.event_id,
                status=EventStatus.FAILED,
                handler_name=handler_name,
                error=e,
                duration_ms=duration_ms,
            )

    def _check_condition(self, event: Event, condition: str) -> bool:
        """조건 체크

        조건 문자열을 평가하여 핸들러 실행 여부 결정.
        보안을 위해 제한된 컨텍스트에서 실행.
        """
        try:
            # 제한된 네임스페이스에서 조건 평가
            namespace = {
                "event": event,
                "payload": event.payload,
                "metadata": event.metadata,
            }
            return bool(eval(condition, {"__builtins__": {}}, namespace))
        except Exception as e:
            logger.warning(f"Condition evaluation failed: {condition} - {e}")
            return True  # 조건 평가 실패 시 실행

    async def _drain_queue(self) -> None:
        """큐의 모든 이벤트 처리"""
        while not self._queue.empty():
            try:
                event = self._queue.get_nowait()
                await self._process_async_event(event)
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def clear_subscriptions(self) -> None:
        """모든 구독 제거 (테스트용)"""
        self._subscriptions.clear()
        self._subscription_by_id.clear()

    @property
    def queue_size(self) -> int:
        """현재 큐 크기"""
        return self._queue.qsize()

    @property
    def subscription_count(self) -> int:
        """총 구독 수"""
        return len(self._subscription_by_id)
