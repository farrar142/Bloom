"""JWT 인코딩/디코딩 유틸리티

PyJWT 래퍼로 Bloom 스타일의 간단한 JWT 처리를 제공합니다.

사용 예시:
    ```python
    from dataclasses import dataclass
    from bloom import Component
    from bloom.core.decorators import Factory
    from bloom.web.auth import JwtConfig, JwtEncoder, JwtDecoder

    # 1. 설정 정의
    @dataclass
    class MyJwtConfig(JwtConfig):
        secret_key: str = EnvStr("JWT_SECRET", "my-secret-key")
        algorithm: str = "HS256"
        expires_in: int = 3600  # 1시간

    # 2. Factory로 Encoder/Decoder 생성
    @Component
    class SecurityConfig:
        @Factory
        def jwt_encoder(self, config: MyJwtConfig) -> JwtEncoder:
            return JwtEncoder(config)

        @Factory
        def jwt_decoder(self, config: MyJwtConfig) -> JwtDecoder:
            return JwtDecoder(config)

    # 3. 서비스에서 사용
    @Component
    class AuthService:
        encoder: JwtEncoder
        decoder: JwtDecoder

        def create_token(self, user_id: str) -> str:
            return self.encoder.encode({"sub": user_id, "role": "user"})

        def verify_token(self, token: str) -> dict:
            return self.decoder.decode(token)

    # 4. Serializable 객체 사용
    @dataclass
    class UserPayload:
        user_id: str
        role: str

        def to_json(self) -> str:
            return json.dumps({"user_id": self.user_id, "role": self.role})

        @classmethod
        def from_json(cls, data: str) -> "UserPayload":
            obj = json.loads(data)
            return cls(user_id=obj["user_id"], role=obj["role"])

    # Serializable로 인코딩/디코딩
    token = encoder.encode_object(UserPayload(user_id="123", role="admin"))
    payload = decoder.decode_as(UserPayload, token)
    ```
"""

from abc import ABC
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, TypeVar, overload
import json

from bloom.core.exceptions import (
    JwtError,
    JwtExpiredError,
    JwtInvalidSignatureError,
    JwtInvalidTokenError,
    JwtInvalidAudienceError,
    JwtInvalidIssuerError,
)
from bloom.core.protocols import Serializable

T = TypeVar("T", bound=Serializable)


# =============================================================================
# JWT Algorithm Enum
# =============================================================================


class JwtAlgorithm(str, Enum):
    """JWT 서명 알고리즘

    PyJWT에서 지원하는 모든 알고리즘을 정의합니다.

    대칭 키 알고리즘 (HMAC):
        - HS256, HS384, HS512: secret_key 필요

    비대칭 키 알고리즘 (RSA):
        - RS256, RS384, RS512: private_key(서명), public_key(검증) 필요
        - PS256, PS384, PS512: RSA-PSS

    비대칭 키 알고리즘 (ECDSA):
        - ES256, ES256K, ES384, ES512: private_key(서명), public_key(검증) 필요

    EdDSA:
        - EdDSA: Ed25519/Ed448
    """

    # HMAC (대칭 키)
    HS256 = "HS256"
    HS384 = "HS384"
    HS512 = "HS512"

    # RSA (비대칭 키)
    RS256 = "RS256"
    RS384 = "RS384"
    RS512 = "RS512"

    # RSA-PSS (비대칭 키)
    PS256 = "PS256"
    PS384 = "PS384"
    PS512 = "PS512"

    # ECDSA (비대칭 키)
    ES256 = "ES256"
    ES256K = "ES256K"
    ES384 = "ES384"
    ES512 = "ES512"

    # EdDSA
    EdDSA = "EdDSA"

    def is_symmetric(self) -> bool:
        """대칭 키 알고리즘인지 확인"""
        return self.value.startswith("HS")

    def is_asymmetric(self) -> bool:
        """비대칭 키 알고리즘인지 확인"""
        return not self.is_symmetric()


# =============================================================================
# JWT Config
# =============================================================================


@dataclass
class JwtConfig(ABC):
    """
    JWT 설정 베이스 클래스

    상속하여 프로젝트별 설정을 정의합니다.

    Attributes:
        secret_key: 서명에 사용할 비밀 키 (HS256 등)
        public_key: 검증에 사용할 공개 키 (RS256 등, 선택)
        private_key: 서명에 사용할 개인 키 (RS256 등, 선택)
        algorithm: 알고리즘 (JwtAlgorithm enum)
        expires_in: 기본 만료 시간 (초), 0이면 만료 없음
        issuer: 토큰 발급자 (iss claim)
        audience: 토큰 대상자 (aud claim)
        leeway: 시간 검증 허용 오차 (초)

    Example:
        ```python
        @dataclass
        class MyJwtConfig(JwtConfig):
            secret_key: str = EnvStr("JWT_SECRET")
            algorithm: JwtAlgorithm = JwtAlgorithm.HS256
            expires_in: int = 3600
            issuer: str = "my-app"
        ```
    """

    # 대칭 키 (HS256, HS384, HS512)
    secret_key: str = ""

    # 비대칭 키 (RS256, RS384, RS512, ES256, ES384, ES512)
    public_key: str = ""
    private_key: str = ""

    # 알고리즘
    algorithm: JwtAlgorithm = JwtAlgorithm.HS256

    # 만료 시간 (초), 0이면 만료 없음
    expires_in: int = 0

    # 클레임
    issuer: str = ""
    audience: str = ""

    # 검증 옵션
    leeway: int = 0  # 시간 검증 허용 오차 (초)

    # 추가 검증 옵션
    verify_exp: bool = True
    verify_iss: bool = True
    verify_aud: bool = True


# =============================================================================
# JWT Encoder
# =============================================================================


class JwtEncoder:
    """
    JWT 토큰 인코더

    설정에 따라 payload를 JWT 토큰으로 인코딩합니다.

    Attributes:
        config: JWT 설정

    Example:
        ```python
        encoder = JwtEncoder(config)
        token = encoder.encode({"sub": "user123", "role": "admin"})
        ```
    """

    def __init__(self, config: JwtConfig):
        self.config = config
        self._jwt = self._import_jwt()

    def _import_jwt(self):
        """PyJWT import (lazy)"""
        try:
            import jwt

            return jwt
        except ImportError:
            raise RuntimeError(
                "PyJWT is required for JWT support. "
                "Install it with: pip install pyjwt"
            )

    def _get_signing_key(self) -> str:
        """서명 키 반환"""
        if self.config.algorithm.is_symmetric():
            # 대칭 키
            if not self.config.secret_key:
                raise ValueError("secret_key is required for HS* algorithms")
            return self.config.secret_key
        else:
            # 비대칭 키 (RS, ES)
            if not self.config.private_key:
                raise ValueError("private_key is required for RS*/ES* algorithms")
            return self.config.private_key

    def encode(
        self,
        payload: dict[str, Any],
        expires_in: int | None = None,
        **extra_claims: Any,
    ) -> str:
        """
        Payload를 JWT 토큰으로 인코딩

        Args:
            payload: 토큰에 담을 데이터
            expires_in: 만료 시간 (초), None이면 설정값 사용
            **extra_claims: 추가 클레임 (iss, aud 등 오버라이드)

        Returns:
            JWT 토큰 문자열

        Example:
            ```python
            # 기본 사용
            token = encoder.encode({"sub": "user123"})

            # 만료 시간 지정
            token = encoder.encode({"sub": "user123"}, expires_in=7200)

            # 추가 클레임
            token = encoder.encode({"sub": "user123"}, role="admin")
            ```
        """
        # 페이로드 복사
        claims = dict(payload)
        claims.update(extra_claims)

        # 발급 시간
        now = datetime.now(timezone.utc)
        claims["iat"] = int(now.timestamp())

        # 만료 시간
        exp_seconds = expires_in if expires_in is not None else self.config.expires_in
        if exp_seconds > 0:
            claims["exp"] = int((now + timedelta(seconds=exp_seconds)).timestamp())

        # issuer
        if self.config.issuer and "iss" not in claims:
            claims["iss"] = self.config.issuer

        # audience
        if self.config.audience and "aud" not in claims:
            claims["aud"] = self.config.audience

        # 인코딩
        return self._jwt.encode(
            claims,
            self._get_signing_key(),
            algorithm=self.config.algorithm.value,
        )

    def encode_object(
        self,
        obj: Serializable,
        expires_in: int | None = None,
        **extra_claims: Any,
    ) -> str:
        """
        Serializable 객체를 JWT 토큰으로 인코딩

        객체의 to_json()을 호출하여 payload로 사용합니다.

        Args:
            obj: Serializable 프로토콜을 구현한 객체
            expires_in: 만료 시간 (초), None이면 설정값 사용
            **extra_claims: 추가 클레임 (iss, aud 등 오버라이드)

        Returns:
            JWT 토큰 문자열

        Example:
            ```python
            @dataclass
            class UserPayload:
                user_id: str
                role: str

                def to_json(self) -> str:
                    return json.dumps({"user_id": self.user_id, "role": self.role})

                @classmethod
                def from_json(cls, data: str) -> "UserPayload":
                    obj = json.loads(data)
                    return cls(**obj)

            token = encoder.encode_object(UserPayload("123", "admin"))
            ```
        """
        # Serializable.to_json() → dict
        json_str = obj.to_json()
        payload = json.loads(json_str)

        return self.encode(payload, expires_in, **extra_claims)


# =============================================================================
# JWT Decoder
# =============================================================================


class JwtDecoder:
    """
    JWT 토큰 디코더

    설정에 따라 JWT 토큰을 검증하고 디코딩합니다.

    Attributes:
        config: JWT 설정

    Example:
        ```python
        decoder = JwtDecoder(config)
        try:
            payload = decoder.decode(token)
            print(payload["sub"])
        except JwtExpiredError:
            print("토큰 만료")
        ```
    """

    def __init__(self, config: JwtConfig):
        self.config = config
        self._jwt = self._import_jwt()

    def _import_jwt(self):
        """PyJWT import (lazy)"""
        try:
            import jwt

            return jwt
        except ImportError:
            raise RuntimeError(
                "PyJWT is required for JWT support. "
                "Install it with: pip install pyjwt"
            )

    def _get_verification_key(self) -> str:
        """검증 키 반환"""
        if self.config.algorithm.is_symmetric():
            # 대칭 키
            if not self.config.secret_key:
                raise ValueError("secret_key is required for HS* algorithms")
            return self.config.secret_key
        else:
            # 비대칭 키 (RS, ES)
            if not self.config.public_key:
                raise ValueError("public_key is required for RS*/ES* algorithms")
            return self.config.public_key

    def decode(
        self,
        token: str,
        verify: bool = True,
        **options: Any,
    ) -> dict[str, Any]:
        """
        JWT 토큰을 검증하고 디코딩

        Args:
            token: JWT 토큰 문자열
            verify: 서명 검증 여부 (기본 True)
            **options: PyJWT 옵션 오버라이드

        Returns:
            디코딩된 payload 딕셔너리

        Raises:
            JwtExpiredError: 토큰 만료
            JwtInvalidSignatureError: 서명 불일치
            JwtInvalidTokenError: 기타 디코딩 에러

        Example:
            ```python
            payload = decoder.decode(token)
            user_id = payload["sub"]
            ```
        """
        if not token:
            raise JwtInvalidTokenError("Token is missing")

        # 검증 옵션
        decode_options: dict[str, Any] = {
            "verify_signature": verify,
            "verify_exp": self.config.verify_exp,
            "require": ["iat"],
        }

        # 옵션 오버라이드
        decode_options.update(options)

        # audience / issuer 검증
        kwargs: dict[str, Any] = {
            "algorithms": [self.config.algorithm.value],
            "options": decode_options,
        }

        # leeway (초 단위 - kwargs로 전달)
        if self.config.leeway > 0:
            kwargs["leeway"] = timedelta(seconds=self.config.leeway)

        if self.config.issuer and self.config.verify_iss:
            kwargs["issuer"] = self.config.issuer

        if self.config.audience and self.config.verify_aud:
            kwargs["audience"] = self.config.audience

        try:
            return self._jwt.decode(
                token,
                self._get_verification_key(),
                **kwargs,
            )
        except self._jwt.ExpiredSignatureError:
            raise JwtExpiredError()
        except self._jwt.InvalidSignatureError:
            raise JwtInvalidSignatureError()
        except self._jwt.InvalidAudienceError:
            raise JwtInvalidAudienceError()
        except self._jwt.InvalidIssuerError:
            raise JwtInvalidIssuerError()
        except self._jwt.DecodeError as e:
            raise JwtInvalidTokenError(str(e))
        except Exception as e:
            raise JwtInvalidTokenError(f"Unexpected error: {e}")

    def decode_unverified(self, token: str) -> dict[str, Any]:
        """
        서명 검증 없이 디코딩 (디버깅용)

        ⚠️ 주의: 이 메서드는 서명을 검증하지 않습니다.
        프로덕션에서 인증에 사용하지 마세요.

        Args:
            token: JWT 토큰 문자열

        Returns:
            디코딩된 payload
        """
        return self.decode(token, verify=False)

    def get_unverified_header(self, token: str) -> dict[str, Any]:
        """
        토큰 헤더 추출 (검증 없음)

        Args:
            token: JWT 토큰 문자열

        Returns:
            토큰 헤더 (alg, typ 등)
        """
        try:
            return self._jwt.get_unverified_header(token)
        except Exception as e:
            raise JwtInvalidTokenError(f"Failed to get header: {e}")

    def decode_as(
        self,
        target_type: type[T],
        token: str,
        verify: bool = True,
        **options: Any,
    ) -> T:
        """
        JWT 토큰을 Serializable 타입으로 디코딩

        Args:
            target_type: Serializable 프로토콜을 구현한 타입
            token: JWT 토큰 문자열
            verify: 서명 검증 여부 (기본 True)
            **options: PyJWT 옵션 오버라이드

        Returns:
            target_type 인스턴스

        Raises:
            JwtExpiredError: 토큰 만료
            JwtInvalidSignatureError: 서명 불일치
            JwtInvalidTokenError: 기타 디코딩 에러

        Example:
            ```python
            @dataclass
            class UserPayload:
                user_id: str
                role: str

                def to_json(self) -> str:
                    return json.dumps({"user_id": self.user_id, "role": self.role})

                @classmethod
                def from_json(cls, data: str) -> "UserPayload":
                    obj = json.loads(data)
                    return cls(**obj)

            payload = decoder.decode_as(UserPayload, token)
            print(payload.user_id)  # 타입 안전!
            ```
        """
        # 디코딩
        claims = self.decode(token, verify, **options)

        # JWT 메타데이터 제거 (iat, exp, iss, aud 등)
        jwt_claims = {"iat", "exp", "iss", "aud", "nbf", "jti", "sub"}
        payload_data = {k: v for k, v in claims.items() if k not in jwt_claims}

        # JSON 문자열로 변환 후 from_json() 호출
        json_str = json.dumps(payload_data)
        return target_type.from_json(json_str)


# =============================================================================
# JWT Codec (Encoder + Decoder)
# =============================================================================


class JwtCodec:
    """
    JWT 인코더 + 디코더 통합

    하나의 객체로 encode/decode 모두 처리합니다.

    Example:
        ```python
        @Component
        class SecurityConfig:
            @Factory
            def jwt_codec(self, config: MyJwtConfig) -> JwtCodec:
                return JwtCodec(config)

        @Component
        class AuthService:
            jwt: JwtCodec

            def create_token(self, user_id: str) -> str:
                return self.jwt.encode({"sub": user_id})

            def verify_token(self, token: str) -> dict:
                return self.jwt.decode(token)
        ```
    """

    def __init__(self, config: JwtConfig):
        self.config = config
        self.encoder = JwtEncoder(config)
        self.decoder = JwtDecoder(config)

    def encode(
        self,
        payload: dict[str, Any],
        expires_in: int | None = None,
        **extra_claims: Any,
    ) -> str:
        """토큰 인코딩 (JwtEncoder.encode 위임)"""
        return self.encoder.encode(payload, expires_in, **extra_claims)

    def decode(
        self,
        token: str,
        verify: bool = True,
        **options: Any,
    ) -> dict[str, Any]:
        """토큰 디코딩 (JwtDecoder.decode 위임)"""
        return self.decoder.decode(token, verify, **options)

    def decode_unverified(self, token: str) -> dict[str, Any]:
        """서명 검증 없이 디코딩"""
        return self.decoder.decode_unverified(token)

    def get_unverified_header(self, token: str) -> dict[str, Any]:
        """토큰 헤더 추출"""
        return self.decoder.get_unverified_header(token)

    def encode_object(
        self,
        obj: Serializable,
        expires_in: int | None = None,
        **extra_claims: Any,
    ) -> str:
        """Serializable 객체 인코딩 (JwtEncoder.encode_object 위임)"""
        return self.encoder.encode_object(obj, expires_in, **extra_claims)

    def decode_as(
        self,
        target_type: type[T],
        token: str,
        verify: bool = True,
        **options: Any,
    ) -> T:
        """타입 안전한 디코딩 (JwtDecoder.decode_as 위임)"""
        return self.decoder.decode_as(target_type, token, verify, **options)
