"""
인증/인가 모듈

Authenticator, Authentication, AuthMiddleware, @Authorize 등을 제공합니다.
OAuth2 프로토콜 지원도 포함합니다.
"""

from .authenticator import Authentication, Authenticator, ANONYMOUS
from .authorize import Authorize, AuthorizeElement
from .middleware import AuthMiddleware, AuthGroup
from .oauth2 import (
    # Config
    OAuth2Config,
    # Token
    OAuth2Token,
    # Flow
    OAuth2Flow,
    OAuth2FlowComponent,
    # PKCE
    generate_pkce_pair,
)

# 에러들은 bloom.core.exceptions에서 re-export
from bloom.core.exceptions import (
    # HTTP base
    HttpException,
    # OAuth2
    OAuth2Error,
    InvalidGrantError,
    InvalidClientError,
    InvalidTokenError,
    OAuth2RequestError,
)

__all__ = [
    # 인증
    "Authentication",
    "Authenticator",
    "ANONYMOUS",
    # 인가
    "Authorize",
    "AuthorizeElement",
    # 미들웨어
    "AuthMiddleware",
    "AuthGroup",
    # HTTP Exception
    "HttpException",
    # OAuth2
    "OAuth2Config",
    "OAuth2Token",
    "OAuth2Error",
    "InvalidGrantError",
    "InvalidClientError",
    "InvalidTokenError",
    "OAuth2RequestError",
    "OAuth2Flow",
    "OAuth2FlowComponent",
    "generate_pkce_pair",
]
