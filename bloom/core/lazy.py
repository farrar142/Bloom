"""@Lazy 데코레이터와 LazyProxy 구현

@Lazy 데코레이터는 컴포넌트의 인스턴스 생성을 실제 사용 시점까지 지연시킵니다.
순환 의존성 해결에 유용합니다.

사용법:
    @Component
    @Lazy
    class HeavyService:
        pass

    @Component
    class Consumer:
        heavy: HeavyService  # LazyProxy가 주입됨, 실제 접근 시 초기화
"""

from typing import Any, TYPE_CHECKING

from .container import Element, Container

if TYPE_CHECKING:
    from .manager import ContainerManager


class LazyElement(Element):
    """컴포넌트가 @Lazy로 마킹되었음을 나타내는 Element"""

    pass


class LazyProxy:
    """지연 초기화 프록시

    실제 인스턴스에 대한 접근을 가로채서 필요할 때 초기화합니다.
    ContainerManager를 통해 인스턴스를 해결합니다.
    """

    __slots__ = ("_lp_container", "_lp_qualifier", "_lp_instance")

    def __init__(self, container: Container, qualifier: str = "default"):
        object.__setattr__(self, "_lp_container", container)
        object.__setattr__(self, "_lp_qualifier", qualifier)
        object.__setattr__(self, "_lp_instance", None)

    def _resolve(self) -> Any:
        """실제 인스턴스를 해결"""
        instance = object.__getattribute__(self, "_lp_instance")
        if instance is not None:
            return instance

        container: Container = object.__getattribute__(self, "_lp_container")
        qualifier: str = object.__getattribute__(self, "_lp_qualifier")

        if not container.manager:
            raise RuntimeError("LazyProxy requires ContainerManager")

        manager: "ContainerManager" = container.manager

        # 이미 생성된 인스턴스가 있는지 확인
        instance = manager.get_instance(
            container.target, raise_exception=False, qualifier=qualifier
        )
        if instance is None:
            # 없으면 새로 생성하고 등록 (_create_instance가 의존성 주입도 처리함)
            instance = container._create_instance()
            manager.set_instance(container.target, instance, qualifier)
            # 라이프사이클 호출
            manager.lifecycle.invoke_post_construct(container, instance)

        object.__setattr__(self, "_lp_instance", instance)
        return instance

    def __getattr__(self, name: str) -> Any:
        return getattr(self._resolve(), name)

    def __setattr__(self, name: str, value: Any) -> Any:
        setattr(self._resolve(), name, value)

    def __delattr__(self, name: str) -> None:
        delattr(self._resolve(), name)

    def __repr__(self) -> str:
        instance = object.__getattribute__(self, "_lp_instance")
        container: Container = object.__getattribute__(self, "_lp_container")
        if instance is not None:
            return repr(instance)
        return f"<LazyProxy for {container.target.__name__} (unresolved)>"

    def __str__(self) -> str:
        return str(self._resolve())

    def __eq__(self, other: Any) -> bool:
        return self._resolve() == other

    def __hash__(self) -> int:
        return hash(self._resolve())

    def __bool__(self) -> bool:
        return bool(self._resolve())

    def __len__(self) -> int:
        return len(self._resolve())

    def __iter__(self):
        return iter(self._resolve())

    def __contains__(self, item: Any) -> bool:
        return item in self._resolve()

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._resolve()(*args, **kwargs)

    # 비교 연산자들
    def __lt__(self, other: Any) -> bool:
        return self._resolve() < other

    def __le__(self, other: Any) -> bool:
        return self._resolve() <= other

    def __gt__(self, other: Any) -> bool:
        return self._resolve() > other

    def __ge__(self, other: Any) -> bool:
        return self._resolve() >= other

    # 산술 연산자들 (필요시 추가)
    def __add__(self, other: Any) -> Any:
        return self._resolve() + other

    def __radd__(self, other: Any) -> Any:
        return other + self._resolve()

    def __sub__(self, other: Any) -> Any:
        return self._resolve() - other

    def __rsub__(self, other: Any) -> Any:
        return other - self._resolve()

    def __mul__(self, other: Any) -> Any:
        return self._resolve() * other

    def __rmul__(self, other: Any) -> Any:
        return other * self._resolve()

    # 인덱싱/슬라이싱
    def __getitem__(self, key: Any) -> Any:
        return self._resolve()[key]

    def __setitem__(self, key: Any, value: Any) -> None:
        self._resolve()[key] = value

    def __delitem__(self, key: Any) -> None:
        del self._resolve()[key]


def Lazy[T](cls: type[T]) -> type[T]:
    """@Lazy 데코레이터

    컴포넌트의 인스턴스 생성을 실제 사용 시점까지 지연시킵니다.
    순환 의존성 해결에 유용합니다.

    사용법:
        @Component
        @Lazy
        class HeavyService:
            pass
    """
    from .container import ComponentContainer

    container = ComponentContainer.get_or_create(cls)
    container.add_element(LazyElement())
    return cls


def is_lazy_component(target: type | Container) -> bool:
    """대상 타입이 @Lazy로 마킹되었는지 확인"""
    if isinstance(target, Container):
        container = target
    else:
        container = Container.get_container(target)

    if container:
        return container.has_element(LazyElement)
    return False
