"""필드 의존성 주입 유틸리티"""

from typing import Any, ForwardRef, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.manager import ContainerManager
    from ..core.container.base import Container
    from ..core.container.factory import FactoryContainer


class FieldInjector:
    """
    클래스 필드에 의존성을 주입하는 클래스

    LazyFieldProxy를 사용하여 지연 로딩을 지원하며,
    Env 타입, Lazy[T] 명시적 선언, Scope별 처리 등을 담당합니다.

    사용 예:
        injector = FieldInjector(manager)
        kwargs = injector.inject(annotations)
        instance.__dict__.update(kwargs)
    """

    def __init__(self, manager: "ContainerManager"):
        self.manager = manager

    def inject(self, annotations: dict[str, type]) -> dict[str, Any]:
        """
        어노테이션 기반으로 의존성을 주입하여 kwargs 반환

        Args:
            annotations: 클래스의 타입 어노테이션 딕셔너리

        Returns:
            필드명 -> 주입된 값(또는 LazyFieldProxy) 매핑
        """
        from ..core.lazy import (
            LazyFieldProxy,
            is_lazy_wrapper_type,
            get_lazy_inner_type,
        )
        from ..config.env import is_env_type, resolve_env_value

        kwargs: dict[str, Any] = {}

        for name, dep_type in annotations.items():
            if name == "return":
                continue

            # 환경변수 타입 처리 (Env[Literal["KEY"]])
            if is_env_type(dep_type):
                env_value = resolve_env_value(dep_type)
                if env_value is not None:
                    kwargs[name] = env_value
                continue

            # Lazy[T] 필드 타입 처리 - 명시적 Lazy 선언
            if is_lazy_wrapper_type(dep_type):
                result = self._inject_explicit_lazy(name, dep_type)
                if result is not None:
                    kwargs[name] = result
                continue

            # 일반 타입 처리 (기본 Lazy 동작)
            result = self._inject_default_lazy(name, dep_type)
            if result is not None:
                kwargs[name] = result

        return kwargs

    def _inject_explicit_lazy(self, name: str, dep_type: type) -> Any | None:
        """명시적 Lazy[T] 타입 처리"""
        from ..core.lazy import (
            LazyFieldProxy,
            get_lazy_inner_type,
        )
        from ..core.container.element import (
            Scope as ScopeEnum,
            ScopeElement,
            PrototypeMode,
        )

        inner_type = get_lazy_inner_type(dep_type)
        if inner_type is None:
            return None

        # ForwardRef 해결 (문자열 타입 참조)
        if isinstance(inner_type, ForwardRef):
            type_name = inner_type.__forward_arg__
            resolved_type = None
            for t in self.manager.container_registry.keys():
                if t.__name__ == type_name:
                    resolved_type = t
                    break
            if resolved_type is None:
                raise Exception(
                    f"Cannot resolve Lazy['{type_name}']: type not found in registry"
                )
            inner_type = resolved_type

        # 컨테이너에서 Scope 정보 가져오기
        inner_scope = ScopeEnum.SINGLETON
        inner_prototype_mode = PrototypeMode.DEFAULT
        inner_container = self.manager.get_container(inner_type)

        if inner_container:
            for elem in inner_container.elements:
                if isinstance(elem, ScopeElement):
                    inner_scope = elem.scope
                    inner_prototype_mode = elem.prototype_mode
                    break

        # LazyFieldProxy 생성
        lifecycle_container = (
            inner_container
            if inner_scope in (ScopeEnum.CALL, ScopeEnum.REQUEST)
            else None
        )

        return LazyFieldProxy(
            self._make_resolver(inner_type, inner_scope),
            inner_type,
            inner_scope,
            lifecycle_container,
            inner_prototype_mode,
        )

    def _inject_default_lazy(self, name: str, dep_type: type) -> Any | None:
        """일반 타입의 기본 Lazy 동작 처리"""
        from ..core.lazy import LazyFieldProxy
        from ..core.container.element import (
            Scope as ScopeEnum,
            ScopeElement,
            PrototypeMode,
        )

        # 컨테이너 확인
        dep_container = self.manager.get_container(dep_type)
        if dep_container:
            return self._inject_from_container(dep_type, dep_container)

        # Factory 확인
        factory_container = self.manager.get_factory_container(dep_type)
        if factory_container:
            return self._inject_from_factory(dep_type, factory_container)

        # Factory도 없으면 기존 인스턴스 확인
        existing_instance = self.manager.get_instance(dep_type, raise_exception=False)
        if existing_instance is not None:
            return existing_instance

        return None

    def _inject_from_container(self, dep_type: type, dep_container: "Container") -> Any:
        """컨테이너에서 의존성 주입"""
        from ..core.lazy import LazyFieldProxy
        from ..core.container.element import (
            Scope as ScopeEnum,
            ScopeElement,
            PrototypeMode,
        )

        scope = ScopeEnum.SINGLETON
        prototype_mode = PrototypeMode.DEFAULT

        for elem in dep_container.elements:
            if isinstance(elem, ScopeElement):
                scope = elem.scope
                prototype_mode = elem.prototype_mode
                break

        # SINGLETON만 캐시된 인스턴스 사용
        if scope == ScopeEnum.SINGLETON:
            existing_instance = self.manager.get_instance(
                dep_type, raise_exception=False
            )
            if existing_instance is not None:
                return existing_instance

        # LazyFieldProxy로 주입
        lifecycle_container = (
            dep_container if scope in (ScopeEnum.CALL, ScopeEnum.REQUEST) else None
        )

        return LazyFieldProxy(
            self._make_resolver(dep_type, scope),
            dep_type,
            scope,
            lifecycle_container,
            prototype_mode,
        )

    def _inject_from_factory(
        self, dep_type: type, factory_container: "FactoryContainer"
    ) -> Any:
        """Factory에서 의존성 주입"""
        from ..core.lazy import LazyFieldProxy
        from ..core.container.element import Scope as ScopeEnum

        scope, prototype_mode = self.manager.get_container_scope(factory_container)

        # SINGLETON Factory인 경우 기존 인스턴스 사용
        if scope == ScopeEnum.SINGLETON:
            existing_instance = self.manager.get_instance(
                dep_type, raise_exception=False
            )
            if existing_instance is not None:
                return existing_instance

        # LazyFieldProxy로 주입
        def make_factory_resolver(fc: "FactoryContainer"):
            def resolver():
                return fc.initialize_instance()

            return resolver

        return LazyFieldProxy(
            make_factory_resolver(factory_container),
            dep_type,
            scope,
            factory_container,
            prototype_mode,
        )

    def _make_resolver(self, dep_type: type, scope: "ScopeEnum"):
        """Scope별 resolver 함수 생성"""
        from ..core.container.element import Scope as ScopeEnum

        manager = self.manager

        def resolver():
            # CALL/REQUEST는 항상 새 인스턴스 생성
            if scope == ScopeEnum.CALL or scope == ScopeEnum.REQUEST:
                if container := manager.get_container(dep_type):
                    return container._create_instance()
                raise Exception(
                    f"Cannot resolve {dep_type.__name__}: no container found"
                )

            # SINGLETON: 캐시 확인
            instance = manager.get_instance(dep_type, raise_exception=False)
            if instance is not None:
                return instance
            if container := manager.get_container(dep_type):
                return container.initialize_instance()
            raise Exception(f"Cannot resolve {dep_type.__name__}: no container found")

        return resolver
