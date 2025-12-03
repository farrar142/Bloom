"""FactoryContainer 클래스"""

import inspect
from typing import Callable, Self, get_type_hints, TYPE_CHECKING

if TYPE_CHECKING:
    from ..manager import ContainerManager

from .callable import CallableContainer
from ...utils.resolver import DependencyResolver


class FactoryContainer[**P, R](CallableContainer[P, R]):
    """
    팩토리 컴포넌트 컨테이너
    @Component
    class MyService:
        pass

    class ExternalService:
        def __init__(self, my_service: MyService):
            pass

    @Component
    class MyConfiguration:
        @Factory
        def create_external_service(self, my_service: MyService) -> ExternalService:
            return ExternalService(my_service)

    @Component
    class AnotherComponent:
        external_service: ExternalService

    에서 create_external_service 메서드에 대한 컨테이너 역할을 한다
    initialize 후에는 ExternalService 인스턴스가 생성되고
    글로벌 레지스트리에 인스턴스가 저장된다

    """

    _default_priority: int = 30

    def __init__(self, factory_method: Callable[P, R]):
        self._target: type | None = None
        self._resolver: DependencyResolver | None = None
        self.manager: "ContainerManager | None" = None  # scan 시점에 주입됨
        # Factory Chain에서 중간 단계인지 여부 (True면 인스턴스 등록 스킵)
        self._is_chain_intermediate: bool = False

        # CallableContainer 초기화 (target은 property로 동적 resolve)
        self.callable_target = factory_method
        self.owner_cls: type | None = None
        self._bound_method: Callable[P, R] | None = None
        self._is_coroutine: bool | None = None

        # Container 기본 초기화 (target 설정 제외)
        from .element import Element, PriorityElement

        self.elements = list[Element]()
        self.element = Element()
        self.add_element(PriorityElement(self._default_priority))

    @property
    def factory_method(self) -> Callable[P, R]:
        """callable_target의 별칭 (하위 호환성)"""
        return self.callable_target

    def _get_resolver(self) -> DependencyResolver:
        """DependencyResolver 인스턴스 (캐싱)"""
        if self._resolver is None:
            self._resolver = DependencyResolver(
                self.callable_target,
                skip_params=1,  # self 스킵
            )
        return self._resolver

    def _get_target_type(self) -> type:
        """반환 타입을 resolve"""
        hints = self._get_resolver()._hints
        return hints.get("return", type(None))

    def __repr__(self) -> str:
        try:
            target = self._get_target_type()
            target_name = target.__name__ if isinstance(target, type) else str(target)
        except Exception:
            target_name = "Unknown"
        method_name = self.callable_target.__name__
        return f"FactoryContainer(method={method_name}, target={target_name})"

    @property
    def target(self) -> type:  # type: ignore
        """target을 동적으로 resolve"""
        if self._target is None:
            self._target = self._get_target_type()
        return self._target

    def get_dependencies(self) -> list[type]:
        """이 팩토리 컨테이너가 의존하는 타입들을 반환"""
        dependencies = []
        owner_type = self._get_owner_type()
        if owner_type:
            dependencies.append(owner_type)

        resolver = self._get_resolver()
        hints = resolver._hints

        for name, param in resolver._params:
            param_type = hints.get(name)
            if param_type is None or param_type == owner_type:
                continue

            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                # varargs (*args: Type) - 해당 타입의 서브클래스 컨테이너들을 의존성으로 추가
                manager = self._get_manager()
                for containers in manager.get_all_containers().values():
                    for container in containers:
                        kls = container.target
                        if (
                            isinstance(kls, type)
                            and kls != param_type
                            and issubclass(kls, param_type)
                        ):
                            dependencies.append(kls)
            else:
                dependencies.append(param_type)

        return dependencies

    def _create_instance(self) -> R:
        """팩토리 메서드를 통해 인스턴스 생성"""
        manager = self._get_manager()
        owner_type = self._get_owner_type()
        if owner_type is None:
            raise Exception(
                f"Factory method {self.callable_target.__name__} must have 'self' parameter with type hint"
            )
        owner_instance = manager.get_instance(owner_type)

        # DependencyResolver로 의존성 resolve
        resolver = self._get_resolver()
        deps = resolver.resolve(manager, chain_type=self.target)

        return deps.call(self.callable_target, owner_instance)

    def initialize_instance(self) -> R:
        """
        인스턴스 초기화 (Factory Chain을 위해 캐시 무시)

        Factory Chain에서는 각 Factory가 독립적으로 _create_instance()를 호출해야 함.
        이전 단계의 결과를 의존성으로 받아서 수정하는 패턴이기 때문임.

        Note: @PostConstruct는 여기서 호출하지 않습니다.
        orchestrator가 async로 처리합니다.
        """
        # Factory는 항상 _create_instance() 호출 (캐시 무시)
        instance = self._create_instance()
        return instance

    @classmethod
    def get_or_create(cls, factory_method: Callable[P, R]) -> Self:
        """팩토리 메서드에 대한 컨테이너 생성"""
        return cls._apply_override_rules(factory_method, lambda: cls(factory_method))
