"""라우터 - HTTP 요청을 핸들러에 매칭"""

import asyncio
import dataclasses
import re
from typing import Any, TYPE_CHECKING

from vessel.core import ContainerManager

from .controller import ControllerContainer
from .handler import HttpMethodHandler
from .http import HttpRequest, HttpResponse
from .params import resolve_parameters

if TYPE_CHECKING:
    from .middleware import MiddlewareChain


def _convert_to_response_type(result: Any, response_type: type) -> Any:
    """
    핸들러 반환값을 response_type으로 변환

    - pydantic BaseModel: model_validate()로 변환
    - dataclass: 직접 생성자 호출

    Args:
        result: 핸들러 반환값 (dict 또는 다른 객체)
        response_type: 변환할 타입

    Returns:
        response_type의 인스턴스
    """
    # 이미 response_type 인스턴스면 그대로 반환
    if isinstance(result, response_type):
        return result

    # pydantic BaseModel인 경우
    if hasattr(response_type, "model_validate"):
        if isinstance(result, dict):
            return response_type.model_validate(result)
        # dict가 아니면 model_validate에 맡김
        return response_type.model_validate(result)

    # dataclass인 경우
    if dataclasses.is_dataclass(response_type):
        if isinstance(result, dict):
            return response_type(**result)
        # 이미 dataclass 인스턴스면 그대로 반환
        if dataclasses.is_dataclass(result):
            return result
        raise TypeError(
            f"Cannot convert {type(result).__name__} to dataclass {response_type.__name__}"
        )

    # 그 외: 직접 생성자 호출 시도
    if isinstance(result, dict):
        return response_type(**result)

    return result


class Router:
    """
    HTTP 요청을 적절한 핸들러에 라우팅

    사용 예시:
        router = Router()
        router.collect_routes()  # 등록된 HttpMethodHandler들 수집

        response = router.dispatch(request)
    """

    def __init__(self):
        # (method, path_pattern) -> HttpMethodHandler
        self._routes: dict[tuple[str, str], HttpMethodHandler] = {}
        # 컴파일된 정규식 패턴 캐시
        self._compiled_patterns: dict[str, re.Pattern] = {}
        # 미들웨어 체인 (collect_routes에서 수집)
        self._middleware_chain: "MiddlewareChain | None" = None

    @property
    def middleware_chain(self) -> "MiddlewareChain":
        if self._middleware_chain is None:
            raise RuntimeError("MiddlewareChain has not been initialized.")
        return self._middleware_chain

    def collect_routes(self) -> None:
        """ContainerManager에서 HttpMethodHandler들을 수집"""
        from .middleware import ErrorHandlerMiddleware, MiddlewareChain

        # MiddlewareChain 인스턴스 수집
        if not (
            middleware_chain := ContainerManager.get_instance(
                MiddlewareChain, raise_exception=False
            )
        ):
            middleware_chain = MiddlewareChain()
        self._middleware_chain = middleware_chain

        # Controller의 RequestMapping prefix 매핑
        controller_prefixes: dict[type, str] = {}
        for qual_containers in ContainerManager.get_all_containers().values():
            for container in qual_containers.values():
                if isinstance(container, ControllerContainer):
                    # Use generic metadata API to obtain request mapping prefixes.
                    prefixes = container.get_metadatas("request_mapping", default="")
                    controller_prefixes[container.target] = (
                        prefixes[0] if prefixes else ""
                    )
        self._controller_prefixes = controller_prefixes

        # ErrorHandlerMiddleware에 controller_prefixes 전달
        error_handler_middleware = middleware_chain.get_middleware(
            ErrorHandlerMiddleware, raise_exception=False
        )
        if error_handler_middleware:
            error_handler_middleware.set_controller_prefixes(controller_prefixes)

        # 모든 컨테이너를 순회하며 HttpMethodHandler 찾기
        for qual_containers in ContainerManager.get_all_containers().values():
            for container in qual_containers.values():
                if isinstance(container, HttpMethodHandler):
                    # owner_cls의 RequestMapping prefix 가져오기
                    prefix = ""
                    if container.owner_cls:
                        prefix = controller_prefixes.get(container.owner_cls, "")

                    # prefix + handler path 결합
                    full_path = prefix + container.get_metadata("http_path")
                    key = (container.get_metadata("http_method"), full_path)
                    self._routes[key] = container
                    # 경로 패턴 컴파일 (path parameter 지원)
                    self._compile_pattern(full_path)

    def _compile_pattern(self, path: str) -> re.Pattern:
        """경로를 정규식 패턴으로 변환 (예: /users/{id} -> /users/(?P<id>[^/]+))"""
        if path not in self._compiled_patterns:
            # {param} 형식을 정규식으로 변환
            pattern = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", path)
            self._compiled_patterns[path] = re.compile(f"^{pattern}$")
        return self._compiled_patterns[path]

    def _match_path(self, path: str, pattern_path: str) -> tuple[bool, dict[str, str]]:
        """경로 매칭 및 path parameter 추출"""
        pattern = self._compiled_patterns.get(pattern_path)
        if not pattern:
            return False, {}

        match = pattern.match(path)
        if match:
            return True, match.groupdict()
        return False, {}

    def find_handler(
        self, method: str, path: str
    ) -> tuple[HttpMethodHandler | None, dict[str, str]]:
        """요청에 맞는 핸들러 찾기"""
        # 정확히 일치하는 경로 먼저 확인
        exact_key = (method, path)
        if exact_key in self._routes:
            return self._routes[exact_key], {}

        # 패턴 매칭으로 확인
        for (route_method, route_path), handler in self._routes.items():
            if route_method != method:
                continue
            matched, params = self._match_path(path, route_path)
            if matched:
                return handler, params

        return None, {}

    async def dispatch(self, request: HttpRequest) -> HttpResponse:
        """요청을 핸들러에 디스패치 (비동기)"""

        # 핸들러 먼저 찾기 (미들웨어에서 Authorize 검사에 필요)
        handler, path_params = self.find_handler(request.method, request.path)

        async with self.middleware_chain.process(request, handler) as ctx:
            # early return 확인 (인증 실패 등)
            if ctx.early_response:
                return self.middleware_chain.get_final_response(ctx)

            try:
                if handler is None:
                    ctx.set_response(
                        HttpResponse.not_found(
                            f"No handler for {request.method} {request.path}"
                        )
                    )
                else:
                    # 핸들러의 타입 힌트로 파라미터 리졸버를 통해 값 주입
                    type_hints = handler.get_type_hints()
                    resolved_params = await resolve_parameters(
                        type_hints, request, path_params
                    )

                    # 핸들러 호출 - 비동기
                    result = await handler(**resolved_params)

                    # 결과 타입에 따라 응답 생성
                    if isinstance(result, HttpResponse):
                        ctx.set_response(result)
                    else:
                        # response_type이 있으면 변환
                        if response_type := handler.get_metadata(
                            "response_type", raise_exception=False
                        ):
                            result = _convert_to_response_type(result, response_type)
                        ctx.set_response(HttpResponse.ok(result))

            except Exception as e:
                ctx.set_exception(e)

        return self.middleware_chain.get_final_response(ctx)

    def get_routes(self) -> list[tuple[str, str, str]]:
        """등록된 라우트 목록 반환 (method, path, handler_name)"""
        return [
            (method, path, handler.handler_method.__name__)
            for (method, path), handler in self._routes.items()
        ]
