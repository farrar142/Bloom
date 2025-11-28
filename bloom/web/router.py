"""라우터 - HTTP 요청을 핸들러에 매칭"""

import asyncio
import dataclasses
from typing import Any, TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from bloom.core.manager import ContainerManager
    from .middleware import MiddlewareChain

from .handler import HttpMethodHandler
from .http import HttpRequest, HttpResponse, StreamingResponse
from .params import resolve_parameters_cached
from .routing import RouteManager


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
    if isinstance(response_type, BaseModel):
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

    RouteManager를 사용하여 라우트를 관리합니다.

    사용 예시:
        router = Router(manager)
        router.collect_routes()  # 등록된 HttpMethodHandler들 수집

        response = router.dispatch(request)
    """

    def __init__(self, manager: "ContainerManager"):
        self.manager = manager
        # RouteManager를 사용한 라우트 관리
        self._route_manager = RouteManager()
        # 미들웨어 체인 (collect_routes에서 수집)
        self._middleware_chain: "MiddlewareChain | None" = None

    @property
    def middleware_chain(self) -> "MiddlewareChain":
        if self._middleware_chain is None:
            raise RuntimeError("MiddlewareChain has not been initialized.")
        return self._middleware_chain

    @property
    def route_manager(self) -> RouteManager:
        """RouteManager 인스턴스"""
        return self._route_manager

    def collect_routes(self) -> None:
        """ContainerManager에서 HttpMethodHandler들을 수집"""
        from .error import ErrorHandlerMiddleware
        from .middleware import MiddlewareChain

        # MiddlewareChain 인스턴스 수집
        if not (
            middleware_chain := self.manager.get_instance(
                MiddlewareChain, raise_exception=False
            )
        ):
            middleware_chain = MiddlewareChain()
        self._middleware_chain = middleware_chain

        # RouteManager 초기화 (라우트 수집)
        self._route_manager.initialize(self.manager)

        # ErrorHandlerMiddleware에 controller_prefixes 전달
        error_handler_middleware = middleware_chain.get_middleware(
            ErrorHandlerMiddleware, raise_exception=False
        )
        if error_handler_middleware:
            error_handler_middleware.set_controller_prefixes(
                self._route_manager.controller_prefixes
            )

    def find_handler(
        self, method: str, path: str
    ) -> tuple[HttpMethodHandler | None, dict[str, str]]:
        """
        요청에 맞는 핸들러 찾기

        시간 복잡도:
        - 정적 경로: O(1) ~ O(세그먼트 개수)
        - 동적 경로: O(세그먼트 개수)
        """
        return self._route_manager.find_handler(method, path)

    async def dispatch(self, request: HttpRequest) -> HttpResponse | StreamingResponse:
        """요청을 핸들러에 디스패치 (비동기)"""

        # 로컬 변수 바인딩 (속성 조회 오버헤드 제거)
        middleware_chain = self.middleware_chain
        route_manager = self._route_manager

        # 핸들러 먼저 찾기 (미들웨어에서 Authorize 검사에 필요)
        handler, path_params = route_manager.find_handler(request.method, request.path)

        async with middleware_chain.process(request, handler) as ctx:
            # early return 확인 (인증 실패 등)
            if ctx.early_response:
                return middleware_chain.get_final_response(ctx)

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
                    # 캐싱된 리졸버 사용 (handler_id로 리졸버 매핑 캐시)
                    resolved_params = await resolve_parameters_cached(
                        id(handler), type_hints, request, path_params
                    )

                    # 핸들러 호출 - 비동기
                    result = await handler(**resolved_params)

                    # 결과 타입에 따라 응답 생성
                    # HttpResponse가 가장 흔하므로 먼저 체크
                    if result.__class__ is HttpResponse:
                        ctx.set_response(result)
                    elif isinstance(result, HttpResponse):
                        # HttpResponse 서브클래스
                        ctx.set_response(result)
                    elif isinstance(result, StreamingResponse):
                        # 스트리밍 응답은 미들웨어를 거치지 않고 직접 반환
                        return result
                    else:
                        # response_type이 있으면 변환
                        response_type = handler.get_metadata(
                            "response_type", raise_exception=False
                        )
                        if response_type:
                            result = _convert_to_response_type(result, response_type)
                        ctx.set_response(HttpResponse.ok(result))

            except Exception as e:
                ctx.set_exception(e)

        return middleware_chain.get_final_response(ctx)

    def get_routes(self) -> list[tuple[str, str, str]]:
        """등록된 라우트 목록 반환 (method, path, handler_name)"""
        return self._route_manager.get_routes()
