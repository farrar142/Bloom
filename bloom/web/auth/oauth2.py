"""OAuth2 프로토콜 지원

OAuth2 Authorization Code Flow를 지원하는 클래스들을 제공합니다.
각 Provider(Google, Kakao, GitHub 등)는 사용자가 직접 Config를 정의합니다.

사용 예시:
    ```python
    from dataclasses import dataclass
    from bloom.web.auth import OAuth2Config, OAuth2Flow, OAuth2Token

    # 1. Provider 설정 정의
    @dataclass
    class GoogleOAuthConfig(OAuth2Config):
        client_id: str = ""
        client_secret: str = ""
        authorization_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
        token_url: str = "https://oauth2.googleapis.com/token"
        redirect_uri: str = "http://localhost:8000/auth/callback"
        scopes: list[str] = field(default_factory=lambda: ["openid", "email"])

    # 2. Controller에서 사용
    @Controller
    class AuthController:
        flow: OAuth2Flow
        config: GoogleOAuthConfig

        @Get("/login")
        def login(self) -> HttpResponse:
            state = secrets.token_urlsafe(16)
            url = self.flow.get_authorization_url(self.config, state)
            return HttpResponse.redirect(url)

        @Get("/callback")
        async def callback(self, code: str, state: str) -> HttpResponse:
            token = await self.flow.exchange_code(self.config, code)
            return HttpResponse.ok({"access_token": token.access_token})
    ```
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

from bloom.core import Component
from bloom.core.exceptions import (
    OAuth2Error,
    InvalidGrantError,
    InvalidClientError,
    InvalidTokenError,
    OAuth2RequestError,
)


# =============================================================================
# OAuth2 Config
# =============================================================================


@dataclass
class OAuth2Config(ABC):
    """
    OAuth2 설정 베이스 클래스

    각 Provider별로 상속하여 구현합니다.

    사용 예시:
        @dataclass
        class GoogleOAuthConfig(OAuth2Config):
            client_id: str = EnvStr("GOOGLE_CLIENT_ID")
            client_secret: str = EnvStr("GOOGLE_CLIENT_SECRET")
            authorization_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
            token_url: str = "https://oauth2.googleapis.com/token"
            redirect_uri: str = "http://localhost:8000/auth/google/callback"
            scopes: list[str] = field(default_factory=lambda: ["openid", "email", "profile"])
    """

    # 필수 설정
    client_id: str = ""
    client_secret: str = ""
    authorization_url: str = ""
    token_url: str = ""
    redirect_uri: str = ""

    # 선택 설정
    scopes: list[str] = field(default_factory=list)

    # 추가 파라미터 (Provider별 커스텀)
    extra_authorization_params: dict[str, str] = field(default_factory=dict)
    extra_token_params: dict[str, str] = field(default_factory=dict)


# =============================================================================
# OAuth2 Token
# =============================================================================


@dataclass
class OAuth2Token:
    """
    OAuth2 토큰 응답

    Attributes:
        access_token: 액세스 토큰
        token_type: 토큰 타입 (보통 "Bearer")
        expires_in: 만료 시간 (초)
        refresh_token: 리프레시 토큰 (없을 수 있음)
        scope: 부여된 스코프 (공백 구분 문자열)
        id_token: OpenID Connect ID 토큰 (OIDC 사용 시)
        raw_response: 원본 응답 (추가 필드 접근용)
    """

    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 0
    refresh_token: str = ""
    scope: str = ""
    id_token: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> "OAuth2Token":
        """OAuth2 토큰 응답에서 생성"""
        return cls(
            access_token=data.get("access_token", ""),
            token_type=data.get("token_type", "Bearer"),
            expires_in=data.get("expires_in", 0),
            refresh_token=data.get("refresh_token", ""),
            scope=data.get("scope", ""),
            id_token=data.get("id_token", ""),
            raw_response=data,
        )


# =============================================================================
# OAuth2 Flow
# =============================================================================


class OAuth2Flow:
    """
    OAuth2 Authorization Code Flow 처리

    Authorization Code Flow의 핵심 메서드들을 제공합니다:
    - get_authorization_url: 로그인 페이지 URL 생성
    - exchange_code: authorization code → access token 교환
    - refresh_token: 토큰 갱신

    사용 예시:
        flow = OAuth2Flow()

        # 1. 로그인 URL 생성
        url = flow.get_authorization_url(config, state="random-state")

        # 2. 콜백에서 code → token 교환
        token = await flow.exchange_code(config, code="auth-code")

        # 3. 토큰 갱신
        new_token = await flow.refresh_token(config, token.refresh_token)
    """

    def __init__(self, http_client: Any = None):
        """
        OAuth2Flow 초기화

        Args:
            http_client: HTTP 클라이언트 (None이면 httpx 사용)
        """
        self._client = http_client

    def get_authorization_url(
        self,
        config: OAuth2Config,
        state: str,
        *,
        nonce: str = "",
        code_challenge: str = "",
        code_challenge_method: str = "",
        extra_params: dict[str, str] | None = None,
    ) -> str:
        """
        OAuth2 로그인 페이지 URL 생성

        Args:
            config: OAuth2 설정
            state: CSRF 방지용 state 값 (클라이언트에서 생성)
            nonce: OpenID Connect nonce (OIDC 사용 시)
            code_challenge: PKCE code_challenge (PKCE 사용 시)
            code_challenge_method: PKCE 방식 ("S256" 또는 "plain")
            extra_params: 추가 파라미터

        Returns:
            로그인 페이지 URL
        """
        params: dict[str, str] = {
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "response_type": "code",
            "state": state,
        }

        if config.scopes:
            params["scope"] = " ".join(config.scopes)

        if nonce:
            params["nonce"] = nonce

        # PKCE 지원
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = code_challenge_method or "S256"

        # Config의 추가 파라미터
        params.update(config.extra_authorization_params)

        # 메서드 호출 시 추가 파라미터
        if extra_params:
            params.update(extra_params)

        return f"{config.authorization_url}?{urlencode(params)}"

    async def exchange_code(
        self,
        config: OAuth2Config,
        code: str,
        *,
        code_verifier: str = "",
    ) -> OAuth2Token:
        """
        Authorization code를 access token으로 교환

        Args:
            config: OAuth2 설정
            code: authorization code (콜백에서 받은 값)
            code_verifier: PKCE code_verifier (PKCE 사용 시)

        Returns:
            OAuth2Token 객체

        Raises:
            InvalidGrantError: code가 유효하지 않거나 만료됨
            InvalidClientError: client_id/secret이 유효하지 않음
            OAuth2RequestError: 요청 실패
        """
        data = {
            "grant_type": "authorization_code",
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "code": code,
            "redirect_uri": config.redirect_uri,
        }

        # PKCE 지원
        if code_verifier:
            data["code_verifier"] = code_verifier

        # Config의 추가 파라미터
        data.update(config.extra_token_params)

        return await self._request_token(config.token_url, data)

    async def refresh_access_token(
        self,
        config: OAuth2Config,
        refresh_token: str,
    ) -> OAuth2Token:
        """
        Refresh token으로 새 access token 발급

        Args:
            config: OAuth2 설정
            refresh_token: 리프레시 토큰

        Returns:
            새로운 OAuth2Token 객체

        Raises:
            InvalidTokenError: refresh_token이 유효하지 않거나 만료됨
            OAuth2RequestError: 요청 실패
        """
        data = {
            "grant_type": "refresh_token",
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "refresh_token": refresh_token,
        }

        return await self._request_token(config.token_url, data)

    async def _request_token(self, url: str, data: dict[str, str]) -> OAuth2Token:
        """토큰 엔드포인트에 POST 요청"""
        if self._client is not None:
            # 커스텀 클라이언트 사용 (테스트용)
            response = await self._client.post(url, data=data)
            status_code = response.status_code
            response_data = response.json()
        elif HTTPX_AVAILABLE:
            # httpx 사용
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                status_code = response.status_code
                response_data = response.json()
        else:
            raise RuntimeError(
                "httpx is required for OAuth2. Install it with: pip install httpx"
            )

        # 에러 처리
        if status_code != 200:
            error = response_data.get("error", "unknown_error")
            error_description = response_data.get("error_description", "")

            if error == "invalid_grant":
                raise InvalidGrantError(error_description)
            elif error == "invalid_client":
                raise InvalidClientError(error_description)
            elif error == "invalid_token":
                raise InvalidTokenError(error_description)
            else:
                raise OAuth2Error(error, error_description)

        return OAuth2Token.from_response(response_data)


# =============================================================================
# PKCE 헬퍼
# =============================================================================


def generate_pkce_pair() -> tuple[str, str]:
    """
    PKCE code_verifier와 code_challenge 쌍 생성

    Returns:
        (code_verifier, code_challenge) 튜플

    사용 예시:
        verifier, challenge = generate_pkce_pair()
        url = flow.get_authorization_url(config, state, code_challenge=challenge)
        # 콜백에서
        token = await flow.exchange_code(config, code, code_verifier=verifier)
    """
    import secrets
    import hashlib
    import base64

    # code_verifier: 43-128자의 랜덤 문자열
    code_verifier = secrets.token_urlsafe(32)

    # code_challenge: SHA256(code_verifier)의 base64url 인코딩
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    return code_verifier, code_challenge


# =============================================================================
# OAuth2Flow Component (DI용)
# =============================================================================


@Component
class OAuth2FlowComponent(OAuth2Flow):
    """
    DI 컨테이너에서 사용할 OAuth2Flow

    @Component로 등록되어 있어 다른 컴포넌트에서 주입받을 수 있습니다.

    사용 예시:
        @Controller
        class AuthController:
            flow: OAuth2FlowComponent  # 자동 주입

            @Get("/login")
            def login(self) -> HttpResponse:
                ...
    """

    pass
