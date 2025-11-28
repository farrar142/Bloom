"""
인증 모듈

Authenticator 추상 클래스와 Authentication 데이터 클래스를 제공합니다.
사용자는 Authenticator를 상속받아 커스텀 인증 로직을 구현합니다.

사용 예시:
    ```python
    from bloom import Component
    from bloom.web.auth import Authenticator, Authentication
    from bloom.web.http import HttpRequest

    @Component
    class JwtAuthenticator(Authenticator):
        def supports(self, request: HttpRequest) -> bool:
            return "Authorization" in request.headers

        def authenticate(self, request: HttpRequest) -> Authentication | None:
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            if self.validate_token(token):
                return Authentication(user_id="user123", authenticated=True)
            return None

        def validate_token(self, token: str) -> bool:
            # JWT 검증 로직
            ...
    ```
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from ..http import HttpRequest


@dataclass
class Authentication:
    """
    인증 결과를 담는 데이터 클래스

    Attributes:
        user_id: 인증된 사용자 ID
        authenticated: 인증 성공 여부
        authorities: 권한 목록
    """

    user_id: str | None = None
    authenticated: bool = False
    authorities: list[str] = field(default_factory=list)

    def is_authenticated(self) -> bool:
        """인증 여부 확인"""
        return self.authenticated

    def has_authority(self, authority: str) -> bool:
        """특정 권한 보유 여부 확인"""
        return authority in self.authorities


class Authenticator(ABC):
    """
    인증기 추상 클래스

    사용자는 이 클래스를 상속받아 커스텀 인증 로직을 구현합니다.
    여러 Authenticator를 AuthMiddleware에 등록하여 체이닝할 수 있습니다.

    구현 예시:
        ```python
        @Component
        class ApiKeyAuthenticator(Authenticator):
            def supports(self, request: HttpRequest) -> bool:
                return "X-API-Key" in request.headers

            def authenticate(self, request: HttpRequest) -> Authentication | None:
                api_key = request.headers.get("X-API-Key")
                if self.is_valid_key(api_key):
                    return Authentication(user_id="api-user", authenticated=True)
                return None
        ```
    """

    @abstractmethod
    def supports(self, request: HttpRequest) -> bool:
        """
        이 인증기가 해당 요청을 처리할 수 있는지 확인

        Args:
            request: HTTP 요청

        Returns:
            True이면 authenticate() 호출, False이면 다음 인증기로
        """
        ...

    @abstractmethod
    def authenticate(self, request: HttpRequest) -> Optional["Authentication"]:
        """
        인증 수행

        Args:
            request: HTTP 요청

        Returns:
            인증 성공 시 Authentication 객체, 실패 시 None
        """
        ...


# Anonymous 인증 (인증되지 않은 상태)
ANONYMOUS = Authentication(authenticated=False)
