"""OAuth2 프로토콜 지원 테스트"""

import pytest
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

from bloom.web.auth import (
    OAuth2Config,
    OAuth2Token,
    OAuth2Error,
    InvalidGrantError,
    InvalidClientError,
    InvalidTokenError,
    OAuth2RequestError,
    OAuth2Flow,
    OAuth2FlowComponent,
    generate_pkce_pair,
)


# =============================================================================
# 테스트용 Config
# =============================================================================


@dataclass
class MockOAuthConfig(OAuth2Config):
    """테스트용 OAuth2 설정"""

    client_id: str = "test-client-id"
    client_secret: str = "test-client-secret"
    authorization_url: str = "https://example.com/oauth/authorize"
    token_url: str = "https://example.com/oauth/token"
    redirect_uri: str = "http://localhost:8000/callback"
    scopes: list[str] = field(default_factory=lambda: ["openid", "email"])


@dataclass
class GoogleOAuthConfig(OAuth2Config):
    """Google OAuth2 설정 예시"""

    client_id: str = ""
    client_secret: str = ""
    authorization_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url: str = "https://oauth2.googleapis.com/token"
    redirect_uri: str = "http://localhost:8000/auth/google/callback"
    scopes: list[str] = field(default_factory=lambda: ["openid", "email", "profile"])
    extra_authorization_params: dict[str, str] = field(
        default_factory=lambda: {"access_type": "offline", "prompt": "consent"}
    )


# =============================================================================
# OAuth2Config 테스트
# =============================================================================


class TestOAuth2Config:
    """OAuth2Config 테스트"""

    def test_config_creation(self):
        """기본 설정 생성"""
        config = MockOAuthConfig()

        assert config.client_id == "test-client-id"
        assert config.client_secret == "test-client-secret"
        assert config.authorization_url == "https://example.com/oauth/authorize"
        assert config.token_url == "https://example.com/oauth/token"
        assert config.redirect_uri == "http://localhost:8000/callback"
        assert config.scopes == ["openid", "email"]

    def test_google_config(self):
        """Google OAuth 설정 예시"""
        config = GoogleOAuthConfig(
            client_id="google-client-id",
            client_secret="google-client-secret",
        )

        assert (
            config.authorization_url == "https://accounts.google.com/o/oauth2/v2/auth"
        )
        assert "openid" in config.scopes
        assert config.extra_authorization_params["access_type"] == "offline"


# =============================================================================
# OAuth2Token 테스트
# =============================================================================


class TestOAuth2Token:
    """OAuth2Token 테스트"""

    def test_token_from_response(self):
        """응답에서 토큰 생성"""
        response_data = {
            "access_token": "access-token-123",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "refresh-token-456",
            "scope": "openid email",
            "id_token": "id-token-789",
        }

        token = OAuth2Token.from_response(response_data)

        assert token.access_token == "access-token-123"
        assert token.token_type == "Bearer"
        assert token.expires_in == 3600
        assert token.refresh_token == "refresh-token-456"
        assert token.scope == "openid email"
        assert token.id_token == "id-token-789"
        assert token.raw_response == response_data

    def test_token_minimal_response(self):
        """최소 응답 (access_token만 있는 경우)"""
        response_data = {"access_token": "access-token-only"}

        token = OAuth2Token.from_response(response_data)

        assert token.access_token == "access-token-only"
        assert token.token_type == "Bearer"  # 기본값
        assert token.expires_in == 0
        assert token.refresh_token == ""


# =============================================================================
# OAuth2Error 테스트
# =============================================================================


class TestOAuth2Error:
    """OAuth2Error 테스트"""

    def test_oauth2_error(self):
        """기본 OAuth2 에러"""
        error = OAuth2Error("invalid_request", "Missing required parameter")

        assert error.error == "invalid_request"
        assert error.error_description == "Missing required parameter"
        assert str(error) == "invalid_request: Missing required parameter"

    def test_invalid_grant_error(self):
        """InvalidGrantError"""
        error = InvalidGrantError()

        assert error.error == "invalid_grant"
        assert "invalid or expired" in error.error_description

    def test_invalid_client_error(self):
        """InvalidClientError"""
        error = InvalidClientError("Wrong client secret")

        assert error.error == "invalid_client"
        assert error.error_description == "Wrong client secret"

    def test_invalid_token_error(self):
        """InvalidTokenError"""
        error = InvalidTokenError()

        assert error.error == "invalid_token"

    def test_oauth2_request_error(self):
        """OAuth2RequestError"""
        error = OAuth2RequestError(500, '{"error": "server_error"}')

        assert error.status_code == 500
        assert error.error == "request_failed"


# =============================================================================
# OAuth2Flow 테스트
# =============================================================================


class TestOAuth2Flow:
    """OAuth2Flow 테스트"""

    def test_get_authorization_url_basic(self):
        """기본 authorization URL 생성"""
        flow = OAuth2Flow()
        config = MockOAuthConfig()

        url = flow.get_authorization_url(config, state="random-state-123")

        assert url.startswith("https://example.com/oauth/authorize?")
        assert "client_id=test-client-id" in url
        assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fcallback" in url
        assert "response_type=code" in url
        assert "state=random-state-123" in url
        assert "scope=openid+email" in url

    def test_get_authorization_url_with_pkce(self):
        """PKCE 파라미터 포함"""
        flow = OAuth2Flow()
        config = MockOAuthConfig()

        url = flow.get_authorization_url(
            config,
            state="state",
            code_challenge="challenge-abc",
            code_challenge_method="S256",
        )

        assert "code_challenge=challenge-abc" in url
        assert "code_challenge_method=S256" in url

    def test_get_authorization_url_with_nonce(self):
        """OpenID Connect nonce 포함"""
        flow = OAuth2Flow()
        config = MockOAuthConfig()

        url = flow.get_authorization_url(config, state="state", nonce="nonce-123")

        assert "nonce=nonce-123" in url

    def test_get_authorization_url_with_extra_params(self):
        """추가 파라미터 포함"""
        flow = OAuth2Flow()
        config = GoogleOAuthConfig(
            client_id="google-id",
            client_secret="google-secret",
        )

        url = flow.get_authorization_url(config, state="state")

        # extra_authorization_params가 포함되어야 함
        assert "access_type=offline" in url
        assert "prompt=consent" in url

    @pytest.mark.asyncio
    async def test_exchange_code_success(self):
        """code → token 교환 성공"""
        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-access-token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "new-refresh-token",
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        flow = OAuth2Flow(http_client=mock_client)
        config = MockOAuthConfig()

        token = await flow.exchange_code(config, code="auth-code-123")

        assert token.access_token == "new-access-token"
        assert token.refresh_token == "new-refresh-token"

        # POST 요청 확인
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://example.com/oauth/token"
        assert call_args[1]["data"]["grant_type"] == "authorization_code"
        assert call_args[1]["data"]["code"] == "auth-code-123"

    @pytest.mark.asyncio
    async def test_exchange_code_with_pkce(self):
        """PKCE code_verifier 포함"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "token"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        flow = OAuth2Flow(http_client=mock_client)
        config = MockOAuthConfig()

        await flow.exchange_code(config, code="code", code_verifier="verifier-123")

        call_args = mock_client.post.call_args
        assert call_args[1]["data"]["code_verifier"] == "verifier-123"

    @pytest.mark.asyncio
    async def test_exchange_code_invalid_grant(self):
        """invalid_grant 에러"""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Code expired",
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        flow = OAuth2Flow(http_client=mock_client)
        config = MockOAuthConfig()

        with pytest.raises(InvalidGrantError) as exc_info:
            await flow.exchange_code(config, code="expired-code")

        assert exc_info.value.error_description == "Code expired"

    @pytest.mark.asyncio
    async def test_exchange_code_invalid_client(self):
        """invalid_client 에러"""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {
            "error": "invalid_client",
            "error_description": "Client authentication failed",
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        flow = OAuth2Flow(http_client=mock_client)
        config = MockOAuthConfig()

        with pytest.raises(InvalidClientError):
            await flow.exchange_code(config, code="code")

    @pytest.mark.asyncio
    async def test_refresh_access_token_success(self):
        """토큰 갱신 성공"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "refreshed-access-token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        flow = OAuth2Flow(http_client=mock_client)
        config = MockOAuthConfig()

        token = await flow.refresh_access_token(
            config, refresh_token="old-refresh-token"
        )

        assert token.access_token == "refreshed-access-token"

        call_args = mock_client.post.call_args
        assert call_args[1]["data"]["grant_type"] == "refresh_token"
        assert call_args[1]["data"]["refresh_token"] == "old-refresh-token"

    @pytest.mark.asyncio
    async def test_refresh_access_token_invalid_token(self):
        """토큰 갱신 실패 (만료된 refresh_token)"""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "invalid_token",
            "error_description": "Refresh token expired",
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        flow = OAuth2Flow(http_client=mock_client)
        config = MockOAuthConfig()

        with pytest.raises(InvalidTokenError):
            await flow.refresh_access_token(config, refresh_token="expired-token")


# =============================================================================
# PKCE 헬퍼 테스트
# =============================================================================


class TestPKCE:
    """PKCE 헬퍼 테스트"""

    def test_generate_pkce_pair(self):
        """PKCE 쌍 생성"""
        verifier, challenge = generate_pkce_pair()

        # verifier: 43자 이상
        assert len(verifier) >= 43

        # challenge: base64url 인코딩
        assert all(c.isalnum() or c in "-_" for c in challenge)

        # 매번 다른 값 생성
        verifier2, challenge2 = generate_pkce_pair()
        assert verifier != verifier2
        assert challenge != challenge2

    def test_pkce_challenge_verification(self):
        """PKCE challenge 검증 (SHA256)"""
        import hashlib
        import base64

        verifier, challenge = generate_pkce_pair()

        # challenge는 SHA256(verifier)의 base64url 인코딩이어야 함
        digest = hashlib.sha256(verifier.encode()).digest()
        expected_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

        assert challenge == expected_challenge


# =============================================================================
# OAuth2FlowComponent (DI) 테스트
# =============================================================================


class TestOAuth2FlowComponent:
    """OAuth2FlowComponent DI 테스트"""

    def test_component_inherits_flow(self):
        """OAuth2Flow를 상속하는지 확인"""
        assert issubclass(OAuth2FlowComponent, OAuth2Flow)

    def test_component_is_decorated(self):
        """@Component 데코레이터가 적용되었는지 확인"""
        from bloom.core.container import ComponentContainer

        container = ComponentContainer.get_container(OAuth2FlowComponent)
        assert container is not None


# =============================================================================
# 통합 테스트 (실제 DI 사용)
# =============================================================================


class TestOAuth2Integration:
    """OAuth2 통합 테스트"""

    def test_oauth2_flow_di_injection(self, reset_container_manager):
        """DI를 통한 OAuth2Flow 주입"""
        from bloom import Application, Component
        import bloom.web.auth.oauth2 as oauth2_module

        @Component
        class AuthService:
            flow: OAuth2FlowComponent

            def get_login_url(self, config: OAuth2Config, state: str) -> str:
                return self.flow.get_authorization_url(config, state)

        # OAuth2FlowComponent가 있는 모듈도 스캔
        app = Application("test").scan(oauth2_module).ready()

        service = app.manager.get_instance(AuthService)
        assert service.flow is not None

        config = MockOAuthConfig()
        url = service.get_login_url(config, "test-state")

        assert "client_id=test-client-id" in url
        assert "state=test-state" in url

    @pytest.mark.asyncio
    async def test_full_oauth2_flow(self, reset_container_manager):
        """전체 OAuth2 플로우 시뮬레이션"""
        from bloom import Application, Component

        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "integration-test-token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "integration-refresh-token",
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        @Component
        class AuthService:
            def __init__(self):
                self.flow = OAuth2Flow(http_client=mock_client)

            def get_login_url(self, config: OAuth2Config, state: str) -> str:
                return self.flow.get_authorization_url(config, state)

            async def handle_callback(
                self, config: OAuth2Config, code: str
            ) -> OAuth2Token:
                return await self.flow.exchange_code(config, code)

        app = Application("test").scan(__name__).ready()

        service = app.manager.get_instance(AuthService)
        config = MockOAuthConfig()

        # 1. 로그인 URL 생성
        login_url = service.get_login_url(config, "csrf-state")
        assert "state=csrf-state" in login_url

        # 2. 콜백에서 토큰 교환
        token = await service.handle_callback(config, "auth-code")
        assert token.access_token == "integration-test-token"
        assert token.refresh_token == "integration-refresh-token"
