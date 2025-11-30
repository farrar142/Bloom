"""Lazy[T] 필드 타입과 LazyFieldProxy 투명 프록시 구현

모든 필드 주입은 기본적으로 LazyFieldProxy로 래핑되어 지연 초기화됩니다.
Lazy[T] 타입을 명시적으로 사용하면 순환 의존성 해결에 유용합니다.

사용법:
    @Component
    class Consumer:
        service: HeavyService  # 자동으로 LazyFieldProxy로 주입됨

        # 또는 명시적으로 Lazy[T] 사용
        heavy: Lazy[HeavyService]

        def use(self):
            # .get() 불필요! 직접 사용 가능 (투명 프록시)
            self.service.do_something()
            self.heavy.do_something()
"""

from typing import Annotated, Any, Callable, TYPE_CHECKING, get_origin, get_args

from .container.element import Scope


# =============================================================================
# LazyFieldProxy: 필드 주입용 투명 프록시
# =============================================================================


class LazyFieldProxy[T]:
    """필드 주입용 투명 프록시

    모든 필드 주입은 기본적으로 이 프록시로 래핑됩니다.
    접근 시점에 실제 인스턴스를 해결하며, Scope에 따라 동작이 다릅니다:
    - SINGLETON: 최초 접근 시 한 번만 resolve (캐시)
    - PROTOTYPE: 매 접근마다 새 인스턴스 생성
    - REQUEST: HTTP 요청 컨텍스트마다 새 인스턴스 (TODO)

    사용법:
        @Component
        class MyService:
            dep: HeavyDependency  # LazyFieldProxy 자동 주입

            def use(self):
                # .get() 불필요! 직접 사용 (투명 프록시)
                self.dep.do_something()
    """

    __slots__ = (
        "_lfp_resolver",
        "_lfp_instance",
        "_lfp_resolved",
        "_lfp_target_type",
        "_lfp_scope",
    )

    def __init__(
        self,
        resolver: Callable[[], T],
        target_type: type[T] | None = None,
        scope: Scope = Scope.SINGLETON,
    ):
        object.__setattr__(self, "_lfp_resolver", resolver)
        object.__setattr__(self, "_lfp_instance", None)
        object.__setattr__(self, "_lfp_resolved", False)
        object.__setattr__(self, "_lfp_target_type", target_type)
        object.__setattr__(self, "_lfp_scope", scope)

    def _lfp_resolve(self) -> T:
        """실제 인스턴스를 해결합니다. Scope에 따라 동작이 다릅니다."""
        scope = object.__getattribute__(self, "_lfp_scope")

        # PROTOTYPE: 매번 새 인스턴스 생성
        if scope == Scope.PROTOTYPE:
            resolver = object.__getattribute__(self, "_lfp_resolver")
            return resolver()

        # SINGLETON (기본값): 캐시 사용
        if not object.__getattribute__(self, "_lfp_resolved"):
            resolver = object.__getattribute__(self, "_lfp_resolver")
            instance = resolver()
            object.__setattr__(self, "_lfp_instance", instance)
            object.__setattr__(self, "_lfp_resolved", True)
        return object.__getattribute__(self, "_lfp_instance")

    def __getattr__(self, name: str) -> Any:
        instance = self._lfp_resolve()
        return getattr(instance, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_lfp_"):
            object.__setattr__(self, name, value)
        else:
            instance = self._lfp_resolve()
            setattr(instance, name, value)

    def __delattr__(self, name: str) -> None:
        instance = self._lfp_resolve()
        delattr(instance, name)

    def __repr__(self) -> str:
        if object.__getattribute__(self, "_lfp_resolved"):
            instance = object.__getattribute__(self, "_lfp_instance")
            return repr(instance)
        target_type = object.__getattribute__(self, "_lfp_target_type")
        type_name = target_type.__name__ if target_type else "?"
        return f"<LazyFieldProxy[{type_name}] unresolved>"

    def __str__(self) -> str:
        instance = self._lfp_resolve()
        return str(instance)

    def __bool__(self) -> bool:
        instance = self._lfp_resolve()
        return bool(instance)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        instance = self._lfp_resolve()
        return instance(*args, **kwargs)  # type:ignore

    def __iter__(self) -> Any:
        instance = self._lfp_resolve()
        return iter(instance)  # type:ignore

    def __len__(self) -> int:
        instance = self._lfp_resolve()
        return len(instance)  # type:ignore

    def __getitem__(self, key: Any) -> Any:
        instance = self._lfp_resolve()
        return instance[key]  # type:ignore

    def __setitem__(self, key: Any, value: Any) -> None:
        instance = self._lfp_resolve()
        instance[key] = value  # type:ignore

    def __eq__(self, other: Any) -> bool:
        instance = self._lfp_resolve()
        return instance == other

    def __hash__(self) -> int:
        instance = self._lfp_resolve()
        return hash(instance)

    # 편의 메서드 (명시적 접근용)
    def get(self) -> T:
        """명시적으로 실제 인스턴스를 가져옵니다. (선택적 사용)"""
        return self._lfp_resolve()

    @property
    def resolved(self) -> bool:
        """인스턴스가 이미 해결되었는지 확인합니다."""
        return object.__getattribute__(self, "_lfp_resolved")


# =============================================================================
# Lazy[T] 타입 별칭
# =============================================================================


def is_lazy_wrapper_type(type_hint: Any) -> bool:
    """타입 힌트가 Lazy[T] 형태인지 확인"""
    origin = get_origin(type_hint)
    return origin is LazyFieldProxy


def get_lazy_inner_type(type_hint: Any) -> type | None:
    """Lazy[T]에서 T 타입을 추출"""
    if not is_lazy_wrapper_type(type_hint):
        return None
    args = get_args(type_hint)
    if args:
        return args[0]
    return None


# Lazy[T] 타입 별칭 - LazyFieldProxy 사용 (투명 프록시)
if TYPE_CHECKING:
    type Lazy[T] = Annotated[T, Lazy[LazyFieldProxy[T]]]
else:
    Lazy = LazyFieldProxy
