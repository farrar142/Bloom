"""
미들웨어 체인

여러 미들웨어를 그룹화하고 실행 순서를 제어합니다.
Router에서 자동으로 수집되어 요청/응답 처리 시 실행됩니다.

설정 방법:
    MiddlewareChain은 @Factory를 통해 생성하고, *middlewares: Middleware로
    모든 Middleware 서브클래스 인스턴스를 자동 주입받습니다.

    ```python
    from vessel import Component
    from vessel.core.decorators import Factory
    from vessel.web.middleware import Middleware, MiddlewareChain

    @Component
    class MiddlewareConfiguration:
        @Factory
        def middleware_chain(self, *middlewares: Middleware) -> MiddlewareChain:
            chain = MiddlewareChain()
            # 모든 Middleware 서브클래스 인스턴스가 자동 주입됨
            chain.add_group_after(*middlewares)
            return chain
    ```

그룹 관리:
    미들웨어를 그룹으로 묶어 일괄 활성화/비활성화 가능

    ```python
    chain = MiddlewareChain()

    # 기본 그룹 뒤에 추가
    chain.add_group_after(auth_middleware, logging_middleware)

    # 특정 그룹 앞에 추가
    security_group = chain.add_group_before(cors_middleware, target_group=auth_group)

    # 그룹 비활성화
    security_group.disable()
    ```

개별 미들웨어 제어:
    ```python
    # 특정 미들웨어만 비활성화
    chain.disable(debug_middleware)

    # 다시 활성화
    chain.enable(debug_middleware)
    ```
"""

from typing import Any, Optional

from ..http import HttpRequest, HttpResponse

from .base import Middleware
from .group import MiddlewareGroup


class MiddlewareChain:
    """
    미들웨어 체인 관리

    여러 미들웨어 그룹을 관리하고 실행 순서를 제어합니다.
    Router.dispatch()에서 자동으로 실행됩니다.

    실행 순서:
        요청: groups[0] → groups[1] → ... → groups[n] → 핸들러
        응답: 핸들러 → groups[n] → ... → groups[1] → groups[0]

    사용 예시:
        ```python
        @Component
        class MiddlewareConfig:
            auth: AuthMiddleware
            logging: LoggingMiddleware
            cors: CorsMiddleware

            @Factory
            def middleware_chain(self) -> MiddlewareChain:
                chain = MiddlewareChain()

                # 순서: cors → auth → logging → 핸들러
                chain.add_group_after(self.cors)
                chain.add_group_after(self.auth)
                chain.add_group_after(self.logging)

                return chain
        ```

    또는 varargs 인젝션 사용:
        ```python
        @Component
        class MiddlewareConfig:
            @Factory
            def middleware_chain(self, *middlewares: Middleware) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.add_group_after(*middlewares)
                return chain
        ```
    """

    def __init__(self):
        self.groups: list[MiddlewareGroup] = []
        self.default_group = MiddlewareGroup("default")
        self.groups.append(self.default_group)
        self.disabled_middlewares: set = set()

    def get_default_group(self) -> MiddlewareGroup:
        """기본 그룹 반환"""
        return self.default_group

    def add_group(self, name: str) -> MiddlewareGroup:
        """
        새 그룹 추가 (마지막에)

        Args:
            name: 그룹 이름

        Returns:
            생성된 그룹
        """
        group = MiddlewareGroup(name)
        self.groups.append(group)
        return group

    def add_group_before(
        self,
        *middlewares: Middleware,
        target_group: Optional[MiddlewareGroup] = None,
    ) -> MiddlewareGroup:
        """
        특정 그룹 앞에 새 그룹 추가

        Args:
            *middlewares: 추가할 미들웨어들
            target_group: 대상 그룹 (None이면 default 그룹 앞)

        Returns:
            생성된 그룹
        """
        target = target_group or self.default_group
        index = self.groups.index(target)

        new_group = MiddlewareGroup(f"before_{target.name}")
        new_group.add(*middlewares)
        self.groups.insert(index, new_group)

        return new_group

    def add_group_after(
        self,
        *middlewares: Middleware,
        target_group: Optional[MiddlewareGroup] = None,
    ) -> MiddlewareGroup:
        """
        특정 그룹 뒤에 새 그룹 추가

        Args:
            *middlewares: 추가할 미들웨어들
            target_group: 대상 그룹 (None이면 default 그룹 뒤)

        Returns:
            생성된 그룹
        """
        target = target_group or self.default_group
        index = self.groups.index(target) + 1

        new_group = MiddlewareGroup(f"after_{target.name}")
        new_group.add(*middlewares)
        self.groups.insert(index, new_group)

        return new_group

    def disable(self, *middlewares: Middleware) -> "MiddlewareChain":
        """
        특정 미들웨어 비활성화

        Args:
            *middlewares: 비활성화할 미들웨어들

        Returns:
            self (메서드 체이닝용)
        """
        for middleware in middlewares:
            self.disabled_middlewares.add(type(middleware))
        return self

    def enable(self, *middlewares: Middleware) -> "MiddlewareChain":
        """
        특정 미들웨어 활성화

        Args:
            *middlewares: 활성화할 미들웨어들

        Returns:
            self (메서드 체이닝용)
        """
        for middleware in middlewares:
            self.disabled_middlewares.discard(type(middleware))
        return self

    def get_all_middlewares(self) -> list[Middleware]:
        """
        모든 활성화된 미들웨어를 순서대로 반환

        Returns:
            미들웨어 리스트
        """
        all_middlewares = []

        for group in self.groups:
            if not group.enabled:
                continue

            for middleware in group.middlewares:
                # 개별적으로 비활성화된 미들웨어는 제외
                if type(middleware) not in self.disabled_middlewares:
                    all_middlewares.append(middleware)

        return all_middlewares

    async def execute_request(self, request: HttpRequest) -> Optional[Any]:
        """
        요청 처리 단계 실행

        Args:
            request: HTTP 요청

        Returns:
            None: 정상 진행
            Any: early return 값
        """
        for middleware in self.get_all_middlewares():
            result = await middleware.process_request(request)
            if result is not None:
                # Early return
                return result
        return None

    async def execute_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        """
        응답 처리 단계 실행 (역순)

        Args:
            request: HTTP 요청
            response: HTTP 응답

        Returns:
            처리된 응답
        """
        # 역순으로 실행
        for middleware in reversed(self.get_all_middlewares()):
            response = await middleware.process_response(request, response)

        return response

    def __repr__(self) -> str:
        active_count = len(self.get_all_middlewares())
        return f"MiddlewareChain(groups={len(self.groups)}, active_middlewares={active_count})"
