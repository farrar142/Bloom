"""ErrorHandlerContainer - 예외 처리 핸들러 컨테이너"""

from typing import Any, Callable, TypeVar

from bloom.core.container import Element, HandlerContainer

T = TypeVar("T")
E = TypeVar("E", bound=Exception)


class ExceptionTypeElement[T](Element[T]):
    """예외 타입을 담는 Element"""

    def __init__(self, exception_type: type[Exception]):
        super().__init__()
        self.metadata["exception_type"] = exception_type

    @property
    def exception_type(self) -> type[Exception]:
        return self.metadata["exception_type"]


class ErrorHandlerContainer[**P, R](HandlerContainer[P, R]):
    """
    예외 처리 핸들러 컨테이너

    예외 타입을 키로 사용하여 해당 예외 발생 시 호출될 핸들러를 등록합니다.

    사용법:
        @Controller
        @RequestMapping("/api/users")
        class UserController:
            @ErrorHandler(ValueError)
            def handle_value_error(self, error: ValueError) -> HttpResponse:
                return HttpResponse.bad_request(str(error))

            # 여러 예외 타입 처리
            @ErrorHandler(KeyError, IndexError)
            def handle_lookup_errors(self, error: Exception) -> HttpResponse:
                return HttpResponse.bad_request(f"Lookup error: {error}")

        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(Exception)
            def handle_all_errors(self, error: Exception) -> HttpResponse:
                return HttpResponse.internal_error(str(error))

    스코프:
        - Controller에 정의: 해당 Controller의 RequestMapping 경로 하위에서만 동작
        - Component에 정의: 모든 엔드포인트에서 동작 (글로벌)

    우선순위:
        1. Controller 스코프의 정확한 예외 타입
        2. Controller 스코프의 부모 예외 타입
        3. 글로벌 스코프의 정확한 예외 타입
        4. 글로벌 스코프의 부모 예외 타입
    """

    def __init__(
        self,
        handler_method: Callable[P, R],
    ):
        super().__init__(handler_method)

    @property
    def exception_types(self) -> list[type[Exception]]:
        """처리 가능한 모든 예외 타입 반환"""
        return [
            e.exception_type
            for e in self.elements
            if isinstance(e, ExceptionTypeElement)
        ]

    @property
    def exception_type(self) -> type[Exception] | None:
        """첫 번째 예외 타입 반환 (하위 호환성)"""
        types = self.exception_types
        return types[0] if types else None

    def __repr__(self) -> str:
        owner = self.owner_cls.__name__ if self.owner_cls else "Unknown"
        exc_types = self.exception_types
        if len(exc_types) == 1:
            exc_name = exc_types[0].__name__
        elif exc_types:
            exc_name = f"[{', '.join(t.__name__ for t in exc_types)}]"
        else:
            exc_name = "Unknown"
        return (
            f"ErrorHandlerContainer("
            f"method={self.handler_method.__name__}, "
            f"exception={exc_name}, "
            f"owner={owner})"
        )

    def can_handle(self, exception: Exception) -> bool:
        """이 핸들러가 주어진 예외를 처리할 수 있는지 확인"""
        return any(isinstance(exception, t) for t in self.exception_types)


def ErrorHandler[T](
    *exception_types: type[Exception],
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    예외 핸들러 데코레이터

    지정된 예외 타입이 발생했을 때 호출될 핸들러 메서드를 등록합니다.

    Args:
        *exception_types: 처리할 예외 타입들 (1개 이상)

    Returns:
        데코레이터 함수

    사용법:
        @Controller
        class UserController:
            @ErrorHandler(ValueError)
            def handle_value_error(self, error: ValueError) -> HttpResponse:
                return HttpResponse.bad_request(str(error))

            # 여러 예외 타입 처리
            @ErrorHandler(KeyError, IndexError, AttributeError)
            def handle_lookup_errors(self, error: Exception) -> HttpResponse:
                return HttpResponse.bad_request(f"Lookup error: {error}")

            @ErrorHandler(NotFoundException)
            def handle_not_found(self, error: NotFoundException) -> HttpResponse:
                return HttpResponse.not_found(error.message)

        # 글로벌 핸들러 (모든 엔드포인트에서 동작)
        @Component
        class GlobalHandlers:
            @ErrorHandler(Exception)
            def fallback_handler(self, error: Exception) -> HttpResponse:
                return HttpResponse.internal_error("Internal Server Error")
    """
    if not exception_types:
        raise ValueError("At least one exception type must be provided")

    def decorator(method: Callable[..., T]) -> Callable[..., T]:
        container = ErrorHandlerContainer.get_or_create(method)
        for exc_type in exception_types:
            container.add_element(ExceptionTypeElement(exc_type))
        return method

    return decorator
