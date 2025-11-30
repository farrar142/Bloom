"""REQUEST 스코프를 위한 요청 컨텍스트 관리

ContextVar 기반으로 각 요청(코루틴)별로 독립적인 인스턴스 저장소를 제공합니다.

사용 예시:
    @Component
    @Scope(ScopeEnum.REQUEST)
    class RequestSession:
        user_id: str | None = None

        @PostConstruct
        def init(self):
            print("세션 시작")

        @PreDestroy
        def cleanup(self):
            print("세션 종료")

    # 미들웨어에서 자동 관리
    # 요청 시작 → RequestContext.start()
    # 요청 종료 → RequestContext.end() → @PreDestroy 호출
"""

from contextvars import ContextVar
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .container import Container

# 요청별 인스턴스 저장소 (타입 -> 인스턴스)
_request_instances: ContextVar[dict[type, Any]] = ContextVar(
    "request_instances", default=None
)

# 요청별 컨테이너 저장소 (타입 -> 컨테이너) - 라이프사이클 관리용
_request_containers: ContextVar[dict[type, "Container"]] = ContextVar(
    "request_containers", default=None
)


class RequestContext:
    """REQUEST 스코프 인스턴스를 관리하는 컨텍스트

    각 HTTP 요청(또는 코루틴)마다 독립적인 인스턴스 저장소를 제공합니다.
    요청 시작 시 `start()`, 종료 시 `end()`를 호출하여 라이프사이클을 관리합니다.
    """

    @staticmethod
    def start() -> None:
        """요청 컨텍스트 시작 - 새 인스턴스 저장소 초기화"""
        _request_instances.set({})
        _request_containers.set({})

    @staticmethod
    def end() -> None:
        """요청 컨텍스트 종료 - @PreDestroy 호출 및 저장소 정리

        LifecycleManager를 통해 모든 REQUEST 인스턴스의 PreDestroy를 호출합니다.
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
                    method()
            except Exception:
                pass  # 예외 무시 (정리 단계)


# 컨텍스트 매니저 지원
class request_scope:
    """REQUEST 스코프를 위한 컨텍스트 매니저

    테스트나 수동 관리 시 사용:
        with request_scope():
            # 이 블록 내에서 REQUEST 스코프 인스턴스가 관리됨
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
        RequestContext.end()
