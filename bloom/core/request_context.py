"""REQUEST 스코프를 위한 요청 컨텍스트 관리

ContextVar 기반으로 각 요청(코루틴)별로 독립적인 인스턴스 저장소를 제공합니다.

사용 예시:
    @Component
    @Scope(ScopeEnum.REQUEST)
    class RequestSession:
        user_id: str | None = None

        @PostConstruct
        async def init(self):
            print("세션 시작")

        @PreDestroy
        async def cleanup(self):
            print("세션 종료")

    # 미들웨어에서 자동 관리
    # 요청 시작 → RequestContext.start()
    # 요청 종료 → RequestContext.end_async() → @PreDestroy 호출
"""

import inspect
from contextvars import ContextVar
from typing import Any, Coroutine, TYPE_CHECKING

if TYPE_CHECKING:
    from .container import Container

# 요청별 인스턴스 저장소 (타입 -> 인스턴스)
_request_instances: ContextVar[dict[type, Any] | None] = ContextVar(
    "request_instances", default=None
)

# 요청별 컨테이너 저장소 (타입 -> 컨테이너) - 라이프사이클 관리용
_request_containers: ContextVar[dict[type, "Container"] | None] = ContextVar(
    "request_containers", default=None
)

# 대기 중인 async @PostConstruct 코루틴들
_pending_async_init: ContextVar[list[Coroutine[Any, Any, None]] | None] = ContextVar(
    "pending_async_init", default=None
)


class RequestContext:
    """REQUEST 스코프 인스턴스를 관리하는 컨텍스트

    각 HTTP 요청(또는 코루틴)마다 독립적인 인스턴스 저장소를 제공합니다.
    요청 시작 시 `start()`, 종료 시 `end_async()`를 호출하여 라이프사이클을 관리합니다.
    
    async @PostConstruct 지원:
        - 인스턴스 생성 시 async 초기화 코루틴이 pending 리스트에 등록됩니다.
        - 핸들러 실행 전 run_pending_init()를 호출하여 모든 초기화를 완료합니다.
    """

    @staticmethod
    def start() -> None:
        """요청 컨텍스트 시작 - 새 인스턴스 저장소 초기화"""
        _request_instances.set({})
        _request_containers.set({})
        _pending_async_init.set([])

    @staticmethod
    def end() -> None:
        """요청 컨텍스트 종료 - @PreDestroy 호출 및 저장소 정리

        LifecycleManager를 통해 모든 REQUEST 인스턴스의 PreDestroy를 호출합니다.
        동기 메서드만 호출합니다. 비동기는 end_async()를 사용하세요.
        """
        instances = _request_instances.get()
        containers = _request_containers.get()

        if instances and containers:
            # 역순으로 PreDestroy 호출 (생성 역순)
            for target_type in reversed(list(instances.keys())):
                instance = instances.get(target_type)
                container = containers.get(target_type)
                if instance is not None and container is not None:
                    RequestContext._invoke_pre_destroy(instance, container)

        # 저장소 초기화
        _request_instances.set(None)
        _request_containers.set(None)
        _pending_async_init.set(None)

    @staticmethod
    async def end_async() -> None:
        """요청 컨텍스트 종료 (비동기) - @PreDestroy 호출 및 저장소 정리

        동기/비동기 @PreDestroy 모두 지원합니다.
        """
        instances = _request_instances.get()
        containers = _request_containers.get()

        if instances and containers:
            # 역순으로 PreDestroy 호출 (생성 역순)
            for target_type in reversed(list(instances.keys())):
                instance = instances.get(target_type)
                container = containers.get(target_type)
                if instance is not None and container is not None:
                    await RequestContext._invoke_pre_destroy_async(instance, container)

        # 저장소 초기화
        _request_instances.set(None)
        _request_containers.set(None)
        _pending_async_init.set(None)

    @staticmethod
    def add_pending_init(coro: Coroutine[Any, Any, None]) -> None:
        """대기 중인 async @PostConstruct 등록"""
        pending = _pending_async_init.get()
        if pending is not None:
            pending.append(coro)

    @staticmethod
    async def run_pending_init() -> None:
        """대기 중인 모든 async @PostConstruct 실행
        
        핸들러 실행 전에 호출하여 모든 REQUEST 인스턴스의 초기화를 완료합니다.
        여러 번 호출해도 안전합니다 (pending이 없으면 즉시 리턴).
        """
        pending = _pending_async_init.get()
        # 빈 리스트이거나 None이면 즉시 리턴 (가장 흔한 케이스)
        if not pending:
            return
        # 실행할 것들을 복사하고 즉시 비움 (재진입 방지)
        to_run = pending.copy()
        pending.clear()
        for coro in to_run:
            await coro

    @staticmethod
    def is_active() -> bool:
        """현재 요청 컨텍스트가 활성화되어 있는지 확인"""
        return _request_instances.get() is not None

    @staticmethod
    def get_instance(target_type: type) -> Any | None:
        """현재 요청에서 해당 타입의 인스턴스 조회"""
        instances = _request_instances.get()
        if instances is None:
            return None
        return instances.get(target_type)

    @staticmethod
    def set_instance(
        target_type: type, instance: Any, container: "Container"
    ) -> None:
        """현재 요청에 인스턴스 저장"""
        instances = _request_instances.get()
        containers = _request_containers.get()

        if instances is None or containers is None:
            raise RuntimeError(
                "RequestContext is not active. "
                "REQUEST scope requires RequestScopeMiddleware to be enabled."
            )

        instances[target_type] = instance
        containers[target_type] = container

    @staticmethod
    def _invoke_pre_destroy(instance: Any, container: "Container") -> None:
        """인스턴스의 @PreDestroy 메서드 호출

        LifecycleManager의 유틸리티 메서드를 사용하여 PreDestroy 메서드를 조회합니다.
        """
        from .lifecycle import LifecycleType
        from .lifecycle.container import LifecycleHandlerContainer, LifecycleTypeElement
        from .container.base import Container as BaseContainer

        target_cls = container.target
        method_names: list[str] = []

        # 클래스의 모든 속성을 순회하면서 @PreDestroy 메서드 찾기
        for attr_name in dir(target_cls):
            try:
                attr = getattr(target_cls, attr_name, None)
                if attr is None:
                    continue

                handler_container = BaseContainer.get_container(attr)
                if handler_container is None:
                    continue

                if not isinstance(handler_container, LifecycleHandlerContainer):
                    continue

                for elem in handler_container.elements:
                    if isinstance(elem, LifecycleTypeElement):
                        if elem.lifecycle_type == LifecycleType.PRE_DESTROY:
                            method_names.append(attr_name)
                            break
            except Exception:
                continue

        for method_name in method_names:
            try:
                method = getattr(instance, method_name, None)
                if method is not None:
                    result = method()
                    # 비동기 메서드인 경우 코루틴 정리 (동기 버전에서는 실행 불가)
                    if hasattr(result, "close"):
                        result.close()
            except Exception:
                pass  # 예외 무시 (정리 단계)

    @staticmethod
    async def _invoke_pre_destroy_async(instance: Any, container: "Container") -> None:
        """인스턴스의 @PreDestroy 메서드 호출 (비동기 지원)"""
        import inspect
        from .lifecycle import LifecycleType
        from .lifecycle.container import LifecycleHandlerContainer, LifecycleTypeElement
        from .container.base import Container as BaseContainer

        target_cls = container.target
        method_names: list[str] = []

        for attr_name in dir(target_cls):
            try:
                attr = getattr(target_cls, attr_name, None)
                if attr is None:
                    continue

                handler_container = BaseContainer.get_container(attr)
                if handler_container is None:
                    continue

                if not isinstance(handler_container, LifecycleHandlerContainer):
                    continue

                for elem in handler_container.elements:
                    if isinstance(elem, LifecycleTypeElement):
                        if elem.lifecycle_type == LifecycleType.PRE_DESTROY:
                            method_names.append(attr_name)
                            break
            except Exception:
                continue

        for method_name in method_names:
            try:
                method = getattr(instance, method_name, None)
                if method is not None:
                    result = method()
                    if inspect.iscoroutine(result):
                        await result
            except Exception:
                pass  # 예외 무시 (정리 단계)


# 컨텍스트 매니저 지원
class request_scope:
    """REQUEST 스코프를 위한 컨텍스트 매니저

    동기 테스트 (동기 @PostConstruct/@PreDestroy만 지원):
        with request_scope():
            service = container.get_instance(RequestService)

    비동기 테스트 (async @PostConstruct/@PreDestroy 지원):
        async with request_scope():
            service = container.get_instance(RequestService)
    """

    def __enter__(self) -> "request_scope":
        RequestContext.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        RequestContext.end()

    async def __aenter__(self) -> "request_scope":
        RequestContext.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        # pending async @PostConstruct 실행
        await RequestContext.run_pending_init()
        # async @PreDestroy 지원하는 정리
        await RequestContext.end_async()
