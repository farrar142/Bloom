"""
STOMP 인증 모듈

StompAuthenticator 추상 클래스와 StompAuthentication 데이터 클래스를 제공합니다.
사용자는 StompAuthenticator를 상속받아 커스텀 인증 로직을 구현합니다.

사용 예시:
    ```python
    from bloom import Component
    from bloom.web.messaging.auth import StompAuthenticator, StompAuthentication
    from bloom.web.messaging import StompFrame, WebSocketSession

    @Component
    class JwtStompAuthenticator(StompAuthenticator):
        def supports(self, session: WebSocketSession, frame: StompFrame) -> bool:
            # CONNECT 프레임의 login 헤더나 passcode 헤더 확인
            return "Authorization" in frame.headers or "login" in frame.headers

        def authenticate(
            self, session: WebSocketSession, frame: StompFrame
        ) -> StompAuthentication | None:
            token = frame.headers.get("Authorization", "")
            if self.validate_token(token):
                return StompAuthentication(
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
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..session import WebSocketSession, StompFrame


@dataclass
class StompAuthentication:
    """
    STOMP 인증 결과를 담는 데이터 클래스

    Attributes:
        user_id: 인증된 사용자 ID
        authenticated: 인증 성공 여부
        authorities: 권한 목록
        attributes: 추가 속성 (세션에 저장될 데이터)
    """

    user_id: str | None = None
    authenticated: bool = False
    authorities: list[str] = field(default_factory=list)
    attributes: dict = field(default_factory=dict)

    def is_authenticated(self) -> bool:
        """인증 여부 확인"""
        return self.authenticated

    def has_authority(self, authority: str) -> bool:
        """특정 권한 보유 여부 확인"""
        return authority in self.authorities

    def get_attribute(self, key: str, default=None):
        """추가 속성 조회"""
        return self.attributes.get(key, default)


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
            ) -> StompAuthentication | None:
                token = frame.headers.get("Authorization", "").replace("Bearer ", "")
                payload = self.jwt_service.decode(token)
                if payload:
                    return StompAuthentication(
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
    ) -> StompAuthentication | None:
        """
        인증 수행

        Args:
            session: WebSocket 세션
            frame: STOMP CONNECT 프레임

        Returns:
            인증 성공 시 StompAuthentication 객체, 실패 시 None
        """
        ...


# Anonymous 인증 (인증되지 않은 상태)
STOMP_ANONYMOUS = StompAuthentication(authenticated=False)
