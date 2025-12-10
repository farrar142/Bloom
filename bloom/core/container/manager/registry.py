"""
ContainerRegistry - 컨테이너/인스턴스 조회 담당
"""

from typing import TYPE_CHECKING, overload

from .types import COMPONENT_ID, containers

if TYPE_CHECKING:
    from ..base import Container
    from ..factory import ConfigurationContainer


class ContainerRegistry:
    """컨테이너 조회 담당

    책임:
    - 컨테이너 조회: container(), containers()
    - 인스턴스 조회: instance(), instances_of()
    - Factory 조회: factory(), factory_types(), configuration_for()
    """

    def __init__(self, instances: dict[COMPONENT_ID, object]) -> None:
        self._instances = instances

    # =========================================================================
    # 컨테이너 조회
    # =========================================================================

    @overload
    def container[T](
        self,
        *,
        type: type[T],
        id: COMPONENT_ID | None = None,
    ) -> "Container[T]":
        """등록된 타입으로 컨테이너 조회"""
        ...

    @overload
    def container[T: "Container"](
        self,
        *,
        container_type: type[T],
        id: COMPONENT_ID | None = None,
    ) -> T:
        """컨테이너 클래스 타입으로 조회"""
        ...

    @overload
    def container(
        self,
        *,
        id: COMPONENT_ID,
    ) -> "Container":
        """컴포넌트 ID로 컨테이너 조회"""
        ...

    def container[T](
        self,
        *,
        type: type[T] | None = None,
        container_type: "type[Container] | None" = None,
        id: COMPONENT_ID | None = None,
    ) -> "Container":
        """컨테이너 조회

        Args:
            type: 등록된 클래스/함수 타입
            container_type: Container 서브클래스 타입 (ConfigurationContainer 등)
            id: 컴포넌트 ID

        Returns:
            조회된 컨테이너

        Examples:
            registry.container(type=MyService)
            registry.container(container_type=ConfigurationContainer, id=some_id)
            registry.container(id=component_id)
        """
        # ID로만 조회
        if id is not None and type is None and container_type is None:
            for container_dict in containers.values():
                if id in container_dict:
                    return container_dict[id]
            raise ValueError(f"No container found for id: {id}")

        # 컨테이너 클래스 타입으로 조회
        if container_type is not None:
            matched = [
                c
                for container_dict in containers.values()
                for c in container_dict.values()
                if isinstance(c, container_type)
            ]
            if id is not None:
                for c in matched:
                    if c.component_id == id:
                        return c
                raise ValueError(f"No {container_type.__name__} found with id: {id}")
            if not matched:
                raise ValueError(f"No {container_type.__name__} found")
            return matched[0]

        # 등록된 타입으로 조회
        if type is not None:
            if type not in containers:
                raise ValueError(f"No container registered for type: {type}")
            container_dict = containers[type]
            if id is not None:
                if id not in container_dict:
                    raise ValueError(f"No container for {type} with id: {id}")
                return container_dict[id]
            if not container_dict:
                raise ValueError(f"No container found for type: {type}")
            return next(iter(container_dict.values()))

        raise ValueError("Must provide 'type', 'container_type', or 'id'")

    def containers[T: "Container"](
        self,
        container_type: type[T],
    ) -> list[T]:
        """특정 컨테이너 클래스의 모든 컨테이너 조회

        Args:
            container_type: Container 서브클래스 (ConfigurationContainer 등)

        Returns:
            해당 타입의 모든 컨테이너 리스트
        """
        return [
            c
            for container_dict in containers.values()
            for c in container_dict.values()
            if isinstance(c, container_type)
        ]

    # =========================================================================
    # 인스턴스 조회
    # =========================================================================

    @overload
    def instance[T](self, *, type: type[T]) -> T:
        """타입으로 인스턴스 조회 (required)"""
        ...

    @overload
    def instance[T](self, *, type: type[T], required: bool) -> T | None:
        """타입으로 인스턴스 조회"""
        ...

    @overload
    def instance[T](self, *, id: COMPONENT_ID) -> T:
        """ID로 인스턴스 조회 (required)"""
        ...

    @overload
    def instance[T](self, *, id: COMPONENT_ID, required: bool) -> T | None:
        """ID로 인스턴스 조회"""
        ...

    @overload
    def instance[T](
        self,
        *,
        type: type[T] | None = None,
        id: COMPONENT_ID | None = None,
        required: bool = True,
    ) -> T | None: ...

    def instance[T](
        self,
        *,
        type: type[T] | None = None,
        id: COMPONENT_ID | None = None,
        required: bool = True,
    ) -> T | None:
        """인스턴스 조회

        Args:
            type: 인스턴스 타입
            id: 컴포넌트 ID
            required: True면 없을 시 예외 발생

        Returns:
            조회된 인스턴스

        Examples:
            registry.instance(type=MyService)
            registry.instance(id=component_id)
            registry.instance(type=MyService, required=False)
        """
        # ID로 조회
        if id is not None:
            if id in self._instances:
                return self._instances[id]  # type: ignore
            if required:
                raise ValueError(f"No instance found for id: {id}")
            return None

        # 타입으로 조회
        if type is not None:
            for inst in self._instances.values():
                if isinstance(inst, type):
                    return inst  # type: ignore
            if required:
                raise ValueError(f"No instance found for type: {type}")
            return None

        raise ValueError("Must provide 'type' or 'id'")

    def instances_of[T](self, type: type[T]) -> list[T]:
        """특정 타입의 모든 인스턴스 조회"""
        return [
            inst for inst in self._instances.values() if isinstance(inst, type)
        ]  # type: ignore

    # =========================================================================
    # Factory 조회
    # =========================================================================

    @overload
    async def factory[T](self, type: type[T]) -> T: ...
    @overload
    async def factory[T](self, type: type[T], *, required: bool) -> T | None: ...
    async def factory[T](self, type: type[T], *, required: bool = True) -> T | None:
        """Factory 인스턴스 조회

        Args:
            type: Factory 반환 타입
            required: True면 없을 시 예외 발생

        Returns:
            Factory 인스턴스
        """
        # 캐시된 인스턴스 찾기
        for config in self._configurations():
            cached = config.get_cached_factory(type)
            if cached is not None:
                return cached

        # Factory 정의가 있는 Configuration 찾기
        config = self.configuration_for(type)
        if config is None:
            if required:
                raise ValueError(f"No Factory found for type '{type.__name__}'")
            return None

        # Factory 인스턴스 생성
        return await config.create_factory(type)

    def factory_types(self) -> list[type]:
        """모든 Factory 반환 타입 조회"""
        result: list[type] = []
        for config in self._configurations():
            result.extend(config.get_factory_types())
        return result

    def configuration_for[T](
        self, factory_type: type[T]
    ) -> "ConfigurationContainer | None":
        """특정 타입의 Factory를 가진 Configuration 찾기"""
        for config in self._configurations():
            if config.has_factory(factory_type):
                return config
        return None

    def _configurations(self) -> list["ConfigurationContainer"]:
        """모든 ConfigurationContainer 조회"""
        from ..factory import ConfigurationContainer

        return self.containers(ConfigurationContainer)
