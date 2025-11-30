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

if TYPE_CHECKING:
    from .lifecycle import LifecycleHandlerContainer
    from .container import Container


# =============================================================================
# LazyFieldProxy: 필드 주입용 투명 프록시
# =============================================================================


class LazyFieldProxy[T]:
    """필드 주입용 투명 프록시

    모든 필드 주입은 기본적으로 이 프록시로 래핑됩니다.
    접근 시점에 실제 인스턴스를 해결하며, Scope에 따라 동작이 다릅니다:
    - SINGLETON: 최초 접근 시 한 번만 resolve (캐시)
    - PROTOTYPE: 매 접근마다 새 인스턴스 생성 (Spring과 동일하게 PreDestroy 미호출)
    - REQUEST: HTTP 요청 컨텍스트마다 새 인스턴스

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
        "_lfp_container",
    )

    def __init__(
        self,
        resolver: Callable[[], T],
        target_type: type[T] | None = None,
        scope: Scope = Scope.SINGLETON,
        container: Any = None,
    ):
        object.__setattr__(self, "_lfp_resolver", resolver)
        object.__setattr__(self, "_lfp_instance", None)
        object.__setattr__(self, "_lfp_resolved", False)
        object.__setattr__(self, "_lfp_target_type", target_type)
        object.__setattr__(self, "_lfp_scope", scope)
        object.__setattr__(self, "_lfp_container", container)

    def _lfp_resolve(self) -> T:
        """실제 인스턴스를 해결합니다. Scope에 따라 동작이 다릅니다."""
        scope = object.__getattribute__(self, "_lfp_scope")

        # PROTOTYPE: 매번 새 인스턴스 생성
        # 콜스택 내에서 생성되면 메서드 종료 시 자동으로 @PreDestroy 호출
        if scope == Scope.PROTOTYPE:
            resolver = object.__getattribute__(self, "_lfp_resolver")
            container = object.__getattribute__(self, "_lfp_container")
            instance = resolver()

            # PROTOTYPE @PostConstruct 호출 - LifecycleManager 위임
            if container is not None:
                manager = container._get_manager()
                if manager is not None:
                    manager.lifecycle.invoke_prototype_post_construct(
                        instance, container
                    )
                    # InstanceCreatedEvent 발행
                    self._lfp_publish_instance_created(manager, instance, scope)

                # 콜스택에 등록 (메서드 종료 시 자동 정리)
                from .advice.tracing import register_prototype

                register_prototype(instance, container)

            return instance

        # REQUEST: 요청별 캐시 사용
        if scope == Scope.REQUEST:
            from .request_context import RequestContext

            container = object.__getattribute__(self, "_lfp_container")
            target_type = object.__getattribute__(self, "_lfp_target_type")

            # 컨텍스트 활성화 확인
            if not RequestContext.is_active():
                raise RuntimeError(
                    f"REQUEST scope requires active request context. "
                    f"Ensure RequestScopeMiddleware is enabled. "
                    f"Type: {target_type.__name__ if target_type else 'unknown'}"
                )

            # 현재 요청에 캐시된 인스턴스 확인
            cached = RequestContext.get_instance(target_type)
            if cached is not None:
                return cached

            # 새 인스턴스 생성
            resolver = object.__getattribute__(self, "_lfp_resolver")
            instance = resolver()

            # 요청 컨텍스트에 저장
            if container is not None:
                RequestContext.set_instance(target_type, instance, container)

                # @PostConstruct 호출
                manager = container._get_manager()
                if manager is not None:
                    manager.lifecycle.invoke_request_post_construct(instance, container)
                    # InstanceCreatedEvent 발행 (REQUEST 추적 가능)
                    self._lfp_publish_instance_created(manager, instance, scope)

            return instance

        # SINGLETON (기본값): 캐시 사용
        if not object.__getattribute__(self, "_lfp_resolved"):
            resolver = object.__getattribute__(self, "_lfp_resolver")
            instance = resolver()
            object.__setattr__(self, "_lfp_instance", instance)
            object.__setattr__(self, "_lfp_resolved", True)
        return object.__getattribute__(self, "_lfp_instance")

    def _lfp_publish_instance_created(
        self, manager: Any, instance: Any, scope: Scope
    ) -> None:
        """InstanceCreatedEvent 발행 (PROTOTYPE/REQUEST 추적용)"""
        from .events import InstanceCreatedEvent

        target_type = object.__getattribute__(self, "_lfp_target_type")
        event = InstanceCreatedEvent(
            instance=instance,
            instance_type=target_type,
            scope=scope,
        )
        manager.system_events.publish(event)

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
