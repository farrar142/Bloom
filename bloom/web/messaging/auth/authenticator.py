"""
STOMP 인증 모듈

StompAuthenticator 추상 클래스를 제공합니다.
인증 결과는 web/auth의 Authentication을 사용합니다.

사용 예시:
    ```python
    from bloom import Component
    from bloom.web.auth import Authentication
    from bloom.web.messaging.auth import StompAuthenticator
    from bloom.web.messaging import StompFrame, WebSocketSession

    @Component
    class JwtStompAuthenticator(StompAuthenticator):
        def supports(self, session: WebSocketSession, frame: StompFrame) -> bool:
            # CONNECT 프레임의 login 헤더나 passcode 헤더 확인
            return "Authorization" in frame.headers or "login" in frame.headers

        def authenticate(
            self, session: WebSocketSession, frame: StompFrame
        ) -> Authentication | None:
            token = frame.headers.get("Authorization", "")
            if self.validate_token(token):
                return Authentication(
                    user_id="user123",
                    authenticated=True,
                    authorities=["ROLE_USER"]
                )
            return None

        def validate_token(self, token: str) -> bool:
            # JWT 검증 로직
            ...
    ```
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

# Authentication은 web/auth에서 가져옴 (통합)
from bloom.web.auth import Authentication, ANONYMOUS

if TYPE_CHECKING:
    from ..session import WebSocketSession, StompFrame

# 하위 호환성을 위한 별칭
StompAuthentication = Authentication
STOMP_ANONYMOUS = ANONYMOUS


class StompAuthenticator(ABC):
    """
    STOMP 인증기 추상 클래스

    사용자는 이 클래스를 상속받아 커스텀 인증 로직을 구현합니다.
    WebSocketSessionManager에 등록하여 CONNECT 시 인증을 수행합니다.

    STOMP CONNECT 프레임 헤더:
        - login: 사용자 로그인 ID
        - passcode: 비밀번호
        - Authorization: Bearer 토큰 (커스텀)
        - 기타 커스텀 헤더

    구현 예시:
        ```python
        @Component
        class TokenStompAuthenticator(StompAuthenticator):
            jwt_service: JwtService  # DI 주입

            def supports(self, session: WebSocketSession, frame: StompFrame) -> bool:
                return "Authorization" in frame.headers

            def authenticate(
                self, session: WebSocketSession, frame: StompFrame
            ) -> Authentication | None:
                token = frame.headers.get("Authorization", "").replace("Bearer ", "")
                payload = self.jwt_service.decode(token)
                if payload:
                    return Authentication(
                        user_id=payload["sub"],
                        authenticated=True,
                        authorities=payload.get("roles", [])
                    )
                return None
        ```
    """

    @abstractmethod
    def supports(self, session: "WebSocketSession", frame: "StompFrame") -> bool:
        """
        이 인증기가 해당 CONNECT 요청을 처리할 수 있는지 확인

        Args:
            session: WebSocket 세션
            frame: STOMP CONNECT 프레임

        Returns:
            True이면 authenticate() 호출, False이면 다음 인증기로
        """
        ...

    @abstractmethod
    def authenticate(
        self, session: "WebSocketSession", frame: "StompFrame"
    ) -> Authentication | None:
        """
        인증 수행

        Args:
            session: WebSocket 세션
            frame: STOMP CONNECT 프레임

        Returns:
            인증 성공 시 Authentication 객체, 실패 시 None
        """
        ...
