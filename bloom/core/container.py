"""bloom.core.container - 컴포넌트 컨테이너"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, TypeVar, get_type_hints, TYPE_CHECKING

from .scope import ScopeEnum
from .lifecycle import LifecycleManager

if TYPE_CHECKING:
    from .manager import ContainerManager


T = TypeVar("T")


@dataclass
class DependencyInfo:
    """의존성 정보"""

    field_name: str  # 필드명
    field_type: type  # 타입 (AsyncProxy[T]인 경우 T)
    is_optional: bool = False  # Optional 여부
    default_value: Any = None  # 기본값
    is_async_proxy: bool = False  # AsyncProxy[T]로 선언되었는지 여부
    raw_type_hint: Any = None  # 원본 타입 힌트 (AsyncProxy[T] 등)


@dataclass
class FactoryInfo(Generic[T]):
    """@Factory 메서드 정보"""

    method: Callable[..., T]  # 팩토리 메서드
    return_type: type[T]  # 반환 타입
    owner: type  # 소속 Configuration 클래스
    dependencies: list[DependencyInfo] = field(
        default_factory=list
    )  # 팩토리 메서드 파라미터 의존성


@dataclass
class Container(Generic[T]):
    """
    컴포넌트 컨테이너.
    하나의 컴포넌트(클래스)에 대한 메타데이터와 인스턴스 관리.
    """

    target: type[T]  # 원본 클래스
    scope: ScopeEnum = ScopeEnum.SINGLETON  # 인스턴스 스코프
    dependencies: list[DependencyInfo] = field(default_factory=list)  # 필드 의존성
    factory: FactoryInfo[T] | None = None  # @Factory 메서드 (있으면)
    name: str | None = None  # 빈 이름 (중복 타입 구분용)
    primary: bool = False  # @Primary 여부
    lazy: bool = True  # 지연 초기화 여부 (기본 True)

    def __post_init__(self) -> None:
        if not self.dependencies:
            self.dependencies = self._analyze_dependencies()

    def _analyze_dependencies(self) -> list[DependencyInfo]:
        """클래스 필드에서 의존성 분석"""
        from typing import get_origin, get_args

        deps: list[DependencyInfo] = []

        # 타입 힌트에서 의존성 추출
        # forward reference 해결을 위해 include_extras=True, globalns/localns 전달
        try:
            # __annotations__에서 직접 가져오되, 문자열은 나중에 해결
            hints = self._resolve_type_hints()
        except Exception:
            hints = {}

        # 클래스 변수 중 타입힌트가 있는 것들
        for name, hint in hints.items():
            if name.startswith("_"):
                continue

            # 기본값 확인
            default = getattr(self.target, name, _MISSING)
            is_optional = default is not _MISSING

            # AsyncProxy[T] 타입 확인
            is_async_proxy = False
            actual_type = hint

            # AsyncProxy 체크 (런타임에 제네릭 타입 분석)
            origin = get_origin(hint)
            if origin is not None:
                # 제네릭 타입인 경우
                from .proxy import AsyncProxy

                if origin is AsyncProxy:
                    is_async_proxy = True
                    args = get_args(hint)
                    if args:
                        actual_type = args[0]  # AsyncProxy[T]에서 T 추출

            # 내장 타입은 제외 (str, int, list 등)
            if _is_builtin_type(actual_type):
                continue

            # 문자열(forward reference)은 나중에 런타임에 해결
            deps.append(
                DependencyInfo(
                    field_name=name,
                    field_type=actual_type,
                    is_optional=is_optional,
                    default_value=default if is_optional else None,
                    is_async_proxy=is_async_proxy,
                    raw_type_hint=hint,
                )
            )

        return deps

    def _resolve_type_hints(self) -> dict[str, type]:
        """타입 힌트 해결 (forward reference 포함)"""
        hints: dict[str, type] = {}

        # __annotations__에서 직접 가져오기
        annotations = getattr(self.target, "__annotations__", {})

        # globalns 구성 (모듈 글로벌 + 클래스 자신 + 부모 클래스 모듈들)
        module = inspect.getmodule(self.target)
        globalns: dict[str, Any] = {}
        if module:
            globalns.update(vars(module))
        globalns[self.target.__name__] = self.target

        # 부모 클래스들의 모듈도 추가 (상속받은 필드의 forward reference 해결용)
        for base in self.target.__mro__[1:]:
            if base is object:
                continue
            base_module = inspect.getmodule(base)
            if base_module:
                globalns.update(vars(base_module))

        for name, hint in annotations.items():
            if isinstance(hint, str):
                # forward reference - 문자열로 저장하고 나중에 해결
                # Optional이나 Union 처리
                hint_str = hint.strip()
                if hint_str.endswith(" | None") or hint_str.startswith("Optional["):
                    # Optional 타입은 스킵하지 않고 저장
                    pass
                hints[name] = hint  # type: ignore - 문자열로 저장
            else:
                hints[name] = hint

        # get_type_hints로 해결 시도
        try:
            resolved = get_type_hints(
                self.target, globalns=globalns, include_extras=True
            )
            hints.update(resolved)
        except Exception:
            pass

        return hints

    async def create_instance(
        self,
        manager: "ContainerManager",
        resolved_deps: dict[str, Any] | None = None,
    ) -> T:
        """
        인스턴스 생성.

        Args:
            manager: ContainerManager (다른 의존성 resolve용)
            resolved_deps: 미리 resolve된 의존성 (선택적)

        Returns:
            생성된 인스턴스
        """
        if self.factory:
            # @Factory 메서드로 생성
            instance = await self._create_from_factory(manager)
        else:
            # 직접 생성
            instance = await self._create_direct(manager, resolved_deps)

        # @PostConstruct 호출
        await LifecycleManager.invoke_post_construct(instance)

        return instance

    async def _create_direct(
        self,
        manager: "ContainerManager",
        resolved_deps: dict[str, Any] | None = None,
    ) -> T:
        """직접 인스턴스 생성 (생성자 호출)"""
        # 생성자 파라미터 분석
        init_params = self._get_init_params()

        # 생성자에 주입할 인자 준비 (async)
        init_args: dict[str, Any] = {}
        for param_name, param_type in init_params.items():
            if resolved_deps and param_name in resolved_deps:
                init_args[param_name] = resolved_deps[param_name]
            elif not _is_builtin_type(param_type):
                # 컴포넌트 타입이면 resolve (async)
                init_args[param_name] = await manager.get_instance_async(param_type)

        # 인스턴스 생성
        instance = self.target(**init_args)

        # 필드 주입 (Lazy Proxy로)
        await self._inject_fields(instance, manager)

        return instance

    async def _create_from_factory(self, manager: "ContainerManager") -> T:
        """@Factory 메서드로 인스턴스 생성"""
        if not self.factory:
            raise RuntimeError("No factory method")

        # Configuration 인스턴스 획득 (async)
        config_instance = await manager.get_instance_async(self.factory.owner)

        # 팩토리 메서드 파라미터 준비 (async)
        factory_args: dict[str, Any] = {}
        for dep in self.factory.dependencies:
            factory_args[dep.field_name] = await manager.get_instance_async(
                dep.field_type
            )

        # 팩토리 메서드 호출
        method = getattr(config_instance, self.factory.method.__name__)
        result = method(**factory_args)

        # async factory 지원
        if inspect.iscoroutine(result):
            result = await result

        return result

    async def _inject_fields(
        self,
        instance: T,
        manager: "ContainerManager",
    ) -> None:
        """필드에 의존성 주입

        - AsyncProxy[T]로 선언된 필드: AsyncProxy로 주입 (await resolve() 필요)
        - CALL 스코프 + async factory: AsyncProxy 필수 (에러 발생)
        - SINGLETON/REQUEST/CALL: LazyProxy로 주입 (순환 의존성 지원)
        
        CALL 스코프 async factory 컴포넌트는 반드시 AsyncProxy[T]로 선언해야 합니다.
        """
        from .proxy import AsyncProxy, LazyProxy
        from .scope import ScopeEnum

        for dep in self.dependencies:
            # 이미 값이 있으면 스킵
            current_value = getattr(instance, dep.field_name, _MISSING)
            if current_value is not _MISSING and current_value is not None:
                continue

            # forward reference 해결
            field_type = self._resolve_forward_ref(dep.field_type, manager)
            if field_type is None:
                if dep.is_optional:
                    continue
                raise RuntimeError(
                    f"Cannot resolve forward reference '{dep.field_type}' "
                    f"for field '{dep.field_name}' "
                    f"in component '{self.target.__name__}'"
                )

            # 의존성 컨테이너 찾기
            dep_container = manager.get_container(field_type)
            if dep_container is None:
                if dep.is_optional:
                    continue
                type_name = (
                    field_type.__name__
                    if isinstance(field_type, type)
                    else str(field_type)
                )
                raise RuntimeError(
                    f"Cannot resolve dependency '{dep.field_name}' "
                    f"of type '{type_name}' "
                    f"for component '{self.target.__name__}'"
                )

            # CALL 스코프 + async factory 체크
            if dep_container.scope == ScopeEnum.CALL and not dep.is_async_proxy:
                # async factory인지 확인
                is_async_factory = (
                    dep_container.factory is not None
                    and inspect.iscoroutinefunction(dep_container.factory.method)
                )
                if is_async_factory:
                    raise RuntimeError(
                        f"CALL scoped async factory '{field_type.__name__}' must be declared as "
                        f"AsyncProxy[{field_type.__name__}] in '{self.target.__name__}.{dep.field_name}'. "
                        f"Use: {dep.field_name}: AsyncProxy[{field_type.__name__}]"
                    )

            # AsyncProxy[T]로 명시적으로 선언된 경우: AsyncProxy 주입
            if dep.is_async_proxy:
                async_proxy: AsyncProxy[Any] = AsyncProxy(dep_container, manager)
                setattr(instance, dep.field_name, async_proxy)
            else:
                # SINGLETON/REQUEST/CALL 모두: LazyProxy로 주입
                # CALL 스코프는 접근 시점에 컨텍스트 체크 후 resolve
                proxy: LazyProxy[Any] = LazyProxy(dep_container, manager)
                setattr(instance, dep.field_name, proxy)

    def _resolve_forward_ref(
        self,
        type_hint: type | str,
        manager: "ContainerManager",
    ) -> type | None:
        """forward reference를 실제 타입으로 해결"""
        if isinstance(type_hint, type):
            return type_hint

        if not isinstance(type_hint, str):
            return None

        # 문자열에서 타입명 추출 (Optional, Union 등 처리)
        type_str = type_hint.strip()

        # "TypeName | None" 형식 처리
        if " | None" in type_str:
            type_str = type_str.replace(" | None", "").strip()

        # "Optional[TypeName]" 형식 처리
        if type_str.startswith("Optional[") and type_str.endswith("]"):
            type_str = type_str[9:-1].strip()

        # 등록된 컨테이너에서 타입 찾기
        for container in manager.get_all_containers():
            if container.target.__name__ == type_str:
                return container.target

        return None

    def _get_init_params(self) -> dict[str, type]:
        """__init__ 파라미터 타입 분석"""
        try:
            hints = get_type_hints(self.target.__init__)
        except Exception:
            return {}

        params: dict[str, type] = {}
        sig = inspect.signature(self.target.__init__)

        for name, param in sig.parameters.items():
            if name == "self":
                continue
            if name in hints:
                params[name] = hints[name]

        return params

    def __repr__(self) -> str:
        return (
            f"Container("
            f"target={self.target.__name__}, "
            f"scope={self.scope.name}, "
            f"deps={len(self.dependencies)})"
        )


class _Missing:
    """기본값 없음을 나타내는 센티널"""

    def __repr__(self) -> str:
        return "<MISSING>"


_MISSING = _Missing()


def _is_builtin_type(t: type) -> bool:
    """내장 타입 여부 확인"""
    if t is type(None):
        return True

    # 기본 타입들
    builtins = (str, int, float, bool, bytes, list, dict, set, tuple, type(None))

    try:
        if isinstance(t, type) and issubclass(t, builtins):
            return True
    except TypeError:
        pass

    # typing 모듈 타입 (List, Dict 등)
    origin = getattr(t, "__origin__", None)
    if origin is not None:
        return origin in (list, dict, set, tuple)

    return False


def analyze_factory_method[T](
    method: Callable[..., T],
    owner: type,
) -> FactoryInfo[T]:
    """@Factory 메서드 분석"""
    # 반환 타입 추출
    hints = get_type_hints(method)
    return_type = hints.get("return")
    if return_type is None:
        raise ValueError(f"Factory method {method.__name__} must have return type hint")

    # 파라미터 의존성 분석
    deps: list[DependencyInfo] = []
    sig = inspect.signature(method)

    for name, param in sig.parameters.items():
        if name == "self":
            continue
        if name in hints and not _is_builtin_type(hints[name]):
            deps.append(
                DependencyInfo(
                    field_name=name,
                    field_type=hints[name],
                    is_optional=param.default is not inspect.Parameter.empty,
                    default_value=(
                        param.default
                        if param.default is not inspect.Parameter.empty
                        else None
                    ),
                )
            )

    return FactoryInfo(
        method=method,
        return_type=return_type,
        owner=owner,
        dependencies=deps,
    )
