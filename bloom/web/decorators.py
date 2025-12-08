from enum import Enum
from pickle import PUT
from typing import Callable, overload
from bloom.core import Container, HandlerContainer, get_container_manager
from bloom.core.container.functions import Method, MethodDecorator

from .route import Route


@overload
def Controller[T](path: str) -> Callable[[type[T]], type[T]]: ...
@overload
def Controller[T](path: type[T]) -> type[T]: ...


def Controller[T](path: type[T] | str) -> type[T] | Callable[[type[T]], type[T]]:
    """컨트롤러 데코레이터"""
    if isinstance(path, str):
        if not path.startswith("/"):
            path = "/" + path

        def wrapper(cls: type[T]) -> type[T]:
            container = Container.register(cls)
            container.add_element("path_prefix", path)
            return cls

        return wrapper
    container = Container.register(path)
    container.add_element("path_prefix", "")
    return path


class RouteContainer(HandlerContainer):
    pass


def _MethodDecorator(method: str):
    """HTTP 메서드 데코레이터 클래스

    오버로드를 통해 타입 안전성을 보장합니다.
    """

    @overload
    def decorator[**P, T, R](func: Method[P, T, R]) -> Method[P, T, R]:
        """@GetMapping - path 없이 직접 함수에 적용"""
        ...

    @overload
    def decorator[**P, T, R](
        *,
        path: str = "",
    ) -> Method[P, T, R]:
        """@GetMapping("/path") - path 지정"""
        ...

    def decorator[**P, T, R](
        func: Method[P, T, R] | None = None,
        *,
        path: str = "",
    ) -> Method[P, T, R] | MethodDecorator[P, T, R]:
        if func is not None:
            # 직접 함수에 적용된 경우
            container = RouteContainer.register(func)
            container.add_element("method", method)
            container.add_element("path", "")
            return func

        def decorator(func: Method[P, T, R]) -> Method[P, T, R]:
            container = RouteContainer.register(func)
            container.add_element("method", method)
            container.add_element("path", path)
            return func

        return decorator

    return decorator


# 각 HTTP 메서드별 데코레이터
GetMapping = _MethodDecorator("GET")
PostMapping = _MethodDecorator("POST")
PutMapping = _MethodDecorator("PUT")
DeleteMapping = _MethodDecorator("DELETE")
PatchMapping = _MethodDecorator("PATCH")
