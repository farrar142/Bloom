"""REQUEST 스코프를 위한 요청 컨텍스트 관리

ContainerManager와 동일한 패턴:
- RequestContextManager 인스턴스가 ContextVar에 저장됨
- 요청마다 새 인스턴스 생성
- 모듈 레벨 접근 함수 제공

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
    # 요청 시작 → RequestContextManager.start()
    # 요청 종료 → manager.end_async() → @PreDestroy 호출
"""

import inspect
from contextvars import ContextVar
from typing import Any, Coroutine, TYPE_CHECKING

if TYPE_CHECKING:
    from .container import Container


# =============================================================================
# ContextVar 및 접근 함수 (ContainerManager 패턴)
# =============================================================================

# 현재 활성 RequestContextManager를 저장하는 ContextVar
_current_request: ContextVar["RequestContextManager | None"] = ContextVar(
    "current_request", default=None
)


def get_current_request() -> "RequestContextManager":
    """현재 활성화된 RequestContextManager 반환

    Raises:
        RuntimeError: 활성화된 요청 컨텍스트가 없을 때
    """
    if manager := _current_request.get():
        return manager
    raise RuntimeError(
        "No active RequestContext. "
        "REQUEST scope requires RequestScopeMiddleware to be enabled."
    )


def try_get_current_request() -> "RequestContextManager | None":
    """현재 활성화된 RequestContextManager 반환 (없으면 None)"""
    return _current_request.get()


# =============================================================================
# RequestContextManager 클래스
# =============================================================================


class RequestContextManager:
    """REQUEST 스코프 인스턴스를 관리하는 매니저

    ContainerManager와 동일한 패턴:
    - 인스턴스가 ContextVar에 저장됨
    - 요청마다 새 인스턴스 생성
    - 레지스트리로 인스턴스/컨테이너 관리

    레지스트리 구조:
    - instance_registry: dict[type, Any] - 요청별 인스턴스
    - container_registry: dict[type, Container] - 라이프사이클 관리용
    - pending_init: list[Coroutine] - 대기 중인 async @PostConstruct
    """

    def __init__(self):
        # type -> instance (요청당 1개씩)
        self.instance_registry: dict[type, Any] = {}
        # type -> container (라이프사이클용)
        self.container_registry: dict[type, "Container"] = {}
        # pending async @PostConstruct
        self.pending_init: list[Coroutine[Any, Any, None]] = []

    # -------------------------------------------------------------------------
    # Static 팩토리 메서드 (ContainerManager.start/end 패턴)
    # -------------------------------------------------------------------------

    @staticmethod
    def start() -> "RequestContextManager":
        """새 요청 컨텍스트 시작

        Returns:
            생성된 RequestContextManager 인스턴스
        """
        manager = RequestContextManager()
        _current_request.set(manager)
        return manager

    @staticmethod
    def end() -> None:
        """요청 컨텍스트 종료 (동기) - @PreDestroy 호출 및 저장소 정리

        동기 메서드만 호출합니다. 비동기는 end_async()를 사용하세요.
        """
        manager = _current_request.get()
        if manager:
            manager._cleanup()
        _current_request.set(None)

    @staticmethod
    async def end_async() -> None:
        """요청 컨텍스트 종료 (비동기) - @PreDestroy 호출 및 저장소 정리

        동기/비동기 @PreDestroy 모두 지원합니다.
        """
        manager = _current_request.get()
        if manager:
            await manager._cleanup_async()
        _current_request.set(None)

    @staticmethod
    def is_active() -> bool:
        """현재 요청 컨텍스트가 활성화되어 있는지 확인"""
        return _current_request.get() is not None

    @staticmethod
    async def run_pending_init() -> None:
        """대기 중인 모든 async @PostConstruct 실행

        핸들러 실행 전에 호출하여 모든 REQUEST 인스턴스의 초기화를 완료합니다.
        여러 번 호출해도 안전합니다 (pending이 없으면 즉시 리턴).
        """
        manager = _current_request.get()
        if not manager:
            return
        await manager._run_pending_init()

    # -------------------------------------------------------------------------
    # 인스턴스 메서드
    # -------------------------------------------------------------------------

    def get_instance(self, target_type: type) -> Any | None:
        """현재 요청에서 해당 타입의 인스턴스 조회"""
        return self.instance_registry.get(target_type)

    def set_instance(
        self, target_type: type, instance: Any, container: "Container"
    ) -> None:
        """현재 요청에 인스턴스 저장"""
        self.instance_registry[target_type] = instance
        self.container_registry[target_type] = container

    def add_pending_init(self, coro: Coroutine[Any, Any, None]) -> None:
        """대기 중인 async @PostConstruct 등록"""
        self.pending_init.append(coro)

    async def _run_pending_init(self) -> None:
        """대기 중인 모든 async @PostConstruct 실행 (인스턴스 메서드)"""
        # 빈 리스트면 즉시 리턴 (가장 흔한 케이스)
        if not self.pending_init:
            return
        # 실행할 것들을 복사하고 즉시 비움 (재진입 방지)
        to_run = self.pending_init.copy()
        self.pending_init.clear()
        for coro in to_run:
            await coro

    def reset(self) -> None:
        """레지스트리 초기화 (테스트용)"""
        self.instance_registry.clear()
        self.container_registry.clear()
        self.pending_init.clear()

    # -------------------------------------------------------------------------
    # 라이프사이클 관리
    # -------------------------------------------------------------------------

    def _cleanup(self) -> None:
        """@PreDestroy 호출 및 저장소 정리 (동기)"""
        # 역순으로 PreDestroy 호출 (생성 역순)
        for target_type in reversed(list(self.instance_registry.keys())):
            instance = self.instance_registry.get(target_type)
            container = self.container_registry.get(target_type)
            if instance is not None and container is not None:
                self._invoke_pre_destroy(instance, container)

    async def _cleanup_async(self) -> None:
        """@PreDestroy 호출 및 저장소 정리 (비동기)"""
        # 역순으로 PreDestroy 호출 (생성 역순)
        for target_type in reversed(list(self.instance_registry.keys())):
            instance = self.instance_registry.get(target_type)
            container = self.container_registry.get(target_type)
            if instance is not None and container is not None:
                await self._invoke_pre_destroy_async(instance, container)

    def _invoke_pre_destroy(self, instance: Any, container: "Container") -> None:
        """인스턴스의 @PreDestroy 메서드 호출 (동기)"""
        target_cls = container.target
        method_names = self._find_pre_destroy_methods(target_cls)

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

    async def _invoke_pre_destroy_async(
        self, instance: Any, container: "Container"
    ) -> None:
        """인스턴스의 @PreDestroy 메서드 호출 (비동기)"""
        target_cls = container.target
        method_names = self._find_pre_destroy_methods(target_cls)

        for method_name in method_names:
            try:
                method = getattr(instance, method_name, None)
                if method is not None:
                    result = method()
                    if inspect.iscoroutine(result):
                        await result
            except Exception:
                pass  # 예외 무시 (정리 단계)

    @staticmethod
    def _find_pre_destroy_methods(target_cls: type) -> list[str]:
        """클래스에서 @PreDestroy 메서드 이름들을 찾음"""
        from .lifecycle import LifecycleType
        from .lifecycle.container import LifecycleHandlerContainer, LifecycleTypeElement
        from .container.base import Container as BaseContainer

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

        return method_names

    def __repr__(self) -> str:
        return (
            f"RequestContextManager("
            f"instances={len(self.instance_registry)}, "
            f"pending={len(self.pending_init)})"
        )


# =============================================================================
# 하위 호환성: RequestContext (기존 static API 유지)
# =============================================================================


class RequestContext:
    """REQUEST 스코프 인스턴스를 관리하는 컨텍스트 (하위 호환성)

    RequestContextManager의 static 메서드를 위임합니다.
    새 코드에서는 RequestContextManager 또는 get_current_request()를 사용하세요.
    """

    @staticmethod
    def start() -> None:
        """요청 컨텍스트 시작 - 새 인스턴스 저장소 초기화"""
        RequestContextManager.start()

    @staticmethod
    def end() -> None:
        """요청 컨텍스트 종료 - @PreDestroy 호출 및 저장소 정리"""
        RequestContextManager.end()

    @staticmethod
    async def end_async() -> None:
        """요청 컨텍스트 종료 (비동기) - @PreDestroy 호출 및 저장소 정리"""
        await RequestContextManager.end_async()

    @staticmethod
    def add_pending_init(coro: Coroutine[Any, Any, None]) -> None:
        """대기 중인 async @PostConstruct 등록"""
        manager = try_get_current_request()
        if manager:
            manager.add_pending_init(coro)

    @staticmethod
    async def run_pending_init() -> None:
        """대기 중인 모든 async @PostConstruct 실행"""
        await RequestContextManager.run_pending_init()

    @staticmethod
    def is_active() -> bool:
        """현재 요청 컨텍스트가 활성화되어 있는지 확인"""
        return RequestContextManager.is_active()

    @staticmethod
    def get_instance(target_type: type) -> Any | None:
        """현재 요청에서 해당 타입의 인스턴스 조회"""
        manager = try_get_current_request()
        if manager is None:
            return None
        return manager.get_instance(target_type)

    @staticmethod
    def set_instance(
        target_type: type, instance: Any, container: "Container"
    ) -> None:
        """현재 요청에 인스턴스 저장"""
        manager = try_get_current_request()
        if manager is None:
            raise RuntimeError(
                "RequestContext is not active. "
                "REQUEST scope requires RequestScopeMiddleware to be enabled."
            )
        manager.set_instance(target_type, instance, container)


# =============================================================================
# 컨텍스트 매니저 지원
# =============================================================================


class request_scope:
    """REQUEST 스코프를 위한 컨텍스트 매니저

    동기 테스트 (동기 @PostConstruct/@PreDestroy만 지원):
        with request_scope():
            service = container.get_instance(RequestService)

    비동기 테스트 (async @PostConstruct/@PreDestroy 지원):
        async with request_scope():
            service = container.get_instance(RequestService)
    """

    def __init__(self):
        self._manager: RequestContextManager | None = None

    def __enter__(self) -> "request_scope":
        self._manager = RequestContextManager.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        RequestContextManager.end()

    async def __aenter__(self) -> "request_scope":
        self._manager = RequestContextManager.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        # pending async @PostConstruct 실행
        await RequestContextManager.run_pending_init()
        # async @PreDestroy 지원하는 정리
        await RequestContextManager.end_async()

    @property
    def manager(self) -> RequestContextManager | None:
        """현재 컨텍스트의 RequestContextManager 반환"""
        return self._manager
