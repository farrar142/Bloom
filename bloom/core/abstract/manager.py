"""AbstractManager - 매니저 추상 클래스

Manager는 전체 시스템을 조율하고, Registry/Entry를 관리합니다.
초기화 순서 관리, Entry 수집, 인스턴스 캐싱 등을 담당합니다.

Registry 생성 방식:
    1. ContainerManager에서 Registry 인스턴스 검색
    2. 존재하면 해당 Registry 사용
    3. 존재하지 않으면 Manager가 Entry들을 수집하여 자동으로 Registry 생성

사용 예시:
    class StaticFilesManager(AbstractManager[StaticFilesRegistry]):
        registry_type = StaticFilesRegistry  # 생성할 Registry 타입
        entry_type = StaticFileEntry         # 수집할 Entry 타입
"""

from abc import ABC
from typing import Generic, TypeVar, TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from .registry import AbstractRegistry
    from .entry import Entry
    from ..manager import ContainerManager

R = TypeVar("R", bound="AbstractRegistry")


class AbstractManager(ABC, Generic[R]):
    """
    매니저 추상 클래스

    Manager는 다음 책임을 가집니다:
    - 전체 시스템 조율 및 초기화
    - Registry 관리 (검색 또는 자동 생성)
    - Entry 수집 및 Registry에 등록
    - 라이프사이클 관리

    Registry 생성 방식:
        1. ContainerManager에서 registry_type 인스턴스 검색
        2. 존재하면 해당 Registry 사용
        3. 존재하지 않으면 새 Registry 생성 후 entry_type Entry들 수집

    서브클래스는 다음을 구현해야 합니다:
    - registry_type: 생성할 Registry 타입 (클래스 변수)
    - entry_type: 수집할 Entry 타입 (클래스 변수)

    사용 예시:
        class StaticFilesManager(AbstractManager[StaticFilesRegistry]):
            registry_type = StaticFilesRegistry
            entry_type = StaticFileEntry
    """

    # 서브클래스에서 정의해야 할 클래스 변수
    registry_type: ClassVar[type[R]]  # type: ignore
    entry_type: ClassVar[type["Entry"]]  # type: ignore

    def __init__(self):
        self._initialized: bool = False
        self._registry: R | None = None

    @property
    def registry(self) -> R:
        """
        관리하는 Registry 반환

        초기화되지 않았으면 자동으로 초기화합니다.
        """
        if self._registry is None:
            raise RuntimeError(
                f"{self.__class__.__name__} is not initialized. "
                "Call initialize() first."
            )
        return self._registry

    @property
    def initialized(self) -> bool:
        """초기화 완료 여부"""
        return self._initialized

    def initialize(self, container_manager: "ContainerManager") -> None:
        """
        Manager 초기화

        1. ContainerManager에서 Registry 검색
        2. 없으면 새 Registry 생성
        3. Entry들을 수집하여 Registry에 등록

        Args:
            container_manager: Entry와 Registry를 검색할 ContainerManager
        """
        if self._initialized:
            return

        # 1. ContainerManager에서 기존 Registry 검색
        registry_type = getattr(self.__class__, "registry_type", None)
        if registry_type is not None:
            existing_registries = container_manager.get_sub_instances(registry_type)
            if existing_registries:
                self._registry = existing_registries[0]
            else:
                # 2. 없으면 새 Registry 생성
                self._registry = registry_type()

        # 3. Entry들 수집 및 등록
        entry_type = getattr(self.__class__, "entry_type", None)
        if entry_type is not None and self._registry is not None:
            entries = container_manager.get_sub_instances(entry_type)
            for entry in entries:
                self._registry.register(entry)

        self._initialized = True

    def ensure_initialized(self, container_manager: "ContainerManager") -> None:
        """초기화되지 않았으면 초기화 수행"""
        if not self._initialized:
            self.initialize(container_manager)

    def reset(self) -> None:
        """Manager 상태 초기화"""
        if self._registry is not None:
            self._registry.clear()
        self._initialized = False

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(initialized={self._initialized})"


class SingletonManager(AbstractManager[R], Generic[R]):
    """
    싱글톤 매니저

    하나의 인스턴스만 허용하는 Manager입니다.
    같은 타입의 여러 인스턴스 생성을 방지합니다.

    사용 예시:
        class ConfigManager(SingletonManager[ConfigRegistry]):
            registry_type = ConfigRegistry
            entry_type = ConfigEntry
            _instance: ClassVar["ConfigManager | None"] = None

            @classmethod
            def get_instance(cls) -> "ConfigManager":
                if cls._instance is None:
                    cls._instance = cls()
                return cls._instance
    """

    pass


class CollectorManager(AbstractManager[R], Generic[R]):
    """
    수집기 매니저

    ContainerManager에서 특정 타입의 Entry를 수집하는 Manager입니다.
    AbstractManager의 기본 동작을 그대로 사용합니다.

    사용 예시:
        class StaticFilesManager(CollectorManager[StaticFilesRegistry]):
            registry_type = StaticFilesRegistry
            entry_type = StaticFileEntry
    """

    pass


# TYPE_CHECKING을 위한 import
if TYPE_CHECKING:
    from ..manager import ContainerManager
