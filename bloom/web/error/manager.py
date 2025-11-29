"""ErrorHandlerManager - 에러 핸들러 Manager

에러 핸들러 Registry들을 통합 관리하는 Manager 클래스입니다.
"""

import asyncio
from typing import Any, Callable, TYPE_CHECKING

from bloom.core.abstract import AbstractManager
from bloom.core.manager import get_current_manager

from .container import ErrorHandlerContainer
from .registry import ErrorHandlerRegistry

if TYPE_CHECKING:
    from bloom.web.http import HttpRequest, HttpResponse


class ErrorHandlerManager(AbstractManager[ErrorHandlerRegistry]):
    """
    에러 핸들러 Manager

    Controller 스코프와 글로벌 스코프의 ErrorHandlerRegistry를 관리합니다.

    핸들러 우선순위:
        1. Controller 스코프의 정확한 예외 타입
        2. Controller 스코프의 부모 예외 타입
        3. 글로벌 스코프의 정확한 예외 타입
        4. 글로벌 스코프의 부모 예외 타입

    사용 예시:
        ```python
        manager = ErrorHandlerManager()
        manager.collect_handlers(controller_prefixes)

        # 예외 처리
        handler = manager.find_handler(exception, request_path)
        if handler:
            response = await manager.call_handler(handler, exception, request)
        ```
    """

    def __init__(self):
        super().__init__()
        # 스코프별 Registry
        self._controller_registry = ErrorHandlerRegistry("controller")
        self._global_registry = ErrorHandlerRegistry("global")
        self._registries = [self._controller_registry, self._global_registry]
        self._controller_prefixes: dict[type, str] = {}

    def set_controller_prefixes(self, prefixes: dict[type, str]) -> None:
        """Controller prefix 매핑 설정"""
        self._controller_prefixes = prefixes

    def collect_handlers(self) -> None:
        """
        ContainerManager에서 ErrorHandlerContainer를 수집

        각 핸들러를 Controller 스코프 또는 글로벌 스코프 Registry에 등록합니다.
        """
        # 기존 항목 초기화
        self._controller_registry._entries.clear()
        self._global_registry._entries.clear()

        container_manager = get_current_manager()

        for containers in container_manager.get_all_containers().values():
            for container in containers:
                if not isinstance(container, ErrorHandlerContainer):
                    continue

                # 스코프에 따라 Registry에 등록
                if container.is_controller_scope():
                    self._controller_registry.add(container)
                else:
                    self._global_registry.add(container)

    def find_handler(
        self,
        exception: Exception,
        request_path: str,
    ) -> ErrorHandlerContainer | None:
        """
        예외와 요청 경로에 맞는 핸들러 찾기

        우선순위:
            1. Controller 스코프 + 정확한 예외 타입
            2. Controller 스코프 + 부모 예외 타입
            3. 글로벌 스코프 + 정확한 예외 타입
            4. 글로벌 스코프 + 부모 예외 타입
        """
        # Controller 스코프 먼저 검색
        handler = self._controller_registry.find_handler(exception, request_path)
        if handler:
            return handler

        # 글로벌 스코프 검색
        return self._global_registry.find_handler(exception, request_path)

    async def call_handler(
        self,
        handler: ErrorHandlerContainer,
        exception: Exception,
        request: "HttpRequest",
    ) -> Any:
        """
        에러 핸들러 메서드 호출

        핸들러 메서드의 타입 힌트를 확인하여 request 파라미터가 있으면 전달합니다.

        Args:
            handler: 에러 핸들러 Container
            exception: 발생한 예외
            request: HTTP 요청

        Returns:
            핸들러 반환값
        """
        import inspect
        from bloom.web.http import HttpRequest

        # owner 인스턴스 가져오기
        owner_instance = None
        if handler.owner_cls:
            container_manager = get_current_manager()
            owner_instance = container_manager.get_instance(
                handler.owner_cls, raise_exception=False
            )

        # 핸들러 메서드의 파라미터 검사
        sig = inspect.signature(handler.handler_method)
        params = list(sig.parameters.values())

        # self 제외하고 파라미터 이름과 타입 힌트 확인
        needs_request = False
        for param in params:
            if param.name == "self":
                continue
            if param.annotation is HttpRequest or param.name == "request":
                needs_request = True
                break

        # 핸들러 호출
        if owner_instance:
            if needs_request:
                result = handler.handler_method(owner_instance, exception, request)
            else:
                result = handler.handler_method(owner_instance, exception)
        else:
            if needs_request:
                result = handler.handler_method(exception, request)
            else:
                result = handler.handler_method(exception)

        # async 함수인 경우 await
        if asyncio.iscoroutine(result):
            result = await result

        return result

    @property
    def controller_registry(self) -> ErrorHandlerRegistry:
        """Controller 스코프 Registry"""
        return self._controller_registry

    @property
    def global_registry(self) -> ErrorHandlerRegistry:
        """글로벌 스코프 Registry"""
        return self._global_registry

    def __repr__(self) -> str:
        controller_count = len(self._controller_registry._entries)
        global_count = len(self._global_registry._entries)
        return (
            f"ErrorHandlerManager("
            f"controller={controller_count}, global={global_count})"
        )
