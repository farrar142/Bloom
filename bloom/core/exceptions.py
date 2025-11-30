"""Bloom 프레임워크 예외 클래스들

모든 Bloom 관련 예외는 이 모듈에서 정의됩니다.

예외 계층:
    BloomException (기본)
    ├── ContainerException (DI 컨테이너 관련)
    │   ├── CircularDependencyError (순환 의존성)
    │   ├── AmbiguousProviderError (모호한 Provider)
    │   └── AmbiguousInstanceError (모호한 인스턴스)
    ├── HttpException (HTTP 관련)
    │   ├── BadRequestError (400)
    │   │   ├── ValidationError (유효성 검사 실패)
    │   │   └── ParameterBindingError (파라미터 바인딩 실패)
    │   │       ├── MissingParameterError (필수 파라미터 누락)
    │   │       └── TypeConversionError (타입 변환 실패)
    │   ├── UnauthorizedError (401)
    │   ├── ForbiddenError (403)
    │   ├── NotFoundError (404)
    │   ├── MethodNotAllowedError (405)
    │   ├── InternalServerError (500)
    │   ├── ServiceUnavailableError (503)
    │   └── OAuth2Error (OAuth2 관련)
    │       ├── InvalidGrantError
    │       ├── InvalidClientError
    │       ├── InvalidTokenError
    │       └── OAuth2RequestError
    └── SystemException (시스템/내부 관련)
        └── ConfigurationError (설정 관련)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .container import Container, FactoryContainer


# =============================================================================
# Base Exception
# =============================================================================


class BloomException(Exception):
    """Bloom 프레임워크 기본 예외

    모든 Bloom 예외의 최상위 부모 클래스입니다.
    """

    pass


# =============================================================================
# Container Exceptions (DI 컨테이너 관련)
# =============================================================================


class ContainerException(BloomException):
    """DI 컨테이너 관련 예외 베이스 클래스

    의존성 주입, 컨테이너 등록, 인스턴스 생성 등에서 발생하는 에러입니다.
    """

    pass


class CircularDependencyError(ContainerException):
    """순환 의존성 감지 예외

    순환 의존성이 발견되면 이 예외가 발생하며,
    관련된 컨테이너들의 정보와 의존성 그래프를 포함합니다.
    """

    def __init__(
        self,
        message: str,
        unresolved_containers: list[Any] | None = None,
        all_containers: list[Any] | None = None,
    ):
        super().__init__(message)
        self.unresolved_containers: list[Any] = unresolved_containers or []
        self.all_containers: list[Any] = all_containers or []
        self._graph_saved_path: str | None = None

    @property
    def graph_saved_path(self) -> str | None:
        """그래프가 저장된 파일 경로"""
        return self._graph_saved_path

    @graph_saved_path.setter
    def graph_saved_path(self, path: str) -> None:
        self._graph_saved_path = path

    def get_cycle_info(self) -> str:
        """순환 의존성 정보를 문자열로 반환"""
        if not self.unresolved_containers:
            return "No cycle information available"

        lines = ["Circular dependency detected among:"]
        for container in self.unresolved_containers:
            deps = container.get_dependencies()
            dep_names = [d.__name__ for d in deps]
            lines.append(f"  - {container.target.__name__} → {dep_names}")

        return "\n".join(lines)


class AmbiguousProviderError(ContainerException):
    """Factory Chain에서 Ambiguous Provider 감지 예외

    동일 타입에 대해 여러 Creator가 있고 Modifier가 있는 경우 발생합니다.

    두 가지 케이스:
    1. Creator가 여러 개이고 Modifier가 있는 경우 (creators, modifiers 전달)
    2. 어떤 Factory를 사용할지 모호한 경우 (conflicting_factories, dependent_factory 전달)
    """

    def __init__(
        self,
        target_type: type,
        creators: list | None = None,
        modifiers: list | None = None,
        conflicting_factories: list["FactoryContainer"] | None = None,
        dependent_factory: "FactoryContainer | None" = None,
    ):
        self.target_type = target_type
        self.creators = creators or []
        self.modifiers = modifiers or []
        self.conflicting_factories = conflicting_factories or []
        self.dependent_factory = dependent_factory

        # 메시지 생성
        if creators and modifiers:
            # Case 1: Creator/Modifier 충돌
            creator_names = [
                f"{c.owner_type.__name__}.{c.factory_method.__name__}" for c in creators
            ]
            message = (
                f"Ambiguous Provider for {target_type.__name__}: "
                f"Found {len(creators)} creators ({creator_names}) with {len(modifiers)} modifiers. "
                f"Only one creator is allowed when modifiers exist."
            )
        elif conflicting_factories and dependent_factory:
            # Case 2: Factory 선택 모호
            factory_names = [f.factory_method.__name__ for f in conflicting_factories]
            message = (
                f"Ambiguous provider for type '{target_type.__name__}'.\n"
                f"Multiple factories produce this type: {factory_names}\n"
                f"Factory '{dependent_factory.factory_method.__name__}' requires "
                f"'{target_type.__name__}' as a dependency but cannot determine which provider to use.\n"
                f"This is an Ambiguous Provider Anti-pattern.\n"
                f"Solution: Use Factory Chain pattern where only ONE factory creates the initial instance, "
                f"and others modify it with @Order decorator."
            )
        else:
            message = f"Ambiguous provider for type '{target_type.__name__}'"

        super().__init__(message)


class AmbiguousInstanceError(ContainerException):
    """동일 타입의 인스턴스가 여러 개일 때 발생

    get_instance()로 단일 인스턴스를 요청했지만
    해당 타입의 인스턴스가 여러 개 등록된 경우 발생합니다.

    Solution: get_instances()를 사용하거나, 특정 인스턴스를 지정하세요.
    """

    def __init__(self, target_type: type, count: int = 0, message: str = ""):
        self.target_type = target_type
        self.count = count

        if not message:
            message = (
                f"Multiple instances found for type '{target_type.__name__}' (count: {count}). "
                f"Use get_instances() to retrieve all, or specify a concrete type."
            )
        super().__init__(message)


# =============================================================================
# HTTP Exceptions (웹/HTTP 관련)
# =============================================================================


class HttpException(BloomException):
    """HTTP 관련 예외 베이스 클래스

    웹 요청/응답, 인증, API 호출 등에서 발생하는 에러입니다.

    Attributes:
        status_code: HTTP 상태 코드 (기본값: 500)
        detail: 에러 상세 메시지
    """

    status_code: int = 500

    def __init__(self, detail: str = "", status_code: int | None = None):
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        super().__init__(detail)


# -----------------------------------------------------------------------------
# HTTP 4xx Client Errors
# -----------------------------------------------------------------------------


class BadRequestError(HttpException):
    """잘못된 요청 (400)

    요청 형식이 잘못되었거나 파라미터가 유효하지 않은 경우
    """

    status_code: int = 400

    def __init__(self, detail: str = "Bad request"):
        super().__init__(detail)


class UnauthorizedError(HttpException):
    """인증 필요 (401)

    인증이 필요하거나 인증 정보가 유효하지 않은 경우
    """

    status_code: int = 401

    def __init__(self, detail: str = "Authentication required"):
        super().__init__(detail)


class ForbiddenError(HttpException):
    """접근 금지 (403)

    인증은 되었지만 해당 리소스에 접근 권한이 없는 경우
    """

    status_code: int = 403

    def __init__(self, detail: str = "Access forbidden"):
        super().__init__(detail)


class NotFoundError(HttpException):
    """리소스 없음 (404)

    요청한 리소스를 찾을 수 없는 경우
    """

    status_code: int = 404

    def __init__(self, detail: str = "Resource not found"):
        super().__init__(detail)


class MethodNotAllowedError(HttpException):
    """허용되지 않는 메서드 (405)

    요청한 HTTP 메서드가 해당 리소스에서 지원되지 않는 경우
    """

    status_code: int = 405

    def __init__(self, detail: str = "Method not allowed"):
        super().__init__(detail)


class ValidationError(BadRequestError):
    """유효성 검사 실패 (400)

    요청 파라미터나 바디의 유효성 검사에 실패한 경우.
    pydantic ValidationError를 래핑하여 필드별 상세 에러 정보를 제공합니다.

    Attributes:
        errors: 필드별 에러 목록 (pydantic 형식)
            [
                {
                    "loc": ["body", "user", "email"],  # 중첩 경로
                    "msg": "value is not a valid email address",
                    "type": "value_error.email",
                    "input": "invalid-email"
                },
                ...
            ]

    Example:
        ```python
        try:
            User.model_validate(data)
        except pydantic.ValidationError as e:
            raise ValidationError.from_pydantic(e)
        ```
    """

    def __init__(
        self,
        detail: str = "Validation failed",
        errors: list[dict[str, Any]] | None = None,
    ):
        self.errors: list[dict[str, Any]] = errors or []
        super().__init__(detail)

    @classmethod
    def from_pydantic(
        cls,
        pydantic_error: Any,
        loc_prefix: tuple[str, ...] = ("body",),
    ) -> "ValidationError":
        """pydantic ValidationError로부터 Bloom ValidationError 생성

        Args:
            pydantic_error: pydantic.ValidationError 인스턴스
            loc_prefix: 에러 위치 앞에 추가할 경로 (예: ("body",), ("query",))

        Returns:
            ValidationError with detailed field errors
        """
        errors: list[dict[str, Any]] = []

        for error in pydantic_error.errors():
            # 중첩 경로 구성: loc_prefix + 원래 loc
            loc = list(loc_prefix) + list(error.get("loc", []))

            error_detail: dict[str, Any] = {
                "loc": loc,
                "msg": error.get("msg", ""),
                "type": error.get("type", ""),
            }

            # input 값이 있으면 포함 (민감 정보 주의)
            if "input" in error:
                input_val = error["input"]
                # 너무 긴 값은 잘라냄
                if isinstance(input_val, str) and len(input_val) > 100:
                    input_val = input_val[:100] + "..."
                error_detail["input"] = input_val

            # ctx (추가 컨텍스트)가 있으면 포함
            if "ctx" in error:
                error_detail["ctx"] = error["ctx"]

            errors.append(error_detail)

        # 에러 개수를 포함한 메시지
        error_count = len(errors)
        detail = (
            f"Validation failed: {error_count} error{'s' if error_count > 1 else ''}"
        )

        return cls(detail=detail, errors=errors)

    def to_dict(self) -> dict[str, Any]:
        """에러를 딕셔너리로 변환 (JSON 응답용)

        Returns:
            {
                "error": "ValidationError",
                "message": "Validation failed: 2 errors",
                "details": [
                    {
                        "loc": ["body", "user", "email"],
                        "msg": "value is not a valid email address",
                        "type": "value_error.email"
                    },
                    ...
                ]
            }
        """
        return {
            "error": "ValidationError",
            "message": self.detail,
            "details": self.errors,
        }


class ParameterBindingError(BadRequestError):
    """파라미터 바인딩 실패 (400)

    핸들러 파라미터에 값을 바인딩하는 과정에서 실패한 경우

    Attributes:
        param_name: 실패한 파라미터 이름
        param_type: 파라미터 타입
        reason: 실패 원인
    """

    def __init__(
        self,
        param_name: str,
        param_type: type | None = None,
        reason: str = "",
    ):
        self.param_name = param_name
        self.param_type = param_type
        self.reason = reason

        type_name = param_type.__name__ if param_type else "unknown"
        detail = f"Failed to bind parameter '{param_name}' (type: {type_name})"
        if reason:
            detail += f": {reason}"
        super().__init__(detail)


class MissingParameterError(ParameterBindingError):
    """필수 파라미터 누락 (400)

    필수 파라미터가 요청에 포함되지 않은 경우
    """

    def __init__(self, param_name: str, param_type: type | None = None):
        super().__init__(param_name, param_type, "Required parameter is missing")


class TypeConversionError(ParameterBindingError):
    """타입 변환 실패 (400)

    파라미터 값을 요청된 타입으로 변환할 수 없는 경우

    Attributes:
        value: 변환 시도된 원본 값
    """

    def __init__(
        self,
        param_name: str,
        param_type: type | None = None,
        value: Any = None,
    ):
        self.value = value
        reason = f"Cannot convert value '{value}' to {param_type.__name__ if param_type else 'unknown'}"
        super().__init__(param_name, param_type, reason)


# -----------------------------------------------------------------------------
# HTTP 5xx Server Errors
# -----------------------------------------------------------------------------


class InternalServerError(HttpException):
    """내부 서버 오류 (500)

    예상치 못한 서버 오류가 발생한 경우
    """

    status_code: int = 500

    def __init__(self, detail: str = "Internal server error"):
        super().__init__(detail)


class ServiceUnavailableError(HttpException):
    """서비스 이용 불가 (503)

    서버가 일시적으로 요청을 처리할 수 없는 경우
    """

    status_code: int = 503

    def __init__(self, detail: str = "Service temporarily unavailable"):
        super().__init__(detail)


# -----------------------------------------------------------------------------
# OAuth2 Errors
# -----------------------------------------------------------------------------


class OAuth2Error(HttpException):
    """OAuth2 관련 에러 베이스 클래스

    OAuth2 표준 에러 코드를 포함합니다.

    Attributes:
        error: OAuth2 에러 코드 (예: "invalid_grant", "invalid_client")
        error_description: 에러 상세 설명
        error_uri: 에러 정보 URI (선택)
    """

    status_code: int = 400

    def __init__(
        self,
        error: str,
        error_description: str = "",
        error_uri: str = "",
    ):
        self.error = error
        self.error_description = error_description
        self.error_uri = error_uri
        detail = f"{error}: {error_description}" if error_description else error
        super().__init__(detail)


class InvalidGrantError(OAuth2Error):
    """authorization code가 유효하지 않거나 만료됨

    OAuth2 표준 에러 코드: invalid_grant
    """

    def __init__(
        self, description: str = "The authorization code is invalid or expired"
    ):
        super().__init__("invalid_grant", description)


class InvalidClientError(OAuth2Error):
    """client_id 또는 client_secret이 유효하지 않음

    OAuth2 표준 에러 코드: invalid_client
    """

    status_code: int = 401

    def __init__(self, description: str = "Invalid client credentials"):
        super().__init__("invalid_client", description)


class InvalidTokenError(OAuth2Error):
    """access_token 또는 refresh_token이 유효하지 않음

    OAuth2 표준 에러 코드: invalid_token
    """

    status_code: int = 401

    def __init__(self, description: str = "The token is invalid or expired"):
        super().__init__("invalid_token", description)


class OAuth2RequestError(OAuth2Error):
    """OAuth2 서버 요청 실패

    HTTP 요청 자체가 실패한 경우 (네트워크 오류, 서버 에러 등)

    Attributes:
        status_code: HTTP 상태 코드
        response_body: 응답 본문
    """

    def __init__(self, status_code: int, response_body: str):
        self.response_body = response_body
        super().__init__(
            "request_failed",
            f"OAuth2 request failed with status {status_code}: {response_body}",
        )
        self.status_code = status_code


# -----------------------------------------------------------------------------
# JWT Errors
# -----------------------------------------------------------------------------


class JwtError(UnauthorizedError):
    """JWT 관련 에러 베이스 클래스

    JWT 토큰의 인코딩, 디코딩, 검증 과정에서 발생하는 에러입니다.

    Attributes:
        error: JWT 에러 코드 (예: "token_expired", "invalid_signature")
    """

    def __init__(self, error: str = "jwt_error", detail: str = "JWT error"):
        self.error = error
        super().__init__(detail)


class JwtExpiredError(JwtError):
    """JWT 토큰 만료

    토큰의 exp claim이 현재 시간을 초과한 경우
    """

    def __init__(self, detail: str = "Token has expired"):
        super().__init__("token_expired", detail)


class JwtInvalidSignatureError(JwtError):
    """JWT 서명 불일치

    토큰 서명이 secret_key로 검증되지 않는 경우
    """

    def __init__(self, detail: str = "Invalid token signature"):
        super().__init__("invalid_signature", detail)


class JwtInvalidTokenError(JwtError):
    """JWT 토큰 형식 오류

    토큰 디코딩 자체가 실패한 경우 (형식 오류, 손상 등)
    """

    def __init__(self, detail: str = "Invalid token"):
        super().__init__("invalid_token", detail)


class JwtInvalidAudienceError(JwtError):
    """JWT audience 불일치

    토큰의 aud claim이 예상 audience와 일치하지 않는 경우
    """

    def __init__(self, detail: str = "Invalid token audience"):
        super().__init__("invalid_audience", detail)


class JwtInvalidIssuerError(JwtError):
    """JWT issuer 불일치

    토큰의 iss claim이 예상 issuer와 일치하지 않는 경우
    """

    def __init__(self, detail: str = "Invalid token issuer"):
        super().__init__("invalid_issuer", detail)


# =============================================================================
# System Exceptions (시스템/내부 관련)
# =============================================================================


class SystemException(BloomException):
    """시스템/내부 관련 예외 베이스 클래스

    설정, 초기화, 런타임 등 시스템 레벨에서 발생하는 에러입니다.
    """

    pass


class ConfigurationError(SystemException):
    """설정 관련 예외

    설정 파일 로드 실패, 필수 설정 누락, 잘못된 설정 값 등에서 발생합니다.
    """

    def __init__(self, message: str, key: str = "", value: Any = None):
        self.key = key
        self.value = value
        super().__init__(message)
