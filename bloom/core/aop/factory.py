"""
DecoratorFactory: 일반 파이썬 데코레이터를 AOP 인터셉터로 변환

사용자가 익숙한 파이썬 데코레이터 문법으로 AOP 기능을 구현할 수 있게 함.

지원하는 사용법:
    1. @RateLimited                    # 인자 없이
    2. @RateLimited()                  # 빈 괄호
    3. @RateLimited(limit=100)         # 키워드 인자
    4. @RateLimited(100, 60)           # 위치 인자

InjectableDecoratorFactory 추가 지원:
    - 데코레이터 내에서 DI 컨테이너로부터 의존성 주입 가능
    - 타입 힌트된 파라미터를 자동으로 주입
"""

from typing import Any, Callable, TypeVar, ParamSpec, overload, Generic, get_type_hints, TYPE_CHECKING
from functools import wraps
import inspect

from .interceptor import MethodInterceptor, MethodInvocation
from .descriptor import InterceptorInfo, ensure_method_descriptor
from .registry import get_interceptor_registry

if TYPE_CHECKING:
    from ..manager import ContainerManager


P = ParamSpec("P")
F = TypeVar("F", bound=Callable[..., Any])


class WrapperInterceptor(MethodInterceptor):
    """
    파이썬 데코레이터 래퍼 함수를 인터셉터로 변환.

    일반 데코레이터의 wrapper 함수가 proceed를 호출하는 것처럼 동작.
    """

    def __init__(
        self,
        wrapper_factory: Callable[..., Callable],
        wrapper_args: tuple,
        wrapper_kwargs: dict,
        order: int = 0,
    ):
        self.wrapper_factory = wrapper_factory
        self.wrapper_args = wrapper_args
        self.wrapper_kwargs = wrapper_kwargs
        self.order = order

    async def intercept(
        self,
        invocation: MethodInvocation,
        proceed: Callable[[], Any],
    ) -> Any:
        # 원본 함수가 동기/비동기인지 확인
        is_async = inspect.iscoroutinefunction(invocation.method)

        if is_async:
            # 비동기 버전
            async def fake_func(*args, **kwargs):
                invocation.args = args
                invocation.kwargs = kwargs
                return await proceed()
        else:
            # 동기 버전 - 하지만 proceed는 항상 async이므로 래핑 필요
            async def fake_func(*args, **kwargs):
                invocation.args = args
                invocation.kwargs = kwargs
                return await proceed()

        # wrapper 생성 (데코레이터 팩토리 호출)
        wrapper = self.wrapper_factory(*self.wrapper_args, **self.wrapper_kwargs)(
            fake_func
        )

        # wrapper 실행
        if inspect.iscoroutinefunction(wrapper):
            result = await wrapper(*invocation.args, **invocation.kwargs)
        else:
            result = wrapper(*invocation.args, **invocation.kwargs)
            if inspect.iscoroutine(result):
                result = await result
        return result


class DecoratorFactory(Generic[P]):
    """
    일반 파이썬 데코레이터 팩토리를 AOP 어노테이션으로 변환.

    @RateLimited, @RateLimited(), @RateLimited(limit=100) 모두 지원.

    Usage:
        # 1. 일반 파이썬 데코레이터 정의 (기본값 있음)
        def rate_limited(limit: int = 100, window: int = 60):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    # rate limit 로직
                    return await func(*args, **kwargs)
                return wrapper
            return decorator

        # 2. AOP 어노테이션으로 변환
        RateLimited = DecoratorFactory(rate_limited)

        # 3. 다양한 방식으로 사용
        @Component
        class MyService:
            @RateLimited                    # 기본값 사용
            async def method1(self): ...

            @RateLimited()                  # 기본값 사용
            async def method2(self): ...

            @RateLimited(limit=50)          # 커스텀 값
            async def method3(self): ...
    """

    def __init__(
        self,
        decorator_factory: Callable[P, Callable[[Callable], Callable]],
        *,
        order: int = 0,
        interceptor_type: str | None = None,
    ):
        """
        Args:
            decorator_factory: 데코레이터를 반환하는 팩토리 함수
            order: 인터셉터 실행 순서 (낮을수록 먼저)
            interceptor_type: 인터셉터 타입 ID (None이면 자동 생성)
        """
        self._decorator_factory = decorator_factory
        self._order = order
        self._interceptor_type = (
            interceptor_type or f"decorator_factory_{id(decorator_factory)}"
        )

        # 레지스트리에 팩토리 등록
        self._register_factory()

    def _register_factory(self) -> None:
        """인터셉터 팩토리를 레지스트리에 등록"""
        registry = get_interceptor_registry()
        decorator_factory = self._decorator_factory

        @registry.register_factory(self._interceptor_type)
        def factory(info: InterceptorInfo) -> MethodInterceptor:
            return WrapperInterceptor(
                wrapper_factory=decorator_factory,
                wrapper_args=info.metadata.get("args", ()),
                wrapper_kwargs=info.metadata.get("kwargs", {}),
                order=info.order,
            )

    def _apply_decorator(
        self,
        func: F,
        args: tuple,
        kwargs: dict,
        order: int,
    ) -> F:
        """실제 데코레이터 적용 로직"""
        # 1. AOP 메타데이터 등록
        descriptor = ensure_method_descriptor(func)
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type=self._interceptor_type,
                order=order,
                metadata={"args": args, "kwargs": kwargs},
            )
        )

        # 2. 원본 데코레이터도 적용 (프록시 없이 직접 호출 시를 위해)
        decorated = self._decorator_factory(*args, **kwargs)(func)

        # 3. AOP 메타데이터를 decorated 함수에도 복사
        if hasattr(func, "__bloom_method_descriptor__"):
            setattr(
                decorated,
                "__bloom_method_descriptor__",
                getattr(func, "__bloom_method_descriptor__"),
            )

        return decorated  # type: ignore

    @overload
    def __call__(self, func: F) -> F:
        """@RateLimited (인자 없이 직접 함수에 적용)"""
        ...

    @overload
    def __call__(
        self,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> Callable[[F], F]:
        """@RateLimited() 또는 @RateLimited(limit=100)"""
        ...

    def __call__(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Callable[[F], F] | F:
        """
        두 가지 사용법 지원:
        1. @RateLimited - 첫 번째 인자가 callable이면 직접 적용
        2. @RateLimited(...) - 데코레이터 팩토리 반환
        """
        # Case 1: @RateLimited (인자 없이)
        # 첫 번째 인자가 callable이고 다른 인자가 없으면 직접 적용
        if (
            len(args) == 1
            and len(kwargs) == 0
            and callable(args[0])
            and not isinstance(args[0], type)  # 클래스가 아닌 경우만
        ):
            func = args[0]
            return self._apply_decorator(func, (), {}, self._order)

        # Case 2: @RateLimited() 또는 @RateLimited(limit=100)
        # order 키워드 인자 추출
        order = kwargs.pop("order", None)
        actual_order = order if order is not None else self._order

        def decorator(func: F) -> F:
            return self._apply_decorator(func, args, kwargs, actual_order)

        return decorator

    def __repr__(self) -> str:
        return f"<DecoratorFactory({self._decorator_factory.__name__})>"


class SimpleDecoratorFactory(Generic[P]):
    """
    더 간단한 버전 - 파이썬 데코레이터를 그대로 사용하면서 메타데이터만 추가.

    AOP 프록시 없이도 동작하고, 프록시가 있으면 인터셉터 체인에도 포함됨.

    @RateLimited, @RateLimited(), @RateLimited(limit=100) 모두 지원.
    """

    def __init__(
        self,
        decorator_factory: Callable[P, Callable[[Callable], Callable]],
        *,
        interceptor_type: str | None = None,
        order: int = 0,
    ):
        self._decorator_factory = decorator_factory
        self._interceptor_type = interceptor_type or decorator_factory.__name__
        self._order = order

    def _apply_decorator(
        self,
        func: F,
        args: tuple,
        kwargs: dict,
        order: int,
    ) -> F:
        """실제 데코레이터 적용 로직"""
        # 1. 원본 데코레이터 적용
        decorated = self._decorator_factory(*args, **kwargs)(func)

        # 2. AOP 메타데이터 등록
        descriptor = ensure_method_descriptor(decorated)
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type=self._interceptor_type,
                order=order,
                metadata={"args": args, "kwargs": kwargs},
            )
        )

        return decorated  # type: ignore

    @overload
    def __call__(self, func: F) -> F:
        """@RateLimited (인자 없이)"""
        ...

    @overload
    def __call__(
        self,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> Callable[[F], F]:
        """@RateLimited() 또는 @RateLimited(limit=100)"""
        ...

    def __call__(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Callable[[F], F] | F:
        # Case 1: @RateLimited (인자 없이)
        if (
            len(args) == 1
            and len(kwargs) == 0
            and callable(args[0])
            and not isinstance(args[0], type)
        ):
            func = args[0]
            return self._apply_decorator(func, (), {}, self._order)

        # Case 2: @RateLimited() 또는 @RateLimited(limit=100)
        order = kwargs.pop("order", None)
        actual_order = order if order is not None else self._order

        def decorator(func: F) -> F:
            return self._apply_decorator(func, args, kwargs, actual_order)

        return decorator


# ============================================================
# 헬퍼 함수들
# ============================================================


def create_annotation(
    decorator_factory: Callable[P, Callable[[Callable], Callable]],
    *,
    order: int = 0,
    interceptor_type: str | None = None,
) -> DecoratorFactory[P]:
    """
    일반 파이썬 데코레이터를 AOP 어노테이션으로 변환하는 헬퍼.

    Usage:
        def my_decorator(arg1: int = 10, arg2: str = "default"):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    return await func(*args, **kwargs)
                return wrapper
            return decorator

        MyAnnotation = create_annotation(my_decorator, order=-50)

        # 사용
        @MyAnnotation           # 기본값 사용
        @MyAnnotation()         # 기본값 사용
        @MyAnnotation(arg1=20)  # 커스텀 값
    """
    return DecoratorFactory(
        decorator_factory,
        order=order,
        interceptor_type=interceptor_type,
    )


# ============================================================
# Injectable Decorator Factory (DI 지원)
# ============================================================


class InjectableInterceptor(MethodInterceptor):
    """
    DI 의존성 주입을 지원하는 인터셉터.

    데코레이터 팩토리 함수의 타입 힌트를 분석하여
    컨테이너에서 자동으로 의존성을 주입.
    """

    def __init__(
        self,
        decorator_factory: Callable[..., Callable],
        explicit_args: tuple,
        explicit_kwargs: dict,
        injectable_params: dict[str, type],  # 파라미터명 -> 타입
        order: int = 0,
    ):
        self.decorator_factory = decorator_factory
        self.explicit_args = explicit_args
        self.explicit_kwargs = explicit_kwargs
        self.injectable_params = injectable_params
        self.order = order

    async def intercept(
        self,
        invocation: MethodInvocation,
        proceed: Callable[[], Any],
    ) -> Any:
        # 컨테이너에서 의존성 주입받기
        injected_kwargs = dict(self.explicit_kwargs)

        # 주입 가능한 파라미터들 처리
        container_manager = invocation.attributes.get("container_manager")
        if container_manager and self.injectable_params:
            for param_name, param_type in self.injectable_params.items():
                # 명시적으로 전달되지 않은 파라미터만 주입
                if param_name not in injected_kwargs:
                    try:
                        instance = await container_manager.get_instance_async(
                            param_type, required=False
                        )
                        if instance is not None:
                            injected_kwargs[param_name] = instance
                    except Exception:
                        pass  # 주입 실패 시 무시 (기본값 사용)

        # proceed를 호출하는 가짜 함수 생성
        async def fake_func(*args, **kwargs):
            invocation.args = args
            invocation.kwargs = kwargs
            return await proceed()

        # fake_func의 메타데이터를 원본 함수처럼 설정
        fake_func.__name__ = invocation.method_name
        fake_func.__qualname__ = invocation.method_name

        # wrapper 생성 (데코레이터 팩토리 호출)
        wrapper = self.decorator_factory(*self.explicit_args, **injected_kwargs)(
            fake_func
        )

        # wrapper 실행
        if inspect.iscoroutinefunction(wrapper):
            result = await wrapper(*invocation.args, **invocation.kwargs)
        else:
            result = wrapper(*invocation.args, **invocation.kwargs)
            if inspect.iscoroutine(result):
                result = await result
        return result


class InjectableDecoratorFactory(Generic[P]):
    """
    DI 컨테이너에서 의존성을 주입받는 데코레이터 팩토리.

    데코레이터 팩토리 함수의 파라미터 중 타입 힌트된 클래스들을
    자동으로 컨테이너에서 주입받음.

    Usage:
        @Component
        class RateLimitService:
            async def check(self, key: str, limit: int) -> bool:
                # rate limit 체크 로직
                return True

        # 데코레이터 팩토리 정의 - 타입 힌트로 주입받을 의존성 표시
        def rate_limited(
            limit: int = 100,
            window: int = 60,
            *,
            rate_service: RateLimitService,  # DI로 주입됨
        ):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    # rate_service는 컨테이너에서 주입받음
                    key = func.__name__
                    if not await rate_service.check(key, limit):
                        raise RuntimeError("Rate limit exceeded")
                    return await func(*args, **kwargs)
                return wrapper
            return decorator

        # Injectable 어노테이션으로 변환
        RateLimited = InjectableDecoratorFactory(rate_limited)

        @Component
        class MyService:
            @RateLimited(limit=50)  # rate_service는 자동 주입
            async def api_call(self):
                return "success"
    """

    def __init__(
        self,
        decorator_factory: Callable[P, Callable[[Callable], Callable]],
        *,
        order: int = 0,
        interceptor_type: str | None = None,
    ):
        self._decorator_factory = decorator_factory
        self._order = order
        self._interceptor_type = (
            interceptor_type or f"injectable_decorator_{id(decorator_factory)}"
        )
        self._injectable_params = self._analyze_injectable_params()

        # 레지스트리에 팩토리 등록
        self._register_factory()

    def _analyze_injectable_params(self) -> dict[str, type]:
        """데코레이터 팩토리에서 주입 가능한 파라미터 분석"""
        injectable: dict[str, type] = {}

        try:
            sig = inspect.signature(self._decorator_factory)

            # get_type_hints가 실패할 경우를 대비해 __annotations__도 활용
            try:
                hints = get_type_hints(self._decorator_factory)
            except Exception:
                hints = getattr(self._decorator_factory, "__annotations__", {})

            for param_name, param in sig.parameters.items():
                if param_name == "return":
                    continue

                # 타입 힌트 가져오기
                param_type = hints.get(param_name)

                # 힌트가 없으면 annotation에서 직접 확인
                if param_type is None and param.annotation != inspect.Parameter.empty:
                    param_type = param.annotation

                if param_type is None:
                    continue

                # Union 타입 처리 (X | None 형식)
                # Python 3.10+ UnionType 체크
                if type(param_type).__name__ == "UnionType":
                    # Union의 첫 번째 non-None 타입 추출
                    args = getattr(param_type, "__args__", ())
                    for arg in args:
                        if arg is not type(None):
                            param_type = arg
                            break

                # 클래스 타입인지 확인
                if inspect.isclass(param_type):
                    # 내장 타입은 제외
                    if param_type.__module__ == "builtins":
                        continue
                    injectable[param_name] = param_type

        except Exception:
            pass

        return injectable

    def _register_factory(self) -> None:
        """인터셉터 팩토리를 레지스트리에 등록"""
        registry = get_interceptor_registry()
        decorator_factory = self._decorator_factory
        injectable_params = self._injectable_params

        @registry.register_factory(self._interceptor_type)
        def factory(info: InterceptorInfo) -> MethodInterceptor:
            return InjectableInterceptor(
                decorator_factory=decorator_factory,
                explicit_args=info.metadata.get("args", ()),
                explicit_kwargs=info.metadata.get("kwargs", {}),
                injectable_params=injectable_params,
                order=info.order,
            )

    def _apply_decorator(
        self,
        func: F,
        args: tuple,
        kwargs: dict,
        order: int,
    ) -> F:
        """실제 데코레이터 적용 로직"""
        # 1. AOP 메타데이터 등록
        descriptor = ensure_method_descriptor(func)
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type=self._interceptor_type,
                order=order,
                metadata={
                    "args": args,
                    "kwargs": kwargs,
                    "injectable_params": list(self._injectable_params.keys()),
                },
            )
        )

        # 2. 원본 데코레이터도 적용하되, 주입 가능한 파라미터는 None으로 처리
        # (프록시 없이 직접 호출 시를 위해)
        try:
            full_kwargs = dict(kwargs)
            for param_name in self._injectable_params:
                if param_name not in full_kwargs:
                    full_kwargs[param_name] = None

            decorated = self._decorator_factory(*args, **full_kwargs)(func)
        except TypeError:
            # 필수 파라미터가 없으면 원본 함수 그대로 사용
            decorated = func

        # 3. 원본 함수를 저장 (인터셉터 체인에서 사용)
        # InjectableInterceptor가 DI로 새 wrapper를 생성하고,
        # InterceptorChain._invoke_target이 이 원본 함수를 호출해야 함
        setattr(decorated, "__bloom_original_method__", func)

        # 4. AOP 메타데이터를 decorated 함수에도 복사
        if hasattr(func, "__bloom_method_descriptor__"):
            setattr(
                decorated,
                "__bloom_method_descriptor__",
                getattr(func, "__bloom_method_descriptor__"),
            )

        return decorated  # type: ignore

    @overload
    def __call__(self, func: F) -> F:
        """@RateLimited (인자 없이 직접 함수에 적용)"""
        ...

    @overload
    def __call__(
        self,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> Callable[[F], F]:
        """@RateLimited() 또는 @RateLimited(limit=100)"""
        ...

    def __call__(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Callable[[F], F] | F:
        # Case 1: @RateLimited (인자 없이)
        if (
            len(args) == 1
            and len(kwargs) == 0
            and callable(args[0])
            and not isinstance(args[0], type)
        ):
            func = args[0]
            return self._apply_decorator(func, (), {}, self._order)

        # Case 2: @RateLimited() 또는 @RateLimited(limit=100)
        order = kwargs.pop("order", None)
        actual_order = order if order is not None else self._order

        def decorator(func: F) -> F:
            return self._apply_decorator(func, args, kwargs, actual_order)

        return decorator

    def __repr__(self) -> str:
        return f"<InjectableDecoratorFactory({self._decorator_factory.__name__})>"


def create_injectable_annotation(
    decorator_factory: Callable[P, Callable[[Callable], Callable]],
    *,
    order: int = 0,
    interceptor_type: str | None = None,
) -> InjectableDecoratorFactory[P]:
    """
    DI 주입을 지원하는 어노테이션을 생성하는 헬퍼.

    Usage:
        @Component
        class CacheService:
            def get(self, key: str) -> Any: ...
            def set(self, key: str, value: Any) -> None: ...

        def cached(
            ttl: int = 300,
            *,
            cache: CacheService,  # 자동 주입
        ):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    if cache:
                        # 캐시 로직
                        pass
                    return await func(*args, **kwargs)
                return wrapper
            return decorator

        Cached = create_injectable_annotation(cached, order=-100)
    """
    return InjectableDecoratorFactory(
        decorator_factory,
        order=order,
        interceptor_type=interceptor_type,
    )


# ============================================================
# FlatDecorator - 삼중 중첩 없는 평탄화된 데코레이터
# ============================================================

# 데코레이터 옵션용 ParamSpec
D = ParamSpec("D")
# 타겟 함수용 ParamSpec  
T = ParamSpec("T")
R = TypeVar("R")


class FlatInterceptor(MethodInterceptor):
    """
    FlatDecorator용 인터셉터.
    
    평탄화된 핸들러 함수를 직접 호출.
    """

    def __init__(
        self,
        handler: Callable[..., Any],
        decorator_args: tuple,
        decorator_kwargs: dict,
        order: int = 0,
    ):
        self.handler = handler
        self.decorator_args = decorator_args
        self.decorator_kwargs = decorator_kwargs
        self.order = order

    async def intercept(
        self,
        invocation: MethodInvocation,
        proceed: Callable[[], Any],
    ) -> Any:
        # 핸들러가 동기/비동기인지 확인
        handler_is_async = inspect.iscoroutinefunction(self.handler)

        # proceed를 호출하는 래퍼 함수 (proceed는 항상 async)
        @wraps(invocation.method)
        async def call_next(*args: Any, **kwargs: Any) -> Any:
            invocation.args = args
            invocation.kwargs = kwargs
            return await proceed()

        # 핸들러 호출: handler(func, *args, **kwargs, **decorator_options)
        result = self.handler(
            call_next,
            *invocation.args,
            *self.decorator_args,
            **invocation.kwargs,
            **self.decorator_kwargs,
        )

        if inspect.iscoroutine(result):
            result = await result

        return result


class FlatDecorator(Generic[D]):
    """
    삼중 중첩 없는 평탄화된 데코레이터 팩토리.

    기존 방식 (삼중 중첩):
        def rate_limited(limit: int = 100, *, service: RateLimitService):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    await service.check(limit)
                    return await func(*args, **kwargs)
                return wrapper
            return decorator

    FlatDecorator 방식 (단일 함수):
        def rate_limited(
            func: Callable[P, R],
            *args: P.args,
            limit: int = 100,
            service: RateLimitService,
            **kwargs: P.kwargs,
        ) -> R:
            await service.check(limit)
            return await func(*args, **kwargs)

        RateLimited = FlatDecorator(rate_limited, inject=["service"])

    Usage:
        @RateLimited(limit=50)
        async def api_call(self, data: str) -> str:
            return f"result: {data}"
    """

    def __init__(
        self,
        handler: Callable[..., Any],
        *,
        inject: list[str] | None = None,
        order: int = 0,
        interceptor_type: str | None = None,
    ):
        """
        Args:
            handler: 평탄화된 핸들러 함수 (func, *args, **kwargs, **options) -> result
            inject: DI로 주입받을 파라미터 이름 목록
            order: 인터셉터 실행 순서
            interceptor_type: 인터셉터 타입 ID
        """
        self._handler = handler
        self._inject = inject or []
        self._order = order
        self._interceptor_type = (
            interceptor_type or f"flat_decorator_{id(handler)}"
        )
        self._injectable_params = self._analyze_injectable_params()

        self._register_factory()

    def _analyze_injectable_params(self) -> dict[str, type]:
        """주입 가능한 파라미터 분석"""
        injectable: dict[str, type] = {}

        if not self._inject:
            return injectable

        try:
            sig = inspect.signature(self._handler)
            try:
                hints = get_type_hints(self._handler)
            except Exception:
                hints = getattr(self._handler, "__annotations__", {})

            for param_name in self._inject:
                if param_name not in sig.parameters:
                    continue

                param = sig.parameters[param_name]
                param_type = hints.get(param_name)

                if param_type is None and param.annotation != inspect.Parameter.empty:
                    param_type = param.annotation

                if param_type is None:
                    continue

                # Union 타입 처리 (X | None)
                if type(param_type).__name__ == "UnionType":
                    for arg in getattr(param_type, "__args__", ()):
                        if arg is not type(None):
                            param_type = arg
                            break

                if inspect.isclass(param_type) and param_type.__module__ != "builtins":
                    injectable[param_name] = param_type

        except Exception:
            pass

        return injectable

    def _register_factory(self) -> None:
        """인터셉터 팩토리 등록"""
        registry = get_interceptor_registry()
        handler = self._handler
        injectable_params = self._injectable_params

        @registry.register_factory(self._interceptor_type)
        def factory(info: InterceptorInfo) -> MethodInterceptor:
            return FlatInterceptor(
                handler=handler,
                decorator_args=info.metadata.get("args", ()),
                decorator_kwargs=info.metadata.get("kwargs", {}),
                order=info.order,
            )

    def _apply_decorator(
        self,
        func: F,
        args: tuple,
        kwargs: dict,
        order: int,
    ) -> F:
        """데코레이터 적용"""
        # AOP 메타데이터 등록
        descriptor = ensure_method_descriptor(func)
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type=self._interceptor_type,
                order=order,
                metadata={
                    "args": args,
                    "kwargs": kwargs,
                    "injectable_params": list(self._injectable_params.keys()),
                },
            )
        )

        # 직접 호출용 래퍼 생성
        handler = self._handler
        injectable_params = self._injectable_params
        is_async_func = inspect.iscoroutinefunction(func)
        is_async_handler = inspect.iscoroutinefunction(handler)

        if is_async_func or is_async_handler:
            # 비동기 래퍼
            @wraps(func)
            async def async_wrapper(*call_args: Any, **call_kwargs: Any) -> Any:
                full_kwargs = dict(kwargs)
                for param_name in injectable_params:
                    if param_name not in full_kwargs:
                        full_kwargs[param_name] = None

                result = handler(func, *call_args, *args, **call_kwargs, **full_kwargs)
                if inspect.iscoroutine(result):
                    result = await result
                return result

            # 메타데이터 복사
            if hasattr(func, "__bloom_method_descriptor__"):
                setattr(
                    async_wrapper,
                    "__bloom_method_descriptor__",
                    getattr(func, "__bloom_method_descriptor__"),
                )
            return async_wrapper  # type: ignore
        else:
            # 동기 래퍼
            @wraps(func)
            def sync_wrapper(*call_args: Any, **call_kwargs: Any) -> Any:
                full_kwargs = dict(kwargs)
                for param_name in injectable_params:
                    if param_name not in full_kwargs:
                        full_kwargs[param_name] = None

                return handler(func, *call_args, *args, **call_kwargs, **full_kwargs)

            # 메타데이터 복사
            if hasattr(func, "__bloom_method_descriptor__"):
                setattr(
                    sync_wrapper,
                    "__bloom_method_descriptor__",
                    getattr(func, "__bloom_method_descriptor__"),
                )
            return sync_wrapper  # type: ignore

        return wrapper  # type: ignore

    @overload
    def __call__(self, func: F) -> F:
        """@RateLimited (인자 없이)"""
        ...

    @overload
    def __call__(
        self,
        *args: D.args,
        **kwargs: D.kwargs,
    ) -> Callable[[F], F]:
        """@RateLimited() 또는 @RateLimited(limit=100)"""
        ...

    def __call__(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Callable[[F], F] | F:
        # Case 1: @RateLimited (인자 없이)
        if (
            len(args) == 1
            and len(kwargs) == 0
            and callable(args[0])
            and not isinstance(args[0], type)
        ):
            func = args[0]
            return self._apply_decorator(func, (), {}, self._order)

        # Case 2: @RateLimited() 또는 @RateLimited(limit=100)
        order = kwargs.pop("order", None)
        actual_order = order if order is not None else self._order

        def decorator(func: F) -> F:
            return self._apply_decorator(func, args, kwargs, actual_order)

        return decorator

    def __repr__(self) -> str:
        return f"<FlatDecorator({self._handler.__name__})>"
