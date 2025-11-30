"""LifecycleManager - 라이프사이클 관리자

Manager → Registry → Container(Entry) 패턴을 따릅니다.

SINGLETON, PROTOTYPE, REQUEST 스코프별 라이프사이클 관리:
- SINGLETON: ready() 시점에 PostConstruct, shutdown() 시점에 PreDestroy
- PROTOTYPE: 필드 접근 시 PostConstruct (Spring과 동일하게 PreDestroy 미호출, GC가 정리)
- REQUEST: 요청 내 첫 접근 시 PostConstruct, 요청 종료 시 PreDestroy (RequestContext)
"""

import asyncio
import inspect
from typing import Any, Callable, ClassVar, TYPE_CHECKING

from bloom.core.abstract import AbstractManager
from .container import LifecycleHandlerContainer, LifecycleType, LifecycleTypeElement
from .registry import LifecycleRegistry

if TYPE_CHECKING:
    from bloom.core.manager import ContainerManager
    from bloom.core.container import Container


class LifecycleManager(AbstractManager[LifecycleRegistry]):
    """
    애플리케이션 레벨에서 컨테이너들의 라이프사이클을 관리하는 클래스

    Manager → Registry → Container(Entry) 패턴을 따릅니다.

    - @PostConstruct: 컨테이너 인스턴스 생성 후 호출
      - 동기 메서드: 즉시 실행
      - 비동기 메서드: 지연 등록 후 start_async()에서 실행
    - @PreDestroy: 애플리케이션 종료 시 역순으로 호출
    """

    registry_type: ClassVar[type[LifecycleRegistry]] = LifecycleRegistry
    # item_type은 None - 수집 방식이 다름 (클래스 메서드 탐색)

    def __init__(self, container_manager: "ContainerManager"):
        super().__init__()
        self.container_manager = container_manager
        self._registry = LifecycleRegistry()
        # 비동기 PostConstruct 핸들러들 (지연 실행용)
        self._pending_async_post_construct: list[Callable[[], Any]] = []
        # 비동기 PreDestroy 핸들러들 (역순 실행용)
        self._pending_async_pre_destroy: list[Callable[[], Any]] = []
        # 초기화 완료 여부
        self._started = False
        self._initialized = True  # AbstractManager 호환

    @property
    def registry(self) -> LifecycleRegistry:
        """레지스트리 반환"""
        if self._registry is None:
            raise RuntimeError("LifecycleManager is not initialized")
        return self._registry

    @property
    def is_started(self) -> bool:
        """async 생명주기 시작 여부"""
        return self._started

    def _invoke_handler(
        self, handler: LifecycleHandlerContainer, instance: Any
    ) -> None:
        """핸들러 메서드 호출 (동기만)"""
        method = getattr(instance, handler.handler_method.__name__)
        result = method()

        # 비동기 메서드인 경우: 지연 등록
        if inspect.iscoroutine(result):
            # 코루틴을 클로저로 캡처하여 나중에 실행
            async def run_coro(coro=result):
                await coro

            self._pending_async_post_construct.append(run_coro)

    def _invoke_handler_for_destroy(
        self, handler: LifecycleHandlerContainer, instance: Any
    ) -> None:
        """PreDestroy 핸들러 메서드 호출 (동기만)"""
        method = getattr(instance, handler.handler_method.__name__)
        result = method()

        # 비동기 메서드인 경우: 지연 등록
        if inspect.iscoroutine(result):

            async def run_coro(coro=result):
                await coro

            self._pending_async_pre_destroy.append(run_coro)

    async def start_async(self) -> None:
        """
        지연된 비동기 PostConstruct 핸들러들을 실행합니다.

        ASGI lifespan startup 또는 asyncio.run() 내에서 호출해야 합니다.
        """
        if self._started:
            return

        # 등록된 순서대로 실행
        for handler in self._pending_async_post_construct:
            await handler()

        self._pending_async_post_construct.clear()
        self._started = True

    async def shutdown_async(self) -> None:
        """
        지연된 비동기 PreDestroy 핸들러들을 실행합니다.

        ASGI lifespan shutdown 또는 asyncio.run() 내에서 호출해야 합니다.
        """
        if not self._started:
            return

        # 역순으로 실행
        for handler in reversed(self._pending_async_pre_destroy):
            try:
                await handler()
            except Exception:
                pass  # PreDestroy 에러는 무시

        self._pending_async_pre_destroy.clear()
        self._started = False

    def invoke_post_construct(self, container: "Container", instance: Any) -> None:
        """
        특정 컨테이너 인스턴스의 @PostConstruct 메서드들 호출

        Args:
            container: 대상 컨테이너
            instance: 컨테이너의 인스턴스
        """
        handlers = self.registry.get_post_construct_handlers(container)
        for handler in handlers:
            self._invoke_handler(handler, instance)

    def invoke_pre_destroy(self, container: "Container", instance: Any) -> None:
        """
        특정 컨테이너 인스턴스의 @PreDestroy 메서드들 호출

        Args:
            container: 대상 컨테이너
            instance: 컨테이너의 인스턴스
        """
        handlers = self.registry.get_pre_destroy_handlers(container)
        for handler in handlers:
            self._invoke_handler_for_destroy(handler, instance)

    def invoke_all_pre_destroy(self, containers_order: list["Container"]) -> None:
        """
        모든 컨테이너의 @PreDestroy 메서드들을 역순으로 호출

        Args:
            containers_order: 초기화 순서대로 정렬된 컨테이너 리스트 (역순으로 호출됨)
        """
        for container in reversed(containers_order):
            # Container의 캐시된 인스턴스를 직접 가져옴
            instance = container._get_cached_instance()
            if instance:
                self.invoke_pre_destroy(container, instance)

    # =========================================================================
    # PROTOTYPE 라이프사이클 관리
    # =========================================================================

    def _get_lifecycle_method_names(
        self, target_cls: type, lifecycle_type: LifecycleType
    ) -> list[str]:
        """클래스의 특정 라이프사이클 메서드 이름들을 가져옵니다."""
        from bloom.core.container.base import Container

        method_names: list[str] = []

        for attr_name in dir(target_cls):
            try:
                attr = getattr(target_cls, attr_name, None)
                if attr is None:
                    continue

                handler_container = Container.get_container(attr)
                if handler_container is None:
                    continue

                if not isinstance(handler_container, LifecycleHandlerContainer):
                    continue

                for elem in handler_container.elements:
                    if isinstance(elem, LifecycleTypeElement):
                        if elem.lifecycle_type == lifecycle_type:
                            method_names.append(attr_name)
                            break
            except Exception:
                continue

        return method_names

    def invoke_prototype_post_construct(
        self, instance: Any, container: "Container"
    ) -> None:
        """
        PROTOTYPE 인스턴스의 @PostConstruct 메서드들을 호출합니다.

        PROTOTYPE은 필드 접근 시마다 새 인스턴스가 생성되므로,
        LazyFieldProxy에서 인스턴스 생성 직후 이 메서드를 호출합니다.

        Args:
            instance: PROTOTYPE 인스턴스
            container: 컨테이너

        Raises:
            Exception: PostConstruct 실패 시 예외 전파
        """
        target_cls = container.target
        method_names = self._get_lifecycle_method_names(
            target_cls, LifecycleType.POST_CONSTRUCT
        )

        for method_name in method_names:
            method = getattr(instance, method_name, None)
            if method is not None:
                result = method()
                # 비동기 메서드인 경우 경고 (PROTOTYPE에서는 지원 안 함)
                if inspect.iscoroutine(result):
                    result.close()  # 코루틴 정리
                    raise RuntimeError(
                        f"Async @PostConstruct is not supported for PROTOTYPE scope: "
                        f"{target_cls.__name__}.{method_name}"
                    )

    def invoke_request_post_construct(
        self, instance: Any, container: "Container"
    ) -> None:
        """
        REQUEST 인스턴스의 @PostConstruct 메서드들을 호출합니다.

        REQUEST 스코프는 요청 내 첫 접근 시 인스턴스가 생성되며,
        LazyFieldProxy에서 인스턴스 생성 직후 이 메서드를 호출합니다.

        동기 메서드는 즉시 실행되고, 비동기 메서드는 RequestContext의
        pending 리스트에 등록되어 핸들러 실행 전에 실행됩니다.

        Args:
            instance: REQUEST 인스턴스
            container: 컨테이너

        Raises:
            Exception: PostConstruct 실패 시 예외 전파
        """
        from bloom.core.request_context import RequestContext

        target_cls = container.target
        method_names = self._get_lifecycle_method_names(
            target_cls, LifecycleType.POST_CONSTRUCT
        )

        for method_name in method_names:
            method = getattr(instance, method_name, None)
            if method is not None:
                result = method()
                # 비동기 메서드인 경우: pending에 등록
                if inspect.iscoroutine(result):
                    RequestContext.add_pending_init(result)

    async def invoke_request_post_construct_async(
        self, instance: Any, container: "Container"
    ) -> None:
        """
        REQUEST 인스턴스의 @PostConstruct 메서드들을 비동기로 호출합니다.

        동기/비동기 메서드 모두 지원합니다.

        Args:
            instance: REQUEST 인스턴스
            container: 컨테이너

        Raises:
            Exception: PostConstruct 실패 시 예외 전파
        """
        target_cls = container.target
        method_names = self._get_lifecycle_method_names(
            target_cls, LifecycleType.POST_CONSTRUCT
        )

        for method_name in method_names:
            method = getattr(instance, method_name, None)
            if method is not None:
                result = method()
                if inspect.iscoroutine(result):
                    await result

    # =========================================================================
    # REQUEST 컨텍스트 관리 (ASGI 레벨에서 호출)
    # =========================================================================

    def start_request(self) -> None:
        """
        HTTP 요청 시작 시 호출 - REQUEST 컨텍스트 활성화

        ASGI 앱에서 요청 처리 시작 전에 호출됩니다.
        모든 미들웨어보다 먼저 실행되어 REQUEST 스코프를 사용 가능하게 합니다.
        """
        from bloom.core.request_context import RequestContext

        RequestContext.start()

    def end_request(self) -> None:
        """
        HTTP 요청 종료 시 호출 - REQUEST 인스턴스 정리 (동기 버전)

        ASGI 앱에서 요청 처리 완료 후 호출됩니다.
        모든 REQUEST 스코프 인스턴스의 @PreDestroy를 호출하고 컨텍스트를 정리합니다.

        Note:
            async @PreDestroy가 있는 경우 end_request_async()를 사용하세요.
        """
        from bloom.core.request_context import RequestContext

        RequestContext.end()

    async def run_pending_request_init(self) -> None:
        """
        대기 중인 REQUEST 스코프 인스턴스의 async @PostConstruct 실행

        Router에서 미들웨어 진입 전, 핸들러 실행 전에 호출됩니다.
        여러 번 호출해도 안전합니다 (pending이 없으면 즉시 리턴).
        """
        from bloom.core.request_context import RequestContextManager

        await RequestContextManager.run_pending_init()

    async def end_request_async(self) -> None:
        """
        HTTP 요청 종료 시 호출 - REQUEST 인스턴스 정리 (비동기 버전)

        ASGI 앱에서 요청 처리 완료 후 호출됩니다.
        pending async @PostConstruct를 실행하고,
        모든 REQUEST 스코프 인스턴스의 @PreDestroy (async 포함)를 호출합니다.
        """
        from bloom.core.request_context import RequestContext

        # pending async @PostConstruct 실행
        await RequestContext.run_pending_init()
        # async @PreDestroy 지원하는 정리
        await RequestContext.end_async()

    # =========================================================================
    # PROTOTYPE 라이프사이클 수동 관리
    # =========================================================================

    def invoke_prototype_pre_destroy(
        self, instance: Any, container: "Container | None" = None
    ) -> None:
        """
        PROTOTYPE 인스턴스의 @PreDestroy 메서드들을 호출합니다.

        Spring과 달리 Bloom에서는 사용자가 SystemEventBus를 통해
        PROTOTYPE 인스턴스를 추적하고 명시적으로 정리할 수 있습니다.

        Args:
            instance: PROTOTYPE 인스턴스
            container: 컨테이너 (없으면 인스턴스 타입에서 조회)

        사용 예시:
            @Component
            class ResourceTracker:
                system_events: SystemEventBus
                lifecycle: LifecycleManager  # or via ContainerManager
                _resources: list[tuple[Any, Container]]

                @PostConstruct
                def setup(self):
                    self._resources = []
                    self.system_events.subscribe(InstanceCreatedEvent, self._on_created)

                def _on_created(self, event: InstanceCreatedEvent):
                    if event.scope == Scope.PROTOTYPE:
                        container = self._get_container(event.instance_type)
                        self._resources.append((event.instance, container))

                def cleanup_all(self):
                    for instance, container in self._resources:
                        self.lifecycle.invoke_prototype_pre_destroy(instance, container)
                    self._resources.clear()
        """
        from bloom.core.container.element import Scope
        from bloom.core.events import InstanceDestroyingEvent

        # 컨테이너가 없으면 인스턴스 타입에서 조회
        if container is None:
            container = self.container_manager.get_container(type(instance))

        if container is None:
            return

        target_cls = container.target
        method_names = self._get_lifecycle_method_names(
            target_cls, LifecycleType.PRE_DESTROY
        )

        # InstanceDestroyingEvent 발행
        event = InstanceDestroyingEvent(
            instance=instance,
            instance_type=target_cls,
            scope=Scope.PROTOTYPE,
        )
        self.container_manager.system_events.publish(event)

        # @PreDestroy 메서드들 호출
        for method_name in method_names:
            method = getattr(instance, method_name, None)
            if method is not None:
                try:
                    result = method()
                    # 비동기 메서드인 경우 코루틴 정리
                    if inspect.iscoroutine(result):
                        result.close()
                except Exception:
                    pass  # PreDestroy 에러는 무시
