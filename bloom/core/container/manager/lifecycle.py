"""
ContainerLifecycle - 컨테이너 라이프사이클 관리 담당
"""

import inspect
import types
from typing import TYPE_CHECKING

from .types import COMPONENT_ID, containers

if TYPE_CHECKING:
    from ..base import Container
    from .registry import ContainerRegistry
    from .factory import ContainerFactory


class ContainerLifecycle:
    """컨테이너 라이프사이클 관리 담당

    책임:
    - 초기화: initialize()
    - 종료: shutdown()
    - Factory 초기화: _initialize_factories()
    - Factory 의존성 주입: _inject_factory_dependencies()
    - 핸들러 바인딩: _bind_handler_methods()
    """

    def __init__(
        self,
        instances: dict[COMPONENT_ID, object],
        registry: "ContainerRegistry",
        factory: "ContainerFactory",
    ) -> None:
        self._instances = instances
        self._registry = registry
        self._factory = factory

    # =========================================================================
    # 초기화/종료
    # =========================================================================

    async def initialize(self) -> None:
        """모든 컨테이너 초기화"""
        # 1. 모든 컨테이너 초기화 및 일반 의존성 주입
        # 스냅샷 생성 (반복 중 dict 변경 방지)
        initial_containers = [(rt, dict(cd)) for rt, cd in containers.items()]
        for registered_type, container_dict in initial_containers:
            for container in container_dict.values():
                instance = await container.initialize()
                self._add_instance(container.component_id, instance)
                self._factory.inject_dependencies(container, instance)

        # 2. Factory 인스턴스 미리 생성
        await self._initialize_factories()

        # 3. Factory 의존성 주입 (스냅샷 갱신)
        current_containers = [(rt, dict(cd)) for rt, cd in containers.items()]
        for registered_type, container_dict in current_containers:
            for container in container_dict.values():
                instance = self._registry.instance(
                    id=container.component_id, required=False
                )
                if instance is not None:
                    await self._inject_factory_dependencies(container, instance)

        # 4. Handler 메서드 바인딩 (스냅샷 사용)
        for registered_type, container_dict in current_containers:
            if inspect.isclass(registered_type):
                for container in container_dict.values():
                    await self._bind_handler_methods(container)

    async def shutdown(self) -> None:
        """모든 컨테이너 종료"""
        current_containers = [(rt, dict(cd)) for rt, cd in containers.items()]
        for registered_type, container_dict in current_containers:
            for container in container_dict.values():
                await container.shutdown()

    # =========================================================================
    # Private 메서드
    # =========================================================================

    def _add_instance(self, component_id: COMPONENT_ID, instance: object) -> None:
        """인스턴스 저장"""
        self._instances[component_id] = instance

    async def _initialize_factories(self) -> None:
        """SINGLETON 스코프 Factory 인스턴스만 미리 생성

        CALL, REQUEST 등의 스코프는 사용 시점에 생성됨
        """
        from ..factory import ConfigurationContainer
        from ..scope import Scope

        for config in self._registry.containers(ConfigurationContainer):
            for factory_container in config.get_factory_containers():
                # SINGLETON 스코프만 미리 초기화
                if factory_container.scope == Scope.SINGLETON:
                    await self._registry.factory(
                        factory_container.return_type, required=False
                    )

    async def _inject_factory_dependencies[T](
        self, container: "Container[T]", instance: T
    ) -> None:
        """Factory 타입 필드에 인스턴스 주입"""
        from ..factory import FactoryContainer

        if isinstance(container, FactoryContainer):
            return

        for dep in container.dependencies:
            if not self._factory._is_factory_type(dep.field_type):
                continue

            if getattr(instance, dep.field_name, None) is not None:
                continue

            factory_instance = await self._registry.factory(
                dep.field_type, required=False
            )
            if factory_instance is None:
                if dep.is_optional:
                    continue
                raise RuntimeError(
                    f"Cannot resolve Factory dependency '{dep.field_name}' "
                    f"for '{container.kls.__name__}'"
                )

            setattr(instance, dep.field_name, factory_instance)

    async def _bind_handler_methods[T](self, container: "Container[T]") -> None:
        """Handler 메서드를 인스턴스에 바인딩"""
        from .. import HandlerContainer
        from ...injection import AutowiredField

        for name in dir(container.kls):
            if name.startswith("_"):
                continue

            attr = getattr(container.kls, name, None)
            if attr is None or inspect.isclass(attr):
                continue
            
            # AutowiredField 마커는 스킵 (의존성 주입용)
            if isinstance(attr, AutowiredField):
                continue

            # Handler 등록
            component_id = getattr(attr, "__component_id__", None)
            if not component_id:
                # callable이 아니면 스킵 (속성값 등)
                if not callable(attr):
                    continue
                handler_container = HandlerContainer.register(attr)
                self._add_instance(
                    handler_container.component_id,
                    await handler_container.initialize(),
                )
                component_id = handler_container.component_id

            handler_instance = self._registry.instance(id=component_id, required=False)
            if not handler_instance:
                continue

            # 바인딩
            handler_container = self._registry.container(type=attr, id=component_id)
            parent_instance = self._registry.instance(id=container.component_id)

            handler_container.parent_instance = parent_instance
            handler_container.parent_container = container

            bound_handler = types.MethodType(handler_instance, parent_instance)
            self._add_instance(component_id, bound_handler)
            setattr(parent_instance, name, bound_handler)
