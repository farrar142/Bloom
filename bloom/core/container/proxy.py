from typing import TYPE_CHECKING, Any, Generic, TypeVar, Coroutine


if TYPE_CHECKING:
    from . import Container
    from .manager import ContainerRegistry
    from .factory import FactoryContainer
    from .scope import Scope, ScopeContext

T = TypeVar("T")


class LazyProxy(Generic[T]):
    """
    지연 로딩 프록시.
    실제 인스턴스에 대한 접근을 투명하게 위임.
    """

    __slots__ = ("_lp_container", "_lp_registry", "_lp_instance", "_lp_resolved")

    def __init__(
        self,
        container: "Container[T]",
        registry: "ContainerRegistry",
    ) -> None:
        self._lp_container = container
        self._lp_registry = registry
        self._lp_instance: T | None = None
        self._lp_resolved = False

    def _lp_resolve(self) -> T:
        """
        실제 인스턴스 획득 (지연 로딩).
        """
        if not self._lp_resolved:

            container: "Container[T]" = self._lp_container
            registry: "ContainerRegistry" = self._lp_registry
            instance = registry.instance(type=container.kls)
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


class AsyncProxy(Generic[T]):
    """
    비동기 프록시 - AsyncAutoCloseable용.

    투명 프록시가 아니며, await proxy.resolve()로 명시적으로 인스턴스를 생성해야 함.
    스코프 종료 시 자동으로 __aexit__ 호출.

    Usage:
        class MyComponent:
            session: AsyncProxy[AsyncSession]

            async def my_method(self):
                session = await self.session.resolve()
                # session 사용...
                # 스코프 종료 시 자동으로 __aexit__ 호출
    """

    __slots__ = (
        "_ap_factory_container",
        "_ap_manager",
        "_ap_scope",
        "_ap_instance",
        "_ap_resolved",
    )

    def __init__(
        self,
        factory_container: "FactoryContainer",
        manager: "ContainerManager",
        scope: "Scope",
    ) -> None:
        self._ap_factory_container = factory_container
        self._ap_manager = manager
        self._ap_scope = scope
        self._ap_instance: T | None = None
        self._ap_resolved = False

    async def resolve(self) -> T:
        """
        실제 인스턴스 획득 (비동기).

        스코프에 따라:
        - SINGLETON: 항상 같은 인스턴스
        - CALL: 스코프 내 같은 인스턴스, 스코프 종료 시 close
        - REQUEST: 요청 내 같은 인스턴스
        - Transactional 범위 내: 같은 인스턴스 공유
        """
        from .scope import Scope, get_scope_context
        from ..abstract.autocloseable import AsyncAutoCloseable

        factory: "FactoryContainer" = self._ap_factory_container
        manager: "ContainerManager" = self._ap_manager
        scope: Scope = self._ap_scope

        # SINGLETON은 매니저에서 관리
        if scope == Scope.SINGLETON:
            return await manager.factory(factory.return_type)  # type: ignore

        # 스코프 컨텍스트에서 기존 인스턴스 확인
        scope_context = get_scope_context(scope)
        if scope_context is not None:
            existing = scope_context.get(factory.component_id)
            if existing is not None:
                return existing  # type: ignore

        # 새 인스턴스 생성
        config = manager.configuration_for(factory.return_type)
        if config is None:
            raise RuntimeError(
                f"No Configuration found for Factory type: {factory.return_type}"
            )

        instance = await config.create_factory(factory.return_type)

        # AsyncAutoCloseable이면 __aenter__ 호출
        if isinstance(instance, AsyncAutoCloseable):
            instance = await instance.__aenter__()

        # 스코프 컨텍스트에 저장
        if scope_context is not None:
            scope_context.set(factory.component_id, instance)
            if isinstance(instance, AsyncAutoCloseable):
                scope_context.register_closeable(instance)

        return instance  # type: ignore

    def _ap_get_target_type(self) -> type[T]:
        """프록시 대상 타입 반환"""
        factory: "FactoryContainer" = self._ap_factory_container
        return factory.return_type  # type: ignore

    def __repr__(self) -> str:
        factory: "FactoryContainer" = self._ap_factory_container
        scope: "Scope" = self._ap_scope
        return f"<AsyncProxy[{factory.return_type.__name__}] scope={scope.value}>"


class ScopedProxy(Generic[T]):
    """
    스코프 기반 프록시 - AutoCloseable용 (sync).

    투명 프록시로 동작하며, 접근 시 자동으로 인스턴스 생성.
    스코프 종료 시 자동으로 __exit__ 호출.

    Usage:
        class MyComponent:
            session: Session  # ScopedProxy로 주입됨

            def my_method(self):
                self.session.query(...)  # 자동으로 인스턴스 생성 및 __enter__ 호출
                # 스코프 종료 시 자동으로 __exit__ 호출
    """

    __slots__ = (
        "_sp_factory_container",
        "_sp_manager",
        "_sp_scope",
    )

    def __init__(
        self,
        factory_container: "FactoryContainer",
        manager: "ContainerManager",
        scope: "Scope",
    ) -> None:
        self._sp_factory_container = factory_container
        self._sp_manager = manager
        self._sp_scope = scope

    def _sp_resolve(self) -> T:
        """
        실제 인스턴스 획득 (sync).

        스코프에 따라:
        - SINGLETON: 항상 같은 인스턴스
        - CALL: 스코프 내 같은 인스턴스, 스코프 종료 시 close
        - REQUEST: 요청 내 같은 인스턴스
        - Transactional 범위 내: 같은 인스턴스 공유
        """
        from .scope import Scope, get_scope_context
        from ..abstract.autocloseable import AutoCloseable
        import asyncio

        factory: "FactoryContainer" = self._sp_factory_container
        manager: "ContainerManager" = self._sp_manager
        scope: "Scope" = self._sp_scope

        # SINGLETON은 매니저에서 관리
        if scope == Scope.SINGLETON:
            # sync context에서는 캐시된 것만 반환
            for config in manager._configurations():
                cached = config.get_cached_factory(factory.return_type)
                if cached is not None:
                    return cached  # type: ignore
            raise RuntimeError(
                f"SINGLETON Factory '{factory.return_type}' not initialized. "
                "Use async context or initialize during startup."
            )

        # 스코프 컨텍스트에서 기존 인스턴스 확인
        scope_context = get_scope_context(scope)
        if scope_context is not None:
            existing = scope_context.get(factory.component_id)
            if existing is not None:
                return existing  # type: ignore

        # 새 인스턴스 생성 (sync factory만 지원)
        config = manager.configuration_for(factory.return_type)
        if config is None:
            raise RuntimeError(
                f"No Configuration found for Factory type: {factory.return_type}"
            )

        if factory.is_async:
            raise RuntimeError(
                f"Cannot resolve async Factory '{factory.return_type}' in sync context. "
                "Use AsyncProxy instead."
            )

        # sync factory 호출
        instance = config._create_factory_sync(factory.return_type)

        # AutoCloseable이면 __enter__ 호출
        if isinstance(instance, AutoCloseable):
            instance = instance.__enter__()

        # 스코프 컨텍스트에 저장
        if scope_context is not None:
            scope_context.set(factory.component_id, instance)
            if isinstance(instance, AutoCloseable):
                scope_context.register_closeable(instance)

        return instance  # type: ignore

    def _sp_get_target_type(self) -> type[T]:
        """프록시 대상 타입 반환"""
        factory: "FactoryContainer" = self._sp_factory_container
        return factory.return_type  # type: ignore

    # === Transparent Proxy Methods ===

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_sp_"):
            return object.__getattribute__(self, name)

        instance = self._sp_resolve()
        return getattr(instance, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_sp_"):
            object.__setattr__(self, name, value)
        else:
            instance = self._sp_resolve()
            setattr(instance, name, value)

    def __delattr__(self, name: str) -> None:
        instance = self._sp_resolve()
        delattr(instance, name)

    def __repr__(self) -> str:
        factory: "FactoryContainer" = self._sp_factory_container
        scope: "Scope" = self._sp_scope
        return f"<ScopedProxy[{factory.return_type.__name__}] scope={scope.value}>"

    def __str__(self) -> str:
        return str(self._sp_resolve())

    def __bool__(self) -> bool:
        return bool(self._sp_resolve())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ScopedProxy):
            return self._sp_resolve() == other._sp_resolve()
        return self._sp_resolve() == other

    def __hash__(self) -> int:
        return hash(self._sp_resolve())

    # === Container Protocol ===

    def __len__(self) -> int:
        return len(self._sp_resolve())  # type: ignore

    def __iter__(self):
        return iter(self._sp_resolve())  # type: ignore

    def __contains__(self, item: Any) -> bool:
        return item in self._sp_resolve()  # type: ignore

    def __getitem__(self, key: Any) -> Any:
        return self._sp_resolve()[key]  # type: ignore

    def __setitem__(self, key: Any, value: Any) -> None:
        self._sp_resolve()[key] = value  # type: ignore

    def __delitem__(self, key: Any) -> None:
        del self._sp_resolve()[key]  # type: ignore

    # === Callable Protocol ===

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._sp_resolve()(*args, **kwargs)  # type: ignore
