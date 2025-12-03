"""DecoratorContainer 클래스 - 메서드를 데코레이션하는 컨테이너"""

from typing import (
    Callable,
    Self,
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from ..manager import ContainerManager

from .callable import CallableContainer
from .element import Element


def _resolve_types(manager: "ContainerManager", types: list[type]) -> list:
    """타입 리스트에서 인스턴스 리스트로 resolve"""
    return [manager.get_instance(t) for t in types]


class DecoratorElement(Element):
    """@Decorator 정보를 저장하는 Element
    
    wrapper와 inject_types를 저장하고, 
    다른 컨테이너(Task, Factory 등)에서 resolved wrapper를 가져올 수 있게 합니다.
    
    여러 @Decorator가 적용될 수 있으므로 allow_multiple=True입니다.
    """
    
    key = "decorator"
    allow_multiple = True  # 여러 @Decorator 허용
    
    def __init__(
        self,
        wrapper: Callable,
        inject_types: list[type] | None = None,
    ):
        super().__init__()
        self.metadata["wrapper"] = wrapper
        self.metadata["inject_types"] = inject_types or []
    
    @property
    def wrapper(self) -> Callable:
        return self.metadata["wrapper"]
    
    @property
    def inject_types(self) -> list[type]:
        return self.metadata.get("inject_types", [])
    
    def apply_wrapper(
        self,
        fn: Callable,
        manager: "ContainerManager | None" = None,
    ) -> Callable:
        """wrapper를 fn에 적용하여 반환
        
        Args:
            fn: 감쌀 원본 함수
            manager: 의존성 주입용 ContainerManager (inject_types가 있을 때 필요)
            
        Returns:
            wrapper가 적용된 함수
        """
        wrapper = self.wrapper
        inject_types = self.inject_types
        
        if not inject_types:
            return wrapper(fn)
        
        if manager is None:
            # manager가 없으면 원본 반환
            return fn
            
        deps = _resolve_types(manager, inject_types)
        return wrapper(fn, *deps)


class DecoratorContainer[**P, R](CallableContainer[P, R]):
    """
    원본 컨테이너나 함수를 데코레이션하는 컨테이너.

    DecoratorContainer는 원본 메서드를 wrapper 함수로 감쌉니다.
    여러 @Decorator가 적용되면 wrapper가 누적되어 감싸집니다.

    @Handler 없이도 독립적으로 동작 가능:
        @Component
        class MyService:
            @Decorator(my_wrapper)
            async def my_method(self):
                pass

    의존성 주입 지원:
        def my_wrapper(fn, logger: Logger, config: Config):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                logger.info("before")
                return await fn(*args, **kwargs)
            return wrapped

        @Decorator(my_wrapper)
        async def my_method(self):
            pass
    """

    @classmethod
    def _get_default_priority(cls) -> int:
        return 20

    def __init__(
        self,
        callable_target: Callable[P, R],
        wrapper: Callable[..., Callable[P, R]],
        inject_types: list[type] | None = None,
    ):
        """
        DecoratorContainer 초기화

        Args:
            callable_target: 데코레이션할 원본 함수/메서드
            wrapper: 원본을 완전히 래핑하는 함수 (의존성 파라미터 포함 가능)
            inject_types: wrapper에 주입할 의존성 타입들
        """
        self._original_target = callable_target
        self._resolved_wrapper: Callable[[Callable[P, R]], Callable[P, R]]
        self.manager: "ContainerManager | None" = None
        inject_types = inject_types or []

        # 의존성이 없으면 바로 wrapper 적용
        if not inject_types:
            super().__init__(wrapper(callable_target))
            self._resolved_wrapper = wrapper
        else:
            # 의존성 있으면 일단 원본으로 초기화 (나중에 _bind_method에서 resolve)
            super().__init__(callable_target)
            # 클로저로 wrapper 캡처
            self._resolved_wrapper = self._create_injectable_wrapper(
                wrapper, inject_types
            )

        # DecoratorElement로 wrapper 정보 저장 (다른 컨테이너에서 사용 가능)
        self.add_element(DecoratorElement(wrapper, inject_types))

    def _create_injectable_wrapper(
        self,
        wrapper: Callable[..., Callable[P, R]],
        inject_types: list[type],
    ) -> Callable[[Callable[P, R]], Callable[P, R]]:
        """의존성 주입이 필요한 wrapper를 lazy resolve하는 wrapper 생성"""
        resolved: list[Callable[[Callable[P, R]], Callable[P, R]] | None] = [None]

        def lazy_wrapper(fn: Callable[P, R]) -> Callable[P, R]:
            if resolved[0] is None:
                deps = _resolve_types(self._get_manager(), inject_types)
                resolved[0] = lambda f: wrapper(f, *deps)
            return resolved[0](fn)

        return lazy_wrapper

    def add_wrapper(
        self,
        wrapper: Callable[..., Callable[P, R]],
        inject_types: list[type] | None = None,
    ) -> None:
        """
        새 wrapper를 기존 callable_target에 감싸서 추가

        Args:
            wrapper: 추가할 wrapper 함수
            inject_types: wrapper에 주입할 의존성 타입들
        """
        inject_types = inject_types or []
        old_resolved_wrapper = self._resolved_wrapper

        if not inject_types:
            # 의존성 없으면 기존 wrapper 위에 바로 적용
            def combined_wrapper(fn: Callable[P, R]) -> Callable[P, R]:
                return wrapper(old_resolved_wrapper(fn))

            self._resolved_wrapper = combined_wrapper
        else:
            # 의존성 있으면 lazy resolve
            def combined_wrapper(fn: Callable[P, R]) -> Callable[P, R]:
                deps = _resolve_types(self._get_manager(), inject_types)
                return wrapper(old_resolved_wrapper(fn), *deps)

            self._resolved_wrapper = combined_wrapper

        # 새 wrapper도 DecoratorElement로 저장 (다른 컨테이너에서 사용 가능)
        self.add_element(DecoratorElement(wrapper, inject_types))
        
        self._bound_method = None  # 캐시 무효화

    def _bind_method(self) -> Callable[P, R]:
        """owner 인스턴스에 바인딩된 메서드 반환 (wrapper 적용)"""
        if self._bound_method is not None:
            return self._bound_method

        self._bound_method = self._create_bound_method(
            self._original_target, self._resolved_wrapper
        )
        return self._bound_method

    @classmethod
    def get_or_create(
        cls,
        method: Callable[P, R],
        wrapper: Callable[..., Callable[P, R]],
        inject_types: list[type] | None = None,
    ) -> Self:
        """
        DecoratorContainer 생성 또는 기존에 wrapper 추가

        같은 함수에 @decorator가 여러번 적용되면 wrapper를 누적합니다.
        """
        existing = getattr(method, "__container__", None)

        if isinstance(existing, cls):
            # 같은 타입이면 wrapper만 추가
            existing.add_wrapper(wrapper, inject_types)
            return existing

        # 새로 생성하거나 오버라이드
        return cls._apply_override_rules(
            method, lambda: cls(method, wrapper, inject_types)
        )

    def invoke_sync(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """동기 호출 (테스트용, owner 바인딩 없음)"""
        return self.callable_target(*args, **kwargs)
