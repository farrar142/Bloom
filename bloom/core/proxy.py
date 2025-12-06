from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from .container import Container
    from .manager import ContainerManager


class LazyProxy[T]:
    """
    지연 로딩 프록시.
    실제 인스턴스에 대한 접근을 투명하게 위임.
    """

    __slots__ = ("_lp_container", "_lp_manager", "_lp_instance", "_lp_resolved")

    def __init__(
        self,
        container: "Container[T]",
        manager: "ContainerManager",
    ) -> None:
        self._lp_container = container
        self._lp_manager = manager
        self._lp_instance = None
        self._lp_resolved = False

    def _lp_resolve(self) -> T:
        """
        실제 인스턴스 획득 (지연 로딩).
        """
        if not self._lp_resolved:

            container: "Container[T]" = self._lp_container
            manager: "ContainerManager" = self._lp_manager
            instance = manager.get_instance(container.kls)
            self._lp_instance = instance
            self._lp_resolved = True
        if self._lp_instance is None:
            raise RuntimeError("LazyProxy failed to resolve the target instance.")
        return self._lp_instance

    def _lp_get_target_type(self) -> type[T]:
        """프록시 대상 타입 반환"""
        container: "Container[T]" = self._lp_container
        return container.kls

    # === Transparent Proxy Methods ===

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_lp_"):
            return object.__getattribute__(self, name)

        instance = self._lp_resolve()
        return getattr(instance, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_lp_"):
            object.__setattr__(self, name, value)
        else:
            instance = self._lp_resolve()
            setattr(instance, name, value)

    def __delattr__(self, name: str) -> None:
        instance = self._lp_resolve()
        delattr(instance, name)

    def __repr__(self) -> str:
        container: "Container[T]" = self._lp_container
        resolved = self._lp_resolved
        status = "resolved" if resolved else "pending"
        return f"<LazyProxy[{container.kls.__name__}] {status}>"

    def __str__(self) -> str:
        return str(self._lp_resolve())

    def __bool__(self) -> bool:
        return bool(self._lp_resolve())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, LazyProxy):
            return self._lp_resolve() == other._lp_resolve()
        return self._lp_resolve() == other

    def __hash__(self) -> int:
        return hash(self._lp_resolve())

    # === Container Protocol ===

    def __len__(self) -> int:
        return len(self._lp_resolve())  # type: ignore

    def __iter__(self):
        return iter(self._lp_resolve())  # type: ignore

    def __contains__(self, item: Any) -> bool:
        return item in self._lp_resolve()  # type: ignore

    def __getitem__(self, key: Any) -> Any:
        return self._lp_resolve()[key]  # type: ignore

    def __setitem__(self, key: Any, value: Any) -> None:
        self._lp_resolve()[key] = value  # type: ignore

    def __delitem__(self, key: Any) -> None:
        del self._lp_resolve()[key]  # type: ignore

    # === Callable Protocol ===

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._lp_resolve()(*args, **kwargs)  # type: ignore

    # === Awaitable Protocol ===

    def __await__(self):
        return self._lp_resolve().__await__()  # type: ignore
