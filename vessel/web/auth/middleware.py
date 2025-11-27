"""
인증 미들웨어

여러 Authenticator를 그룹별로 관리하며 인증을 수행합니다.

사용 예시:
    ```python
    from vessel import Component
    from vessel.core.decorators import Factory
    from vessel.web.auth import Authenticator, Authentication, AuthMiddleware
    from vessel.web.middleware import MiddlewareChain

    @Component
    class MiddlewareConfig:
        @Factory
        def auth_middleware(
            self,
            jwt_auth: JwtAuthenticator,
            api_key_auth: ApiKeyAuthenticator,
        ) -> AuthMiddleware:
            return (
                AuthMiddleware()
                # API 그룹: API 키 인증, 필수
                .group("api")
                .register(api_key_auth)
                .include("/api/")
                .require()
                # Admin 그룹: JWT 인증, 필수
                .group("admin")
                .register(jwt_auth)
                .include("/admin/")
                .require()
                # Public 그룹: 인증 선택적
                .group("public")
                .register(jwt_auth)
                .exclude("/health", "/public/")
            )
    ```
"""

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
import inspect
from typing import Any, Optional

from .authenticator import Authentication, Authenticator, ANONYMOUS
from .authorize import AuthorizeElement
from ..http import HttpRequest, HttpResponse
from ..middleware.base import Middleware


@dataclass
class AuthGroup:
    """
    인증 그룹

    특정 경로 패턴에 대해 인증기, 필수 여부, 제외 경로를 설정합니다.

    Attributes:
        name: 그룹 이름
        authenticators: 등록된 인증기 목록
        include_paths: 이 그룹이 적용될 경로 패턴 (빈 리스트면 모든 경로)
        exclude_paths: 이 그룹에서 제외할 경로 패턴
        require_auth: True이면 인증 실패 시 401 반환
    """

    name: str
    authenticators: list[Authenticator] = field(default_factory=list)
    include_paths: list[str] = field(default_factory=list)
    exclude_paths: list[str] = field(default_factory=list)
    require_auth: bool = False

    def matches(self, path: str) -> bool:
        """경로가 이 그룹에 해당하는지 확인"""
        # exclude 먼저 체크
        for exclude_path in self.exclude_paths:
            if path.startswith(exclude_path):
                return False

        # include가 비어있으면 모든 경로에 매칭
        if not self.include_paths:
            return True

        # include 체크
        for include_path in self.include_paths:
            if path.startswith(include_path):
                return True

        return False


class AuthMiddleware(Middleware):
    """
    인증 미들웨어

    그룹별로 인증기, 필수 여부, 경로 패턴을 설정할 수 있습니다.

    사용법:
        ```python
        AuthMiddleware()
            .group("api")           # 그룹 생성/선택
            .register(api_auth)     # 인증기 등록
            .include("/api/")       # 적용 경로
            .require()              # 인증 필수
            .group("public")        # 다른 그룹
            .register(jwt_auth)
            .exclude("/health")     # 제외 경로
        ```
    """

    def __init__(self):
        super().__init__()
        self._groups: dict[str, AuthGroup] = {}
        self._current_group: AuthGroup | None = None
        # 기본 그룹 생성
        self._default_group = AuthGroup(name="default")
        self._groups["default"] = self._default_group
        self._current_group = self._default_group

    def group(self, name: str) -> "AuthMiddleware":
        """
        그룹 생성 또는 선택

        Args:
            name: 그룹 이름

        Returns:
            self (메서드 체이닝용)
        """
        if name not in self._groups:
            self._groups[name] = AuthGroup(name=name)
        self._current_group = self._groups[name]
        return self

    def register(self, *authenticators: Authenticator) -> "AuthMiddleware":
        """
        현재 그룹에 인증기 등록

        Args:
            *authenticators: 등록할 인증기들

        Returns:
            self (메서드 체이닝용)
        """
        if self._current_group:
            self._current_group.authenticators.extend(authenticators)
        return self

    def require(self, require: bool = True) -> "AuthMiddleware":
        """
        현재 그룹의 인증 필수 여부 설정

        Args:
            require: True이면 인증 실패 시 401 반환

        Returns:
            self (메서드 체이닝용)
        """
        if self._current_group:
            self._current_group.require_auth = require
        return self

    def include(self, *paths: str) -> "AuthMiddleware":
        """
        현재 그룹의 적용 경로 설정

        Args:
            *paths: 이 그룹이 적용될 경로들

        Returns:
            self (메서드 체이닝용)
        """
        if self._current_group:
            self._current_group.include_paths.extend(paths)
        return self

    def exclude(self, *paths: str) -> "AuthMiddleware":
        """
        현재 그룹의 제외 경로 설정

        Args:
            *paths: 인증을 건너뛸 경로들

        Returns:
            self (메서드 체이닝용)
        """
        if self._current_group:
            self._current_group.exclude_paths.extend(paths)
        return self

    def get_group(self, name: str) -> AuthGroup | None:
        """그룹 조회"""
        return self._groups.get(name)

    def _find_matching_group(self, path: str) -> AuthGroup | None:
        """
        경로에 매칭되는 그룹 찾기

        include_paths가 설정된 그룹을 우선 확인하고,
        매칭되는 그룹이 없으면 default 그룹 반환
        """
        # include_paths가 설정된 그룹 먼저 확인
        for group in self._groups.values():
            if group.name == "default":
                continue
            if group.include_paths and group.matches(path):
                return group

        # default 그룹 확인
        if self._default_group.matches(path):
            return self._default_group

        return None

    async def process_request(self, request: HttpRequest) -> Optional[HttpResponse]:
        """
        인증 처리 (process_request는 사용하지 않고 _process_request에서 처리)
        """
        return None

    async def _process_request(
        self, request: HttpRequest, handler: Any = None
    ) -> AsyncGenerator[HttpResponse | None, HttpResponse]:
        """
        인증 및 인가 처리

        1. 경로에 매칭되는 그룹 찾기
        2. 그룹의 인증기들로 인증 시도
        3. 인증 성공 시 request.auth에 저장
        4. 인증 필수인데 실패하면 401 반환
        5. @Authorize 검사 - 실패 시 403 반환
        """
        # 매칭되는 그룹 찾기
        group = self._find_matching_group(request.path)

        if group is None:
            # 매칭되는 그룹 없음 - 인증 없이 통과
            request.auth = ANONYMOUS
        else:
            # 인증 시도
            authentication = await self._try_authenticate(request, group)

            # request에 인증 정보 저장
            request.auth = authentication

            # 인증 필수인데 실패한 경우
            if group.require_auth and not authentication.is_authenticated():
                yield HttpResponse(
                    status_code=401,
                    body={
                        "error": "Unauthorized",
                        "message": "Authentication required",
                    },
                )
                return

        # @Authorize 검사
        if handler is not None:
            authorize_response = self._check_authorize(request, handler)
            if authorize_response is not None:
                yield authorize_response
                return

        # 다음 미들웨어/핸들러로 진행
        response = yield
        yield response

    def _check_authorize(
        self, request: HttpRequest, handler: Any
    ) -> HttpResponse | None:
        """
        핸들러의 @Authorize 검사

        Args:
            request: HTTP 요청 (request.auth 사용)
            handler: HttpMethodHandler

        Returns:
            None: 통과
            HttpResponse: 403 Forbidden
        """
        # handler의 elements에서 AuthorizeElement 찾기
        if not hasattr(handler, "elements"):
            return None

        for element in handler.elements:
            if isinstance(element, AuthorizeElement):
                # metadata에서 target_type과 predicate 가져오기
                target_type = element.metadata.get("authorize_target_type")
                predicate = element.metadata.get("authorize_predicate")

                if target_type is None or predicate is None:
                    continue

                # target_type에 맞는 값 가져오기
                target_value = self._get_target_value(request, target_type)

                if target_value is None:
                    # target 값이 없으면 실패
                    return HttpResponse(
                        status_code=403,
                        body={
                            "error": "Forbidden",
                            "message": f"Required {target_type.__name__} not available",
                        },
                    )

                # predicate 검사
                if not predicate(target_value):
                    return HttpResponse(
                        status_code=403,
                        body={"error": "Forbidden", "message": "Access denied"},
                    )

        return None

    def _get_target_value(self, request: HttpRequest, target_type: type) -> Any:
        """
        target_type에 맞는 값을 request에서 가져오기

        현재 지원:
            - Authentication: request.auth
        """
        from .authenticator import Authentication

        if inspect.isclass(target_type):
            if issubclass(target_type, Authentication):
                return request.auth
        else:
            return target_type(request)
        return None

    async def _try_authenticate(
        self, request: HttpRequest, group: AuthGroup
    ) -> Authentication:
        """
        그룹의 인증기들로 인증 시도

        Returns:
            인증 성공 시 Authentication, 실패 시 ANONYMOUS
        """
        for authenticator in group.authenticators:
            # supports() 확인
            if not authenticator.supports(request):
                continue

            # 인증 시도
            result = authenticator.authenticate(request)

            # async 함수인 경우 await
            if asyncio.iscoroutine(result):
                result = await result

            # 인증 성공
            if result is not None and result.is_authenticated():
                return result

        return ANONYMOUS
