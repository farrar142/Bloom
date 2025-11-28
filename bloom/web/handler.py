"""HTTP 메서드 핸들러"""

from typing import Any, Callable, TypeVar, overload
import uuid
from bloom.core.container import Element
from bloom.core.container import HandlerContainer

T = TypeVar("T")
R = TypeVar("R")  # Response type


class MethodElement(Element[T]):
    """HTTP 메서드 정보를 담는 Element"""

    def __init__(self, method: str):
        super().__init__()
        self.metadata["http_method"] = method


class PathElement(Element[T]):
    """HTTP 경로 정보를 담는 Element"""

    def __init__(self, path: str):
        super().__init__()
        self.metadata["http_path"] = path


class ResponseTypeElement(Element[T]):
    """HTTP 응답 타입 정보를 담는 Element"""

    def __init__(self, response_type: type):
        super().__init__()
        self.metadata["response_type"] = response_type


class HttpMethodHandler[**P, R](HandlerContainer[P, R]):
    """
    HTTP 메서드별 핸들러 컨테이너

    @Component
    class UserController:
        @Get("/users")
        def list_users(self) -> list[User]:
            return []

        @Get(path="/users/{id}")
        def get_user(self, id: str) -> User:
            return User(id=id)

        @Post("/users")
        def create_user(self, request: HttpRequest) -> HttpResponse:
            return HttpResponse.created({"id": 1})
    """

    def __init__(
        self,
        handler_method: Callable[P, R],
        handler_key: tuple[str, str] | None = None,
    ):
        super().__init__(handler_method)
        self.handler_key = handler_key

    def __repr__(self) -> str:
        response_type = self.get_metadata("response_type")
        method = self.get_metadata("http_method")
        path = self.get_metadata("http_path")
        response_info = f", response={response_type}" if self else ""
        return (
            f"HttpMethodHandler(method={self.handler_method.__name__}, "
            f"{method} {path}{response_info})"
        )


def _create_http_method_decorator(http_method: str):
    """HTTP 메서드 데코레이터 생성 팩토리"""

    @overload
    def decorator(__func: Callable[..., T], /) -> Callable[..., T]:
        """@Get def handler(): ... 형태"""
        ...

    @overload
    def decorator(
        __path: str = ...,
        /,
        *,
        response: type[R] | None = ...,
    ) -> Callable[[Callable[..., T]], Callable[..., T]]:
        """@Get("/users") 또는 @Get("/users", response=UserOutput) 형태"""
        ...

    def decorator(
        __path_or_func: Callable[..., T] | str | None = None,
        /,
        *,
        response: type | None = None,
    ) -> Callable[..., T] | Callable[[Callable[..., T]], Callable[..., T]]:
        """
        HTTP 메서드 데코레이터

        사용법:
            @Get                              # path = /함수명
            @Get()                            # path = /함수명
            @Get("/users")                    # path = /users
            @Get("/users", response=Output)   # path = /users, 반환값을 Output으로 변환

        Args:
            __path_or_func: 경로 문자열 또는 데코레이트할 함수
            response: 반환값을 변환할 타입 (pydantic BaseModel 또는 dataclass)
        """

        def wrapper(func: Callable[..., T]) -> Callable[..., T]:
            # path 결정: callable이면 함수명에서, 아니면 전달된 값 사용
            if callable(__path_or_func):
                path = f"/{func.__name__}"
            else:
                path = __path_or_func if __path_or_func else f"/{func.__name__}"
            container = HttpMethodHandler.get_or_create(func, (http_method, path))
            setattr(func, "__container__", container)
            container.add_elements(MethodElement(http_method))
            container.add_elements(PathElement(path))
            if response:
                container.add_elements(ResponseTypeElement(response))
            return func

        # @Get (인자 없이 함수 직접 전달)
        if callable(__path_or_func):
            return wrapper(__path_or_func)

        # @Get() 또는 @Get("/path") 또는 @Get("/path", response=Output)
        return wrapper

    return decorator


# HTTP 메서드 데코레이터들
Get = _create_http_method_decorator("GET")
"""GET 요청 핸들러

사용법:
    @Get                    # path = /함수명
    @Get("/users")          # path = /users
"""

Post = _create_http_method_decorator("POST")
"""POST 요청 핸들러"""

Put = _create_http_method_decorator("PUT")
"""PUT 요청 핸들러"""

Patch = _create_http_method_decorator("PATCH")
"""PATCH 요청 핸들러"""

Delete = _create_http_method_decorator("DELETE")
"""DELETE 요청 핸들러"""
