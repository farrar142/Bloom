"""
ContainerFactory - 컨테이너 생성/의존성 분석 담당
"""

import inspect
from typing import TYPE_CHECKING, Any, get_type_hints

from .types import COMPONENT_ID

if TYPE_CHECKING:
    from ..base import Container, DependencyInfo
    from .registry import ContainerRegistry


class ContainerFactory:
    """컨테이너 생성/분석 담당

    책임:
    - 의존성 분석: analyze_dependencies()
    - 타입 힌트 해결: _resolve_type_hints()
    - 의존성 주입: inject_dependencies()
    """

    def __init__(
        self,
        instances: dict[COMPONENT_ID, object],
        registry: "ContainerRegistry",
    ) -> None:
        self._instances = instances
        self._registry = registry
        self._factory_types_cache: set[type] | None = None

    # =========================================================================
    # 의존성 분석
    # =========================================================================

    def analyze_dependencies[T](
        self, container: "Container[T]"
    ) -> list["DependencyInfo"]:
        """컨테이너의 클래스 필드에서 의존성 분석

        Container는 데이터만 저장하고, 분석 로직은 여기서 담당합니다.
        """
        from ..base import DependencyInfo

        deps: list[DependencyInfo] = []
        kls = container.kls

        # 타입 힌트 해결
        try:
            hints = self._resolve_type_hints(kls)
        except Exception:
            hints = {}

        # 클래스 변수 중 타입힌트가 있는 것들
        for name, hint in hints.items():
            if name.startswith("_"):
                continue

            # 기본값 확인
            default = getattr(kls, name, _MISSING)
            is_optional = default is not _MISSING

            actual_type = hint

            # 내장 타입은 제외 (str, int, list 등)
            if _is_builtin_type(actual_type):
                continue

            deps.append(
                DependencyInfo(
                    field_name=name,
                    field_type=actual_type,
                    is_optional=is_optional,
                    default_value=default if is_optional else None,
                    is_async_proxy=False,
                    raw_type_hint=hint,
                )
            )

        return deps

    def _resolve_type_hints(self, kls: type) -> dict[str, type]:
        """타입 힌트 해결 (forward reference 포함)"""
        hints: dict[str, type] = {}

        # __annotations__에서 직접 가져오기
        annotations = getattr(kls, "__annotations__", {})

        # globalns 구성 (모듈 글로벌 + 클래스 자신 + 부모 클래스 모듈들)
        module = inspect.getmodule(kls)
        globalns: dict[str, Any] = {}
        if module:
            globalns.update(vars(module))
        globalns[kls.__name__] = kls

        # 부모 클래스들의 모듈도 추가 (상속받은 필드의 forward reference 해결용)
        for base in kls.__mro__[1:]:
            if base is object:
                continue
            base_module = inspect.getmodule(base)
            if base_module:
                globalns.update(vars(base_module))

        for name, hint in annotations.items():
            if isinstance(hint, str):
                # forward reference - 문자열로 저장하고 나중에 해결
                hints[name] = hint  # type: ignore
            else:
                hints[name] = hint

        # get_type_hints로 해결 시도
        try:
            resolved = get_type_hints(kls, globalns=globalns, include_extras=True)
            hints.update(resolved)
        except Exception:
            pass

        return hints

    # =========================================================================
    # 의존성 주입
    # =========================================================================

    def inject_dependencies[T](self, container: "Container[T]", instance: T) -> None:
        """일반 의존성 주입 (LazyProxy 사용)"""
        from ..proxy import LazyProxy

        for dep in container.dependencies:
            if getattr(instance, dep.field_name, None) is not None:
                continue

            # Factory 타입은 나중에 처리
            if self._is_factory_type(dep.field_type):
                continue

            try:
                dep_container = self._registry.container(type=dep.field_type)
            except ValueError:
                if dep.is_optional:
                    continue
                raise RuntimeError(
                    f"Cannot resolve dependency '{dep.field_name}' "
                    f"for '{container.kls.__name__}'"
                )

            # LazyProxy에 registry 전달
            setattr(instance, dep.field_name, LazyProxy(dep_container, self._registry))

    def _is_factory_type(self, field_type: type) -> bool:
        """타입이 Factory로 등록되어 있는지 확인"""
        # 캐시 사용
        if self._factory_types_cache is None:
            self._factory_types_cache = set(self._registry.factory_types())
        return field_type in self._factory_types_cache


# =============================================================================
# 헬퍼 클래스 및 함수
# =============================================================================


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
