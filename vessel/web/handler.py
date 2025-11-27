"""HTTP 메서드 핸들러"""

from typing import Any, Callable, TypeVar, overload

from vessel.core.container import HandlerContainer

T = TypeVar("T")


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
        method: str,
        path: str,
    ):
        # handler_key는 (method, path) 튜플
        super().__init__(handler_method, (method, path))
        self.method = method
        self.path = path

    def __repr__(self) -> str:
        return (
            f"HttpMethodHandler(method={self.handler_method.__name__}, "
            f"{self.method} {self.path})"
        )


def _create_http_method_decorator(http_method: str):
    """HTTP 메서드 데코레이터 생성 팩토리"""

    @overload
    def decorator(__func: Callable[..., T], /) -> Callable[..., T]:
        """@Get def handler(): ... 형태"""
        ...

    @overload
    def decorator(
        __path: str = ..., /
    ) -> Callable[[Callable[..., T]], Callable[..., T]]:
        """@Get("/users") 형태"""
        ...

    def decorator(
        __path_or_func: Callable[..., T] | str | None = None, /
    ) -> Callable[..., T] | Callable[[Callable[..., T]], Callable[..., T]]:
        """
        HTTP 메서드 데코레이터

        사용법:
            @Get                # path = /함수명
            @Get()              # path = /함수명
            @Get("/users")      # path = /users
        """

        def wrapper(func: Callable[..., T]) -> Callable[..., T]:
            # path 결정: callable이면 함수명에서, 아니면 전달된 값 사용
            if callable(__path_or_func):
                path = f"/{func.__name__}"
            else:
                path = __path_or_func if __path_or_func else f"/{func.__name__}"

            container = HttpMethodHandler(func, http_method, path)
            setattr(func, "__container__", container)
            return func

        # @Get (인자 없이 함수 직접 전달)
        if callable(__path_or_func):
            return wrapper(__path_or_func)

        # @Get() 또는 @Get("/path")
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
