"""테스트용 Mock 컨테이너 및 의존성 오버라이드"""

from contextlib import contextmanager
from typing import Any, Callable, Iterator, TypeVar, Generic
from dataclasses import dataclass, field

from ..core.manager import ContainerManager, get_current_manager, set_current_manager
from ..core.container import Container, ComponentContainer


T = TypeVar("T")


@dataclass
class MockInstance(Generic[T]):
    """Mock 인스턴스 정보"""

    target_type: type[T]
    instance: T
    original: T | None = None


class MockContainer:
    """
    테스트용 Mock 컨테이너

    특정 타입의 인스턴스를 mock으로 대체할 수 있습니다.

    Usage:
        mock = MockContainer()
        mock.override(UserRepository, FakeUserRepository())

        with mock.apply():
            # 이 스코프 내에서 UserRepository 주입 시 FakeUserRepository가 사용됨
            app = Application("test").scan(module)
            asyncio.run(app.ready_async())
            user_service = app.manager.get_instance(UserService)
    """

    def __init__(self):
        self._overrides: dict[type, Any] = {}
        self._original_instances: dict[type, list[Any]] = {}
        self._manager: ContainerManager | None = None

    def override(self, target_type: type[T], instance: T) -> "MockContainer":
        """
        특정 타입의 인스턴스를 mock으로 대체

        Args:
            target_type: 대체할 타입
            instance: mock 인스턴스

        Returns:
            self (체이닝 지원)
        """
        self._overrides[target_type] = instance
        return self

    def override_factory(
        self, target_type: type[T], factory: Callable[..., T]
    ) -> "MockContainer":
        """
        특정 타입의 팩토리를 mock으로 대체

        팩토리 함수는 호출 시마다 새 인스턴스를 생성합니다.

        Args:
            target_type: 대체할 타입
            factory: mock 인스턴스를 생성하는 팩토리 함수

        Returns:
            self (체이닝 지원)
        """
        # _FactoryWrapper를 사용하여 팩토리임을 표시
        self._overrides[target_type] = _FactoryWrapper(factory)
        return self

    def clear(self) -> "MockContainer":
        """모든 오버라이드 제거"""
        self._overrides.clear()
        return self

    def remove(self, target_type: type) -> "MockContainer":
        """특정 타입의 오버라이드 제거"""
        self._overrides.pop(target_type, None)
        return self

    @contextmanager
    def apply(
        self, manager: ContainerManager | None = None
    ) -> Iterator["MockContainer"]:
        """
        오버라이드를 적용하는 컨텍스트 매니저

        Args:
            manager: 적용할 ContainerManager (없으면 현재 활성 매니저)

        Yields:
            self
        """
        self._manager = manager or get_current_manager()

        # 원래 인스턴스 백업 및 mock 주입
        for target_type, override in self._overrides.items():
            # 원래 인스턴스 백업
            self._original_instances[target_type] = list(
                self._manager.instance_registry.get(target_type, [])
            )

            # mock 인스턴스 주입
            instance = override() if isinstance(override, _FactoryWrapper) else override
            self._manager.instance_registry[target_type] = [instance]

        try:
            yield self
        finally:
            # 원래 인스턴스 복원
            for target_type, original in self._original_instances.items():
                if original:
                    self._manager.instance_registry[target_type] = original
                else:
                    self._manager.instance_registry.pop(target_type, None)

            self._original_instances.clear()
            self._manager = None

    def get_mock(self, target_type: type[T]) -> T | None:
        """
        등록된 mock 인스턴스 반환

        Args:
            target_type: 조회할 타입

        Returns:
            mock 인스턴스 또는 None
        """
        override = self._overrides.get(target_type)
        if override is None:
            return None
        return override() if isinstance(override, _FactoryWrapper) else override


class _FactoryWrapper:
    """팩토리 함수 래퍼"""

    def __init__(self, factory: Callable[..., Any]):
        self._factory = factory

    def __call__(self) -> Any:
        return self._factory()


@contextmanager
def override_dependency(
    target_type: type[T], instance: T, manager: ContainerManager | None = None
) -> Iterator[T]:
    """
    단일 의존성을 오버라이드하는 컨텍스트 매니저

    Usage:
        with override_dependency(UserRepository, FakeUserRepository()) as mock:
            # mock 사용
            pass

    Args:
        target_type: 대체할 타입
        instance: mock 인스턴스
        manager: 적용할 ContainerManager (없으면 현재 활성 매니저)

    Yields:
        mock 인스턴스
    """
    mock = MockContainer()
    mock.override(target_type, instance)

    with mock.apply(manager):
        yield instance


@contextmanager
def isolated_container(
    name: str = "isolated_test", inherit_containers: bool = False
) -> Iterator[ContainerManager]:
    """
    격리된 ContainerManager를 생성하는 컨텍스트 매니저

    테스트 간 완전한 격리가 필요할 때 사용합니다.

    Usage:
        with isolated_container() as manager:
            # 새로운 격리된 환경에서 테스트
            app = Application("test")
            app.scan(module)
            asyncio.run(app.ready_async())

    Args:
        name: ContainerManager 이름
        inherit_containers: True면 현재 매니저의 컨테이너를 상속

    Yields:
        새로운 격리된 ContainerManager
    """
    original_manager = get_current_manager() if inherit_containers else None
    new_manager = ContainerManager(name)

    # 컨테이너 상속 (선택적)
    if inherit_containers and original_manager:
        for target, containers in original_manager.container_registry.items():
            for container in containers:
                new_manager.register_container(container)

    # 새 매니저 활성화
    old_manager = get_current_manager() if set_current_manager else None
    set_current_manager(new_manager)

    try:
        yield new_manager
    finally:
        # 원래 매니저 복원
        set_current_manager(old_manager)
        new_manager.reset()
