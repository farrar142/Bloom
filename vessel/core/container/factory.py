"""FactoryContainer 클래스"""

import inspect
from typing import Callable, Self, get_type_hints, TYPE_CHECKING

if TYPE_CHECKING:
    from ..manager import ContainerManager

from .base import Container


class FactoryContainer[**P, R](Container[Callable[P, R]]):
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

    def __init__(self, factory_method: Callable[P, R]):
        self.factory_method = factory_method
        self._resolved_hints: dict | None = None
        self._target: type | None = None
        self.elements = list()
        self.owner_cls: type | None = None  # scan_components 후 주입됨
        self.manager: "ContainerManager | None" = None  # scan 시점에 주입됨

    def _get_type_hints(self) -> dict:
        """타입 힌트를 resolve하여 캐시"""
        if self._resolved_hints is None:
            try:
                # 함수의 globals를 사용해서 타입 힌트 resolve
                globalns = getattr(self.factory_method, "__globals__", {})
                self._resolved_hints = get_type_hints(
                    self.factory_method, globalns=globalns
                )
            except Exception:
                self._resolved_hints = getattr(
                    self.factory_method, "__annotations__", {}
                )
        return self._resolved_hints  # type: ignore

    def _get_target_type(self) -> type:
        """반환 타입을 resolve"""
        hints = self._get_type_hints()
        return hints.get("return", type(None))

    def _get_owner_type(self) -> type | None:
        """owner 타입 반환 (scan_components에서 주입됨)"""
        return self.owner_cls

    def __repr__(self) -> str:
        try:
            target = self._get_target_type()
            target_name = target.__name__ if isinstance(target, type) else str(target)
        except Exception:
            target_name = "Unknown"
        return f"FactoryContainer(method={self.factory_method.__name__}, target={target_name}, elements={self.elements})"

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

        hints = self._get_type_hints()
        sig = inspect.signature(self.factory_method)
        first_param_name = list(sig.parameters.keys())[0] if sig.parameters else None

        for param_name, param in sig.parameters.items():
            if param_name == first_param_name:
                continue
            param_type = hints.get(param_name)
            if param_type is None or param_type == owner_type:
                continue

            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                # varargs (*args: Type) - 해당 타입의 서브클래스 컨테이너들을 의존성으로 추가
                manager = self._get_manager()
                for (
                    kls,
                    qual_containers,
                ) in manager.get_all_containers().items():
                    if kls != param_type and issubclass(kls, param_type):
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
                f"Factory method {self.factory_method.__name__} must have 'self' parameter with type hint"
            )
        owner_instance = manager.get_instance(owner_type)
        # self를 제외한 hints만 전달
        hints = self._get_type_hints()
        sig = inspect.signature(self.factory_method)
        first_param_name = list(sig.parameters.keys())[0] if sig.parameters else None

        # varargs (*args) 파라미터 처리
        varargs: list = []
        vararg_param_name: str | None = None
        for param_name, param in sig.parameters.items():
            if param_name == first_param_name:
                continue
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                vararg_param_name = param_name
                # *args: Type 형태 - 해당 타입의 모든 서브 인스턴스 수집
                vararg_type = hints.get(param_name)
                if vararg_type:
                    varargs = manager.get_sub_instances(vararg_type)

        # varargs 파라미터는 kwargs에서 제외
        filtered_hints = {
            k: v
            for k, v in hints.items()
            if k != first_param_name and k != vararg_param_name
        }
        kwargs = self._inject_dependencies(filtered_hints)
        return self.factory_method(owner_instance, *varargs, **kwargs)  # type: ignore

    @classmethod
    def get_or_create(cls, factory_method: Callable[P, R]) -> Self:
        """팩토리 메서드에 대한 컨테이너 생성"""
        if not (container := getattr(factory_method, "__container__", None)):
            container = cls(factory_method)
            setattr(factory_method, "__container__", container)
        return container
