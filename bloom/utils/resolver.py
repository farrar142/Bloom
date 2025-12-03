"""의존성 해결 유틸리티"""

import inspect
from typing import Any, Callable, get_type_hints, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from ..core.manager import ContainerManager


@dataclass
class ResolvedDependencies:
    """resolve된 의존성 결과"""

    args: list[Any] = field(default_factory=list)
    kwargs: dict[str, Any] = field(default_factory=dict)
    varargs: list[Any] = field(default_factory=list)

    def call(self, func: Callable, *prepend_args: Any) -> Any:
        """함수를 resolve된 의존성으로 호출"""
        return func(*prepend_args, *self.varargs, *self.args, **self.kwargs)


class DependencyResolver:
    """
    함수 시그니처에서 의존성을 추출하고 resolve하는 클래스

    사용 예:
        resolver = DependencyResolver(my_func, skip_params=1)  # self 스킵
        deps = resolver.resolve(manager)
        result = deps.call(my_func, self_instance)
    """

    def __init__(
        self,
        func: Callable,
        skip_params: int = 0,
        exclude_types: list[type] | None = None,
    ):
        """
        Args:
            func: 의존성을 추출할 함수
            skip_params: 건너뛸 앞쪽 파라미터 개수 (예: self, fn 등)
            exclude_types: resolve에서 제외할 타입들 (예: 자신의 반환 타입)
        """
        self.func = func
        self.skip_params = skip_params
        self.exclude_types = exclude_types or []

        # 시그니처 분석
        self._sig = inspect.signature(func)
        self._hints = self._get_type_hints()
        self._params = list(self._sig.parameters.items())[skip_params:]

    def _get_type_hints(self) -> dict:
        """타입 힌트를 안전하게 가져오기"""
        try:
            globalns = getattr(self.func, "__globals__", {})
            return get_type_hints(self.func, globalns=globalns)
        except Exception:
            return getattr(self.func, "__annotations__", {})

    def get_inject_types(self) -> list[type]:
        """
        주입할 타입들만 리스트로 반환 (DecoratorContainer용)

        varargs, kwargs 제외하고 일반 파라미터의 타입만 반환
        """
        result: list[type] = []
        for name, param in self._params:
            if param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue

            param_type = self._hints.get(name)
            if param_type is not None and isinstance(param_type, type):
                result.append(param_type)

        return result

    def get_dependency_types(self) -> list[type]:
        """
        모든 의존성 타입 반환 (varargs의 서브타입 포함하지 않음)

        FactoryContainer.get_dependencies() 용도
        """
        result: list[type] = []
        for name, param in self._params:
            param_type = self._hints.get(name)
            if param_type is None:
                continue
            if param_type in self.exclude_types:
                continue

            # varargs는 타입만 추가 (서브타입은 resolve 시점에 처리)
            if isinstance(param_type, type):
                result.append(param_type)

        return result

    def resolve(
        self,
        manager: "ContainerManager",
        chain_type: type | None = None,
    ) -> ResolvedDependencies:
        """
        의존성을 resolve하여 ResolvedDependencies 반환

        Args:
            manager: ContainerManager 인스턴스
            chain_type: Factory Chain에서 자신의 반환 타입 (특별 처리용)

        Returns:
            ResolvedDependencies with args, kwargs, varargs
        """
        result = ResolvedDependencies()

        for name, param in self._params:
            param_type = self._hints.get(name)
            if param_type is None:
                continue

            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                # *args: Type - 해당 타입의 모든 서브 인스턴스 수집
                if param_type:
                    result.varargs = manager.get_sub_instances(param_type)

            elif param.kind == inspect.Parameter.VAR_KEYWORD:
                # **kwargs는 현재 지원하지 않음
                pass

            else:
                # 일반 파라미터
                if name == "return":
                    continue

                # Factory Chain: 자신의 반환 타입과 같으면 기존 인스턴스 사용
                if chain_type and param_type == chain_type:
                    instance = manager.get_instance(param_type, raise_exception=False)
                    if instance is not None:
                        result.kwargs[name] = instance
                        continue

                # 일반적인 의존성 주입
                result.kwargs[name] = manager.get_instance(param_type)

        return result

    def resolve_as_list(self, manager: "ContainerManager") -> list[Any]:
        """
        의존성을 리스트로 resolve (DecoratorContainer용)

        kwargs 없이 순서대로 리스트로 반환
        """
        result: list[Any] = []
        for name, param in self._params:
            if param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue

            param_type = self._hints.get(name)
            if param_type is not None and isinstance(param_type, type):
                result.append(manager.get_instance(param_type))

        return result
