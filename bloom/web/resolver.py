"""bloom.web.routing.resolver - Parameter Resolvers"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import (
    Any,
    TypeVar,
    Generic,
    get_origin,
    get_args,
    get_type_hints,
    TYPE_CHECKING,
)

from .params import (
    ParamMarker,
    PathVariable,
    PathVariableMarker,
    Query,
    QueryMarker,
    RequestBody,
    RequestBodyMarker,
    RequestField,
    RequestFieldMarker,
    Header,
    HeaderMarker,
    Cookie,
    CookieMarker,
    UploadedFileMarker,
    Authentication,
    get_param_marker,
    is_optional,
)

if TYPE_CHECKING:
    from .request import HttpRequest
    from .route import RouteMatch


T = TypeVar("T")


# =============================================================================
# Parameter Info
# =============================================================================


@dataclass
class ParameterInfo:
    """핸들러 파라미터 정보"""

    name: str
    annotation: type
    actual_type: type
    marker: ParamMarker | None
    default: Any
    has_default: bool
    is_optional: bool

    @classmethod
    def from_parameter(cls, param: inspect.Parameter) -> "ParameterInfo":
        """inspect.Parameter에서 ParameterInfo 생성"""
        return cls.from_parameter_with_annotation(param, param.annotation)

    @classmethod
    def from_parameter_with_annotation(
        cls, param: inspect.Parameter, annotation: Any
    ) -> "ParameterInfo":
        """inspect.Parameter와 실제 타입 어노테이션에서 ParameterInfo 생성

        from __future__ import annotations 사용 시 get_type_hints()로 얻은
        실제 타입을 전달해야 합니다.
        """
        if annotation is inspect.Parameter.empty:
            annotation = Any

        actual_type, marker = get_param_marker(annotation)
        is_opt, inner_type = is_optional(actual_type)

        if is_opt:
            actual_type = inner_type

        has_default = param.default is not inspect.Parameter.empty
        default = param.default if has_default else None

        # param.default가 ParamMarker인 경우 (Query(default=10) 같은 형태)
        if isinstance(default, ParamMarker):
            if default.has_default():
                has_default = True
                marker = default  # 마커 정보 업데이트
                default = default.default
            else:
                has_default = False
                marker = default
                default = None
        # 마커에 default가 있으면 사용
        elif marker is not None and marker.has_default():
            has_default = True
            default = marker.default

        return cls(
            name=param.name,
            annotation=annotation,
            actual_type=actual_type,
            marker=marker,
            default=default,
            has_default=has_default,
            is_optional=is_opt,
        )


# =============================================================================
# Parameter Resolver Interface
# =============================================================================


class ParameterResolver(ABC, Generic[T]):
    """파라미터 리졸버 인터페이스

    WebSocket, HTTP 등 다양한 프로토콜에서 파라미터를 추출하는 인터페이스입니다.
    상속하여 커스텀 리졸버를 구현할 수 있습니다.

    사용 예:
        class AuthenticationResolver(ParameterResolver[Authentication]):
            def supports(self, param: ParameterInfo) -> bool:
                return param.actual_type is Authentication

            async def resolve(
                self, param: ParameterInfo, request: Request, match: RouteMatch
            ) -> Authentication:
                token = request.header("Authorization")
                return await verify_token(token)
    """

    @abstractmethod
    def supports(self, param: ParameterInfo) -> bool:
        """이 리졸버가 해당 파라미터를 처리할 수 있는지 확인"""
        pass

    @abstractmethod
    async def resolve(
        self,
        param: ParameterInfo,
        request: "HttpRequest",
        match: "RouteMatch",
    ) -> T:
        """파라미터 값을 추출"""
        pass


# =============================================================================
# Built-in Resolvers
# =============================================================================


class RequestResolver(ParameterResolver["HttpRequest"]):
    """Request 객체 자체를 주입하는 리졸버"""

    def supports(self, param: ParameterInfo) -> bool:
        # Request 타입이거나 'request'라는 이름인 경우
        from .request import HttpRequest

        return param.actual_type is HttpRequest or param.name == "HttpRequest"

    async def resolve(
        self,
        param: ParameterInfo,
        request: "HttpRequest",
        match: "RouteMatch",
    ) -> "HttpRequest":
        return request


class PathVariableResolver(ParameterResolver[Any]):
    """Path Variable 리졸버

    /users/{id} 에서 id 값을 추출합니다.
    """

    def supports(self, param: ParameterInfo) -> bool:
        return isinstance(param.marker, PathVariableMarker)

    async def resolve(
        self,
        param: ParameterInfo,
        request: "HttpRequest",
        match: "RouteMatch",
    ) -> Any:
        # 마커에 name이 있으면 그 이름 사용, 없으면 파라미터 이름
        name = param.marker.name if param.marker and param.marker.name else param.name

        value = match.path_params.get(name)
        if value is None:
            if param.has_default:
                return param.default
            if param.is_optional:
                return None
            raise ValueError(f"Path variable '{name}' not found")

        # 타입 변환
        return self._convert_type(value, param.actual_type)

    def _convert_type(self, value: str, target_type: type) -> Any:
        """문자열을 타겟 타입으로 변환"""
        if target_type is str:
            return value
        if target_type is int:
            return int(value)
        if target_type is float:
            return float(value)
        if target_type is bool:
            return value.lower() in ("true", "1", "yes")
        return value


class QueryResolver(ParameterResolver[Any]):
    """Query Parameter 리졸버

    ?page=1&size=10 에서 값을 추출합니다.
    """

    def supports(self, param: ParameterInfo) -> bool:
        return isinstance(param.marker, QueryMarker)

    async def resolve(
        self,
        param: ParameterInfo,
        request: "HttpRequest",
        match: "RouteMatch",
    ) -> Any:
        name = param.marker.name if param.marker and param.marker.name else param.name

        value = request.query_param(name)
        if value is None:
            if param.has_default:
                return param.default
            if param.is_optional:
                return None
            raise ValueError(f"Query parameter '{name}' not found")

        return self._convert_type(value, param.actual_type)

    def _convert_type(self, value: str, target_type: type) -> Any:
        """문자열을 타겟 타입으로 변환"""
        if target_type is str:
            return value
        if target_type is int:
            return int(value)
        if target_type is float:
            return float(value)
        if target_type is bool:
            return value.lower() in ("true", "1", "yes")
        return value


class RequestBodyResolver(ParameterResolver[Any]):
    """Request Body 리졸버

    JSON body를 파싱하여 객체로 변환합니다.
    """

    def supports(self, param: ParameterInfo) -> bool:
        return isinstance(param.marker, RequestBodyMarker)

    async def resolve(
        self,
        param: ParameterInfo,
        request: "HttpRequest",
        match: "RouteMatch",
    ) -> Any:
        body = await request.json()

        if body is None:
            if param.has_default:
                return param.default
            if param.is_optional:
                return None
            raise ValueError("Request body is empty")

        # dataclass나 pydantic 모델이면 변환
        target_type = param.actual_type
        if hasattr(target_type, "__dataclass_fields__"):
            return target_type(**body)
        if hasattr(target_type, "model_validate"):
            # Pydantic v2
            return target_type.model_validate(body)
        if hasattr(target_type, "parse_obj"):
            # Pydantic v1
            return target_type.parse_obj(body)

        # dict 그대로 반환
        return body


class RequestFieldResolver(ParameterResolver[Any]):
    """Request Body Field 리졸버

    Body에서 특정 필드만 추출합니다.
    """

    def supports(self, param: ParameterInfo) -> bool:
        return isinstance(param.marker, RequestFieldMarker)

    async def resolve(
        self,
        param: ParameterInfo,
        request: "HttpRequest",
        match: "RouteMatch",
    ) -> Any:
        body = await request.json()

        if body is None:
            body = {}

        name = param.marker.name if param.marker and param.marker.name else param.name

        if name not in body:
            if param.has_default:
                return param.default
            if param.is_optional:
                return None
            raise ValueError(f"Field '{name}' not found in request body")

        value = body[name]

        # 타입 변환
        target_type = param.actual_type
        if hasattr(target_type, "__dataclass_fields__"):
            return target_type(**value) if isinstance(value, dict) else value
        if hasattr(target_type, "model_validate"):
            return target_type.model_validate(value)

        return value


class HeaderResolver(ParameterResolver[Any]):
    """HTTP Header 리졸버"""

    def supports(self, param: ParameterInfo) -> bool:
        return isinstance(param.marker, HeaderMarker)

    async def resolve(
        self,
        param: ParameterInfo,
        request: "HttpRequest",
        match: "RouteMatch",
    ) -> Any:
        # 마커에 name이 있으면 그 이름 사용
        # 없으면 파라미터 이름을 HTTP 헤더 형식으로 변환
        if param.marker and param.marker.name:
            name = param.marker.name
        else:
            # snake_case → Header-Case
            name = param.name.replace("_", "-").title()

        value = request.header(name)
        if value is None:
            if param.has_default:
                return param.default
            if param.is_optional:
                return None
            raise ValueError(f"Header '{name}' not found")

        return value


class CookieResolver(ParameterResolver[Any]):
    """Cookie 리졸버"""

    def supports(self, param: ParameterInfo) -> bool:
        return isinstance(param.marker, CookieMarker)

    async def resolve(
        self,
        param: ParameterInfo,
        request: "HttpRequest",
        match: "RouteMatch",
    ) -> Any:
        name = param.marker.name if param.marker and param.marker.name else param.name

        value = request.cookie(name)
        if value is None:
            if param.has_default:
                return param.default
            if param.is_optional:
                return None
            raise ValueError(f"Cookie '{name}' not found")

        return value


class UploadedFileResolver(ParameterResolver[Any]):
    """Uploaded File 리졸버

    multipart/form-data 요청에서 업로드된 파일을 추출합니다.
    """

    def supports(self, param: ParameterInfo) -> bool:
        # UploadedFileMarker이거나 타입이 UploadedFile인 경우
        if isinstance(param.marker, UploadedFileMarker):
            return True
        # 타입 이름으로 확인 (순환 import 방지)
        type_name = getattr(param.actual_type, "__name__", "")
        return type_name == "UploadedFile"

    async def resolve(
        self,
        param: ParameterInfo,
        request: "HttpRequest",
        match: "RouteMatch",
    ) -> Any:
        from .upload import parse_multipart, UploadedFile as UploadedFileClass

        # multipart/form-data 파싱
        content_type = request.content_type or ""
        if "multipart/form-data" not in content_type:
            if param.has_default:
                return param.default
            if param.is_optional:
                return None
            raise ValueError("Content-Type must be multipart/form-data for file upload")

        try:
            _, files = await parse_multipart(request)
        except Exception as e:
            if param.has_default:
                return param.default
            if param.is_optional:
                return None
            raise ValueError(f"Failed to parse multipart data: {e}")

        # 파일 이름으로 찾기
        name = param.marker.name if param.marker and param.marker.name else param.name

        file = files.get(name)
        if file is None:
            if param.has_default:
                return param.default
            if param.is_optional:
                return None
            # UploadedFileMarker의 required 체크
            if (
                isinstance(param.marker, UploadedFileMarker)
                and not param.marker.required
            ):
                return None
            raise ValueError(f"File '{name}' not found in upload")

        return file


class AuthenticationResolver(ParameterResolver[Any]):
    """Authentication 리졸버

    request.state.authentication에서 인증 정보를 추출합니다.
    """

    def supports(self, param: ParameterInfo) -> bool:
        if isinstance(param.marker, Authentication):
            return True
        # 타입 이름으로 확인
        type_name = getattr(param.actual_type, "__name__", "")
        return type_name in ("AuthenticationInfo", "Authentication")

    async def resolve(
        self,
        param: ParameterInfo,
        request: "HttpRequest",
        match: "RouteMatch",
    ) -> Any:
        return None
        from ..auth import AuthenticationInfo, AnonymousAuthentication
        from ..error import UnauthorizedError

        # request.state에서 인증 정보 가져오기
        auth = request.state.get("authentication")

        if auth is None:
            if param.has_default:
                return param.default
            if param.is_optional:
                return None
            raise UnauthorizedError("Authentication required")

        # AnonymousAuthentication이면 인증되지 않은 것으로 처리
        if isinstance(auth, AnonymousAuthentication):
            if param.is_optional:
                return None
            raise UnauthorizedError("Authentication required")

        return auth


class ImplicitPathVariableResolver(ParameterResolver[Any]):
    """암시적 Path Variable 리졸버

    마커 없이 파라미터 이름이 path에 있는 경우 자동으로 추출합니다.

    예: /users/{id} 에서 def handler(id: int) 처럼 선언된 경우
    """

    def supports(self, param: ParameterInfo) -> bool:
        # 마커가 없고, 기본 타입인 경우
        if param.marker is not None:
            return False
        return param.actual_type in (str, int, float, bool)

    async def resolve(
        self,
        param: ParameterInfo,
        request: "HttpRequest",
        match: "RouteMatch",
    ) -> Any:
        # path_params에 있으면 추출
        if param.name in match.path_params:
            value = match.path_params[param.name]
            return self._convert_type(value, param.actual_type)

        # query_params에 있으면 추출
        value = request.query_param(param.name)
        if value is not None:
            return self._convert_type(value, param.actual_type)

        # 없으면 default 또는 None
        if param.has_default:
            return param.default
        if param.is_optional:
            return None

        raise ValueError(f"Parameter '{param.name}' not found in path or query")

    def _convert_type(self, value: str, target_type: type) -> Any:
        if target_type is str:
            return value
        if target_type is int:
            return int(value)
        if target_type is float:
            return float(value)
        if target_type is bool:
            return value.lower() in ("true", "1", "yes")
        return value


class ImplicitBodyFieldResolver(ParameterResolver[Any]):
    """암시적 Body Field 리졸버

    마커 없이 복잡한 타입(dataclass 등)인 경우 body에서 추출합니다.
    """

    def supports(self, param: ParameterInfo) -> bool:
        if param.marker is not None:
            return False
        # dataclass나 pydantic 모델
        return (
            hasattr(param.actual_type, "__dataclass_fields__")
            or hasattr(param.actual_type, "model_validate")
            or hasattr(param.actual_type, "parse_obj")
        )

    async def resolve(
        self,
        param: ParameterInfo,
        request: "HttpRequest",
        match: "RouteMatch",
    ) -> Any:
        body = await request.json()
        if body is None:
            if param.has_default:
                return param.default
            if param.is_optional:
                return None
            raise ValueError(f"Request body is required for '{param.name}'")

        # 전체 body를 타입으로 변환
        target_type = param.actual_type
        if hasattr(target_type, "__dataclass_fields__"):
            return target_type(**body)
        if hasattr(target_type, "model_validate"):
            return target_type.model_validate(body)
        if hasattr(target_type, "parse_obj"):
            return target_type.parse_obj(body)

        return body


# =============================================================================
# Resolver Registry
# =============================================================================


class ResolverRegistry:
    """리졸버 레지스트리

    리졸버들을 등록하고 파라미터에 맞는 리졸버를 찾습니다.

    사용 예:
        registry = ResolverRegistry()
        registry.add_resolver(AuthenticationResolver())

        # 기본 리졸버들은 자동 등록됨
    """

    def __init__(self) -> None:
        self._resolvers: list[ParameterResolver[Any]] = []
        self._register_defaults()

    def _register_defaults(self) -> None:
        """기본 리졸버 등록"""
        # 우선순위 순서로 등록 (먼저 등록된 것이 우선)
        self._resolvers.extend(
            [
                RequestResolver(),
                AuthenticationResolver(),  # 인증 정보
                UploadedFileResolver(),  # 파일 업로드
                PathVariableResolver(),
                QueryResolver(),
                RequestBodyResolver(),
                RequestFieldResolver(),
                HeaderResolver(),
                CookieResolver(),
                # 암시적 리졸버는 마지막에
                ImplicitPathVariableResolver(),
                ImplicitBodyFieldResolver(),
            ]
        )

    def add_resolver(self, resolver: ParameterResolver[Any], priority: int = 0) -> None:
        """리졸버 추가

        Args:
            resolver: 추가할 리졸버
            priority: 우선순위 (0이면 맨 앞에 추가)
        """
        if priority == 0:
            self._resolvers.insert(0, resolver)
        else:
            self._resolvers.append(resolver)

    def find_resolver(self, param: ParameterInfo) -> ParameterResolver[Any] | None:
        """파라미터에 맞는 리졸버 찾기"""
        for resolver in self._resolvers:
            if resolver.supports(param):
                return resolver
        return None

    async def resolve_parameters(
        self,
        handler: Any,
        request: "HttpRequest",
        match: "RouteMatch",
    ) -> dict[str, Any]:
        """핸들러의 모든 파라미터 해결

        Returns:
            {param_name: resolved_value} 딕셔너리
        """
        sig = inspect.signature(handler)
        params = sig.parameters

        # get_type_hints로 실제 타입 정보 가져오기 (include_extras=True로 Annotated 유지)
        try:
            type_hints = get_type_hints(handler, include_extras=True)
        except Exception:
            # get_type_hints 실패 시 빈 딕셔너리 사용
            type_hints = {}

        resolved: dict[str, Any] = {}

        for name, param in params.items():
            # self 파라미터는 스킵
            if name == "self":
                continue

            # type_hints에서 실제 타입 가져오기
            annotation = type_hints.get(name, param.annotation)
            param_info = ParameterInfo.from_parameter_with_annotation(param, annotation)
            resolver = self.find_resolver(param_info)

            if resolver is None:
                # 리졸버가 없으면 default 사용
                if param_info.has_default:
                    resolved[name] = param_info.default
                elif param_info.is_optional:
                    resolved[name] = None
                else:
                    raise ValueError(
                        f"No resolver found for parameter '{name}' "
                        f"of type {param_info.annotation}"
                    )
            else:
                try:
                    resolved[name] = await resolver.resolve(param_info, request, match)
                except Exception as e:
                    if param_info.has_default:
                        resolved[name] = param_info.default
                    elif param_info.is_optional:
                        resolved[name] = None
                    else:
                        raise

        return resolved
