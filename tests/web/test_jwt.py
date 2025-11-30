"""JWT 유틸리티 테스트"""

import json
from dataclasses import dataclass, field

import pytest


# PyJWT가 없으면 테스트 스킵
pytest.importorskip("jwt", reason="PyJWT required for JWT tests")


from bloom.core.protocols import Serializable
from bloom.web.auth import (
    JwtAlgorithm,
    JwtConfig,
    JwtEncoder,
    JwtDecoder,
    JwtCodec,
    JwtExpiredError,
    JwtInvalidSignatureError,
    JwtInvalidTokenError,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class MyTestJwtConfig(JwtConfig):
    """테스트용 JWT 설정"""

    secret_key: str = "test-secret-key-12345"
    algorithm: JwtAlgorithm = JwtAlgorithm.HS256
    expires_in: int = 3600
    issuer: str = "test-issuer"
    audience: str = "test-audience"


@pytest.fixture
def config() -> MyTestJwtConfig:
    return MyTestJwtConfig()


@pytest.fixture
def encoder(config: MyTestJwtConfig) -> JwtEncoder:
    return JwtEncoder(config)


@pytest.fixture
def decoder(config: MyTestJwtConfig) -> JwtDecoder:
    return JwtDecoder(config)


@pytest.fixture
def codec(config: MyTestJwtConfig) -> JwtCodec:
    return JwtCodec(config)


# =============================================================================
# JwtEncoder Tests
# =============================================================================


class TestJwtEncoder:
    """JwtEncoder 테스트"""

    def test_encode_basic(self, encoder: JwtEncoder):
        """기본 인코딩"""
        token = encoder.encode({"sub": "user123"})
        assert isinstance(token, str)
        assert len(token) > 0
        # JWT format: header.payload.signature
        assert token.count(".") == 2

    def test_encode_with_payload(self, encoder: JwtEncoder):
        """payload 데이터 인코딩"""
        payload = {"sub": "user123", "role": "admin", "name": "John"}
        token = encoder.encode(payload)
        assert isinstance(token, str)

    def test_encode_adds_iat(self, encoder: JwtEncoder, decoder: JwtDecoder):
        """iat (issued at) 자동 추가"""
        token = encoder.encode({"sub": "user123"})
        decoded = decoder.decode(token)
        assert "iat" in decoded
        assert isinstance(decoded["iat"], int)

    def test_encode_adds_exp(self, encoder: JwtEncoder, decoder: JwtDecoder):
        """exp (expiration) 자동 추가"""
        token = encoder.encode({"sub": "user123"})
        decoded = decoder.decode(token)
        assert "exp" in decoded
        assert decoded["exp"] > decoded["iat"]

    def test_encode_with_custom_expires_in(
        self, encoder: JwtEncoder, decoder: JwtDecoder
    ):
        """커스텀 만료 시간"""
        token = encoder.encode({"sub": "user123"}, expires_in=7200)
        decoded = decoder.decode(token)
        # 7200초 = 2시간
        assert decoded["exp"] - decoded["iat"] == 7200

    def test_encode_adds_issuer(self, encoder: JwtEncoder, decoder: JwtDecoder):
        """iss (issuer) 자동 추가"""
        token = encoder.encode({"sub": "user123"})
        decoded = decoder.decode(token)
        assert decoded["iss"] == "test-issuer"

    def test_encode_adds_audience(self, encoder: JwtEncoder, decoder: JwtDecoder):
        """aud (audience) 자동 추가"""
        token = encoder.encode({"sub": "user123"})
        decoded = decoder.decode(token)
        assert decoded["aud"] == "test-audience"

    def test_encode_extra_claims(self, encoder: JwtEncoder, decoder: JwtDecoder):
        """추가 클레임"""
        token = encoder.encode({"sub": "user123"}, custom_claim="value")
        decoded = decoder.decode(token)
        assert decoded["custom_claim"] == "value"

    def test_encode_no_expiration(self, config: MyTestJwtConfig):
        """만료 없는 토큰"""
        config.expires_in = 0
        encoder = JwtEncoder(config)
        decoder = JwtDecoder(config)

        token = encoder.encode({"sub": "user123"})
        decoded = decoder.decode(token)
        assert "exp" not in decoded


# =============================================================================
# JwtDecoder Tests
# =============================================================================


class TestJwtDecoder:
    """JwtDecoder 테스트"""

    def test_decode_basic(self, encoder: JwtEncoder, decoder: JwtDecoder):
        """기본 디코딩"""
        token = encoder.encode({"sub": "user123", "role": "admin"})
        decoded = decoder.decode(token)
        assert decoded["sub"] == "user123"
        assert decoded["role"] == "admin"

    def test_decode_invalid_token(self, decoder: JwtDecoder):
        """잘못된 토큰"""
        with pytest.raises(JwtInvalidTokenError):
            decoder.decode("invalid.token.here")

    def test_decode_empty_token(self, decoder: JwtDecoder):
        """빈 토큰"""
        with pytest.raises(JwtInvalidTokenError):
            decoder.decode("")

    def test_decode_wrong_signature(self, encoder: JwtEncoder, config: MyTestJwtConfig):
        """서명 불일치"""
        token = encoder.encode({"sub": "user123"})

        # 다른 secret으로 디코더 생성
        wrong_config = MyTestJwtConfig()
        wrong_config.secret_key = "wrong-secret"
        wrong_decoder = JwtDecoder(wrong_config)

        with pytest.raises(JwtInvalidSignatureError):
            wrong_decoder.decode(token)

    def test_decode_expired_token(self, config: MyTestJwtConfig):
        """만료된 토큰"""
        import jwt as pyjwt
        from datetime import datetime, timezone

        # 과거 시간으로 직접 토큰 생성 (sleep 불필요)
        now = datetime.now(timezone.utc)
        past = int(now.timestamp()) - 10  # 10초 전

        expired_token = pyjwt.encode(
            {"sub": "user123", "iat": past, "exp": past + 1},  # 이미 만료됨
            config.secret_key,
            algorithm=config.algorithm,
        )

        decoder = JwtDecoder(config)
        with pytest.raises(JwtExpiredError):
            decoder.decode(expired_token)

    def test_decode_unverified(self, encoder: JwtEncoder, config: MyTestJwtConfig):
        """검증 없이 디코딩"""
        token = encoder.encode({"sub": "user123"})

        # 다른 secret으로도 디코딩 가능 (검증 안함)
        wrong_config = MyTestJwtConfig()
        wrong_config.secret_key = "wrong-secret"
        wrong_decoder = JwtDecoder(wrong_config)

        decoded = wrong_decoder.decode_unverified(token)
        assert decoded["sub"] == "user123"

    def test_get_unverified_header(self, encoder: JwtEncoder, decoder: JwtDecoder):
        """헤더 추출"""
        token = encoder.encode({"sub": "user123"})
        header = decoder.get_unverified_header(token)
        assert header["alg"] == "HS256"
        assert header["typ"] == "JWT"


# =============================================================================
# JwtCodec Tests
# =============================================================================


class TestJwtCodec:
    """JwtCodec 테스트"""

    def test_encode_decode(self, codec: JwtCodec):
        """인코딩 + 디코딩"""
        payload = {"sub": "user123", "role": "admin"}
        token = codec.encode(payload)
        decoded = codec.decode(token)
        assert decoded["sub"] == "user123"
        assert decoded["role"] == "admin"

    def test_codec_has_encoder_decoder(self, codec: JwtCodec):
        """encoder/decoder 속성"""
        assert isinstance(codec.encoder, JwtEncoder)
        assert isinstance(codec.decoder, JwtDecoder)

    def test_decode_unverified(self, codec: JwtCodec):
        """검증 없이 디코딩"""
        token = codec.encode({"sub": "user123"})
        decoded = codec.decode_unverified(token)
        assert decoded["sub"] == "user123"

    def test_get_unverified_header(self, codec: JwtCodec):
        """헤더 추출"""
        token = codec.encode({"sub": "user123"})
        header = codec.get_unverified_header(token)
        assert header["alg"] == "HS256"


# =============================================================================
# JwtConfig Tests
# =============================================================================


class TestJwtConfig:
    """JwtConfig 테스트"""

    def test_default_values(self):
        """기본값"""

        @dataclass
        class MinimalConfig(JwtConfig):
            secret_key: str = "secret"

        config = MinimalConfig()
        assert config.algorithm == "HS256"
        assert config.expires_in == 0
        assert config.issuer == ""
        assert config.audience == ""
        assert config.leeway == 0

    def test_custom_algorithm(self):
        """커스텀 알고리즘"""

        @dataclass
        class CustomConfig(JwtConfig):
            secret_key: str = "secret"
            algorithm: JwtAlgorithm = JwtAlgorithm.HS512

        config = CustomConfig()
        encoder = JwtEncoder(config)
        decoder = JwtDecoder(config)

        token = encoder.encode({"sub": "user"})
        header = decoder.get_unverified_header(token)
        assert header["alg"] == "HS512"

    def test_leeway(self, config: MyTestJwtConfig):
        """leeway (시간 허용 오차)"""
        import jwt as pyjwt
        from datetime import datetime, timezone

        config.leeway = 5  # 5초 허용

        # 2초 전에 만료된 토큰 (leeway 5초 이내)
        now = datetime.now(timezone.utc)
        past = int(now.timestamp()) - 3

        nearly_expired_token = pyjwt.encode(
            {
                "sub": "user123",
                "iat": past,
                "exp": past + 1,  # 2초 전 만료
                "iss": config.issuer,
                "aud": config.audience,
            },
            config.secret_key,
            algorithm=config.algorithm.value,
        )

        decoder = JwtDecoder(config)
        # leeway 덕분에 디코딩 성공
        decoded = decoder.decode(nearly_expired_token)
        assert decoded["sub"] == "user123"


# =============================================================================
# Error Cases Tests
# =============================================================================


class TestJwtErrors:
    """JWT 에러 케이스"""

    def test_missing_secret_key(self):
        """secret_key 누락"""

        @dataclass
        class NoSecretConfig(JwtConfig):
            pass

        config = NoSecretConfig()
        encoder = JwtEncoder(config)

        with pytest.raises(ValueError, match="secret_key is required"):
            encoder.encode({"sub": "user"})

    def test_asymmetric_needs_private_key(self):
        """비대칭 알고리즘에서 private_key 필요"""

        @dataclass
        class RSAConfig(JwtConfig):
            algorithm: JwtAlgorithm = JwtAlgorithm.RS256
            secret_key: str = ""  # 비대칭에선 사용 안함

        config = RSAConfig()
        encoder = JwtEncoder(config)

        with pytest.raises(ValueError, match="private_key is required"):
            encoder.encode({"sub": "user"})

    def test_asymmetric_decode_needs_public_key(self):
        """비대칭 알고리즘에서 public_key 필요"""

        @dataclass
        class RSAConfig(JwtConfig):
            algorithm: JwtAlgorithm = JwtAlgorithm.RS256

        config = RSAConfig()
        decoder = JwtDecoder(config)

        # ValueError가 JwtInvalidTokenError로 래핑됨
        with pytest.raises(JwtInvalidTokenError, match="public_key is required"):
            decoder.decode("some.token.here")


# =============================================================================
# Serializable Tests
# =============================================================================


@dataclass
class UserPayload:
    """테스트용 Serializable 페이로드"""

    user_id: str
    role: str
    permissions: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "user_id": self.user_id,
                "role": self.role,
                "permissions": self.permissions,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> "UserPayload":
        obj = json.loads(data)
        return cls(
            user_id=obj["user_id"],
            role=obj["role"],
            permissions=obj.get("permissions", []),
        )


class TestSerializableJwt:
    """Serializable 객체 JWT 인코딩/디코딩 테스트"""

    def test_encode_object(self, encoder: JwtEncoder, decoder: JwtDecoder):
        """Serializable 객체 인코딩"""
        payload = UserPayload(
            user_id="user123", role="admin", permissions=["read", "write"]
        )
        token = encoder.encode_object(payload)

        # 디코딩하여 확인
        decoded = decoder.decode(token)
        assert decoded["user_id"] == "user123"
        assert decoded["role"] == "admin"
        assert decoded["permissions"] == ["read", "write"]

    def test_decode_as(self, encoder: JwtEncoder, decoder: JwtDecoder):
        """타입 안전한 디코딩"""
        original = UserPayload(user_id="user456", role="viewer", permissions=["read"])
        token = encoder.encode_object(original)

        # decode_as로 타입 안전하게 디코딩
        restored = decoder.decode_as(UserPayload, token)

        assert isinstance(restored, UserPayload)
        assert restored.user_id == "user456"
        assert restored.role == "viewer"
        assert restored.permissions == ["read"]

    def test_codec_encode_object(self, codec: JwtCodec):
        """JwtCodec으로 Serializable 인코딩"""
        payload = UserPayload(user_id="user789", role="admin")
        token = codec.encode_object(payload)

        decoded = codec.decode(token)
        assert decoded["user_id"] == "user789"

    def test_codec_decode_as(self, codec: JwtCodec):
        """JwtCodec으로 타입 안전한 디코딩"""
        original = UserPayload(user_id="user000", role="guest")
        token = codec.encode_object(original)

        restored = codec.decode_as(UserPayload, token)
        assert isinstance(restored, UserPayload)
        assert restored.user_id == "user000"
        assert restored.role == "guest"

    def test_serializable_protocol(self):
        """Serializable 프로토콜 확인"""
        payload = UserPayload(user_id="test", role="test")
        assert isinstance(payload, Serializable)

    def test_jwt_claims_excluded(self, encoder: JwtEncoder, decoder: JwtDecoder):
        """JWT 메타데이터(iat, exp 등)가 decode_as에서 제외됨"""
        payload = UserPayload(user_id="user123", role="admin")
        token = encoder.encode_object(payload)

        restored = decoder.decode_as(UserPayload, token)

        # iat, exp, iss, aud 등이 UserPayload에 포함되지 않아야 함
        assert not hasattr(restored, "iat")
        assert not hasattr(restored, "exp")

    def test_round_trip(self, codec: JwtCodec):
        """왕복 테스트 (encode_object → decode_as)"""
        original = UserPayload(
            user_id="roundtrip-user",
            role="super-admin",
            permissions=["create", "read", "update", "delete"],
        )

        token = codec.encode_object(original)
        restored = codec.decode_as(UserPayload, token)

        assert restored.user_id == original.user_id
        assert restored.role == original.role
        assert restored.permissions == original.permissions
