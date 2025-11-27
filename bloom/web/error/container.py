"""ErrorHandlerContainer - 예외 처리 핸들러 컨테이너"""

from typing import Any, Callable, TypeVar

from bloom.core.container import HandlerContainer

T = TypeVar("T")
E = TypeVar("E", bound=Exception)


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
        exception_type: type[Exception],
    ):
        super().__init__(handler_method)
        self.exception_type = exception_type

    def __repr__(self) -> str:
        owner = self.owner_cls.__name__ if self.owner_cls else "Unknown"
        return (
            f"ErrorHandlerContainer("
            f"method={self.handler_method.__name__}, "
            f"exception={self.exception_type.__name__}, "
            f"owner={owner})"
        )

    def can_handle(self, exception: Exception) -> bool:
        """이 핸들러가 주어진 예외를 처리할 수 있는지 확인"""
        return isinstance(exception, self.exception_type)

    def get_qual_name(self) -> str:
        """exception_type 기반으로 고유 qualifier 생성"""
        owner_name = self.owner_cls.__name__ if self.owner_cls else "global"
        return f"error_handler:{owner_name}:{self.exception_type.__name__}"


def ErrorHandler[T](
    exception_type: type[Exception],
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    예외 핸들러 데코레이터

    지정된 예외 타입이 발생했을 때 호출될 핸들러 메서드를 등록합니다.

    Args:
        exception_type: 처리할 예외 타입

    Returns:
        데코레이터 함수

    사용법:
        @Controller
        class UserController:
            @ErrorHandler(ValueError)
            def handle_value_error(self, error: ValueError) -> HttpResponse:
                return HttpResponse.bad_request(str(error))

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

    def decorator(method: Callable[..., T]) -> Callable[..., T]:
        ErrorHandlerContainer.get_or_create(method, exception_type)
        return method

    return decorator
