"""bloom.core.proxy - Lazy Proxy & Method Proxy"""

from __future__ import annotations

import asyncio
from functools import wraps
from typing import Any, Callable, Generic, TypeVar, TYPE_CHECKING, cast, overload

from .scope import ScopeEnum

if TYPE_CHECKING:
    from .container import Container
    from .manager import ContainerManager


T = TypeVar("T")


class LazyProxy(Generic[T]):
    """
    지연 로딩 프록시.
    실제 인스턴스에 대한 접근을 투명하게 위임.

    사용 예:
        @Component
        class UserService:
            repo: UserRepository  # LazyProxy[UserRepository]로 주입됨

            def get_user(self):
                # repo 접근 시점에 실제 인스턴스 resolve
                return self.repo.find(1)

    순환 의존성 해결:
        @Component
        class ServiceA:
            b: ServiceB  # LazyProxy로 주입 - 접근 시점에 resolve

        @Component
        class ServiceB:
            a: ServiceA  # LazyProxy로 주입 - 접근 시점에 resolve

        # A, B 모두 생성 완료 후 접근 시 상호 참조 가능

    스코프별 동작:
        - SINGLETON: 한 번 resolve 후 캐싱
        - REQUEST: 요청마다 다시 resolve (캐싱 안 함)
        - CALL: Handler 호출마다 다시 resolve (캐싱 안 함)
    """

    __slots__ = ("_lp_container", "_lp_manager", "_lp_instance", "_lp_resolved")

    def __init__(
        self,
        container: "Container[T]",
        manager: "ContainerManager",
    ) -> None:
        object.__setattr__(self, "_lp_container", container)
        object.__setattr__(self, "_lp_manager", manager)
        object.__setattr__(self, "_lp_instance", None)
        object.__setattr__(self, "_lp_resolved", False)

    def _lp_resolve(self) -> T:
        """
        실제 인스턴스 획득 (지연 로딩).

        ScopeManager에 캐시된 인스턴스를 먼저 확인하여
        순환 의존성 상황에서도 안전하게 동작.

        스코프별 동작:
        - SINGLETON: 한 번만 resolve하고 프록시 내부에 캐싱
        - REQUEST/CALL: 매번 ScopeManager에서 현재 컨텍스트의 인스턴스 조회
        """
        import asyncio

        container: Container[T] = object.__getattribute__(self, "_lp_container")
        manager: ContainerManager = object.__getattribute__(self, "_lp_manager")

        # SINGLETON이 아닌 스코프는 매번 ScopeManager에서 조회
        # (REQUEST나 CALL 스코프는 컨텍스트마다 다른 인스턴스가 필요)
        if container.scope != ScopeEnum.SINGLETON:
            # 현재 컨텍스트에서 인스턴스 조회
            cached = manager.scope_manager.get_instance(
                container.target, container.scope
            )
            if cached is not None:
                return cached

            # 캐시에 없으면 새로 생성 (get_instance가 처리)
            return manager.get_instance(container.target)

        # SINGLETON: 한 번만 resolve하고 캐싱
        if not object.__getattribute__(self, "_lp_resolved"):
            # 먼저 ScopeManager에서 캐시된 인스턴스 확인
            cached = manager.scope_manager.get_instance(
                container.target, container.scope
            )
            if cached is not None:
                object.__setattr__(self, "_lp_instance", cached)
                object.__setattr__(self, "_lp_resolved", True)
                return cached

            # 캐시에 없으면 get_instance 호출
            # async 컨텍스트에서는 동기 get_instance가 실패할 수 있음
            try:
                asyncio.get_running_loop()
                # async 컨텍스트: 동기적으로 인스턴스 생성 시도
                # Container에서 직접 동기 생성 (의존성 없는 경우만)
                raise RuntimeError(
                    f"LazyProxy for {container.target.__name__} accessed in async context "
                    f"before initialization. Call ready_async() first."
                )
            except RuntimeError as e:
                if "no running event loop" in str(e):
                    # 이벤트 루프 없음: 동기적으로 처리
                    instance = manager.get_instance(container.target)
                    object.__setattr__(self, "_lp_instance", instance)
                    object.__setattr__(self, "_lp_resolved", True)
                else:
                    raise

        return object.__getattribute__(self, "_lp_instance")

    def _lp_get_target_type(self) -> type[T]:
        """프록시 대상 타입 반환"""
        container: Container[T] = object.__getattribute__(self, "_lp_container")
        return container.target

    # === Transparent Proxy Methods ===

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_lp_"):
            return object.__getattribute__(self, name)

        # CALL 스코프 컴포넌트는 Handler 컨텍스트 외부에서 접근 불가
        # hasattr() 등의 호출에서 에러 대신 AttributeError를 발생시켜
        # 해당 속성이 없는 것처럼 동작하게 함
        from .scope import ScopeEnum
        from .scope_manager import _frame_id_stack

        container: Container[T] = object.__getattribute__(self, "_lp_container")
        if container.scope == ScopeEnum.CALL:
            resolved = object.__getattribute__(self, "_lp_resolved")
            if not resolved:
                # CALL 스코프이고 아직 resolve되지 않은 경우
                # Handler 컨텍스트에서만 접근 가능
                stack = _frame_id_stack.get()
                if not stack or len(stack) == 0:
                    # Handler 컨텍스트 외부: 속성이 없는 것처럼 동작
                    raise AttributeError(
                        f"'{container.target.__name__}' is a CALL scoped component "
                        f"and cannot be accessed outside of @Handler context"
                    )

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
        container: Container[T] = object.__getattribute__(self, "_lp_container")
        resolved = object.__getattribute__(self, "_lp_resolved")
        status = "resolved" if resolved else "pending"
        return f"<LazyProxy[{container.target.__name__}] {status}>"

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


# === Method Proxy ===


class MethodProxy(Generic[T]):
    """
    메서드 프록시 - 컴포넌트의 모든 메서드를 감싸서 부가 기능 제공.
    - 콜스택 추적 (CALL 스코프용)
    - AOP 지원 (before/after/around)
    """

    __slots__ = ("_mp_instance", "_mp_method", "_mp_name", "_mp_hooks")

    def __init__(
        self,
        instance: T,
        method: Callable[..., Any],
        name: str,
        hooks: "MethodHooks | None" = None,
    ) -> None:
        object.__setattr__(self, "_mp_instance", instance)
        object.__setattr__(self, "_mp_method", method)
        object.__setattr__(self, "_mp_name", name)
        object.__setattr__(self, "_mp_hooks", hooks)

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        method: Callable[..., Any] = object.__getattribute__(self, "_mp_method")
        hooks: MethodHooks | None = object.__getattribute__(self, "_mp_hooks")
        name: str = object.__getattribute__(self, "_mp_name")

        # Before hook
        if hooks and hooks.before:
            await _maybe_await(hooks.before(name, args, kwargs))

        try:
            # 실제 메서드 호출
            result = method(*args, **kwargs)
            if asyncio.iscoroutine(result):
                result = await result

            # After hook
            if hooks and hooks.after:
                await _maybe_await(hooks.after(name, result))

            return result

        except Exception as e:
            # Error hook
            if hooks and hooks.on_error:
                await _maybe_await(hooks.on_error(name, e))
            raise

    def __repr__(self) -> str:
        name: str = object.__getattribute__(self, "_mp_name")
        return f"<MethodProxy {name}>"


class MethodHooks:
    """메서드 프록시 훅 정의"""

    def __init__(
        self,
        before: Callable[[str, tuple, dict], Any] | None = None,
        after: Callable[[str, Any], Any] | None = None,
        on_error: Callable[[str, Exception], Any] | None = None,
    ) -> None:
        self.before = before
        self.after = after
        self.on_error = on_error


async def _maybe_await[T](value: T | asyncio.Future[T]) -> T:
    """코루틴이면 await, 아니면 그대로 반환"""
    if asyncio.iscoroutine(value):
        return await value  # type: ignore
    return value  # type: ignore


def create_proxied_instance[T](
    instance: T,
    hooks: MethodHooks | None = None,
) -> T:
    """
    인스턴스의 모든 public 메서드를 프록시로 감싼 새 객체 반환.
    원본 인스턴스를 수정하지 않음.
    """
    if hooks is None:
        return instance

    class ProxiedInstance:
        """프록시된 인스턴스 래퍼"""

        def __init__(self, original: T, hooks: MethodHooks) -> None:
            self._original = original
            self._hooks = hooks

        def __getattr__(self, name: str) -> Any:
            attr = getattr(self._original, name)
            if callable(attr) and not name.startswith("_"):
                return MethodProxy(self._original, attr, name, self._hooks)
            return attr

        def __repr__(self) -> str:
            return f"<Proxied {self._original!r}>"

    return cast(T, ProxiedInstance(instance, hooks))
