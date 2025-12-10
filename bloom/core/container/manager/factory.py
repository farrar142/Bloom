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
        
        지원하는 의존성 패턴:
        - 기본: field: SomeType
        - Optional: field: Optional[SomeType] 또는 field: SomeType | None
        - Autowired: field: SomeType = Autowired(qualifier="name", required=False, lazy=True)
        """
        from ..base import DependencyInfo
        from ...injection import AutowiredField, get_autowired_info

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
            
            # Autowired 마커 확인
            autowired_info = get_autowired_info(default)
            
            # Optional 타입 분석
            actual_type, is_optional_type = self._unwrap_optional(hint)
            
            # is_optional 결정:
            # 1. Optional[T] 타입이면 optional
            # 2. Autowired(required=False)면 optional
            # 3. 기본값이 있으면 optional (Autowired 제외)
            is_optional = is_optional_type
            if autowired_info is not None:
                is_optional = not autowired_info.required
            elif default is not _MISSING and autowired_info is None:
                is_optional = True

            # 내장 타입은 제외 (str, int, list 등)
            if _is_builtin_type(actual_type):
                continue

            deps.append(
                DependencyInfo(
                    field_name=name,
                    field_type=actual_type,
                    is_optional=is_optional,
                    default_value=default if default is not _MISSING and autowired_info is None else None,
                    is_async_proxy=False,
                    raw_type_hint=hint,
                    qualifier=autowired_info.qualifier if autowired_info else None,
                    is_lazy=autowired_info.lazy if autowired_info else False,
                )
            )

        return deps
    
    def _unwrap_optional(self, hint: type) -> tuple[type, bool]:
        """Optional[T] 또는 T | None 타입에서 실제 타입 추출
        
        Returns:
            (actual_type, is_optional)
        """
        import typing
        import types
        
        origin = getattr(hint, "__origin__", None)
        args = getattr(hint, "__args__", ())
        
        # Python 3.10+ T | None (types.UnionType)
        if isinstance(hint, types.UnionType):
            args = hint.__args__
            non_none_args = [a for a in args if a is not type(None)]
            if len(non_none_args) == 1 and type(None) in args:
                return non_none_args[0], True
        
        # typing.Optional[T] == typing.Union[T, None]
        if origin is typing.Union:
            # None이 args에 있으면 Optional
            non_none_args = [a for a in args if a is not type(None)]
            if len(non_none_args) == 1 and type(None) in args:
                return non_none_args[0], True
        
        return hint, False

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
        """일반 의존성 주입 (LazyProxy 사용)
        
        지원하는 기능:
        - @Qualifier: 특정 이름의 빈 선택
        - @Primary: 동일 타입 여러 빈 중 기본 선택
        - Optional: 빈이 없으면 None
        - Autowired(lazy=True): 명시적 LazyProxy
        """
        from ..proxy import LazyProxy
        from ...injection import AutowiredField

        for dep in container.dependencies:
            # 이미 값이 설정되어 있으면 스킵 (단, AutowiredField 마커는 제외)
            current_value = getattr(instance, dep.field_name, None)
            if current_value is not None and not isinstance(current_value, AutowiredField):
                continue

            # Factory 타입은 나중에 처리
            if self._is_factory_type(dep.field_type):
                continue

            try:
                # Qualifier가 있으면 이름으로 찾기
                if dep.qualifier:
                    dep_container = self._find_by_qualifier(dep.field_type, dep.qualifier)
                else:
                    # Primary 우선, 없으면 일반 타입 매칭
                    dep_container = self._find_by_type_with_primary(dep.field_type)
            except ValueError:
                if dep.is_optional:
                    setattr(instance, dep.field_name, None)
                    continue
                raise RuntimeError(
                    f"Cannot resolve dependency '{dep.field_name}: {dep.field_type.__name__}' "
                    f"for '{container.kls.__name__}'"
                    + (f" (qualifier='{dep.qualifier}')" if dep.qualifier else "")
                )

            # LazyProxy에 registry 전달
            setattr(instance, dep.field_name, LazyProxy(dep_container, self._registry))
    
    def _find_by_qualifier(self, field_type: type, qualifier: str) -> "Container":
        """Qualifier 이름으로 빈 찾기
        
        1. 정확한 타입 + 이름 매칭
        2. 서브타입 + 이름 매칭
        """
        from ...injection import NAME_ELEMENT_KEY
        from .types import containers
        
        # 모든 컨테이너에서 이름이 일치하는 것 찾기
        for container_type, container_dict in containers.items():
            for container in container_dict.values():
                # 이름 확인
                name = container.get_element(NAME_ELEMENT_KEY, None)
                if name != qualifier:
                    continue
                
                # 타입 호환성 확인
                if isinstance(container_type, type) and issubclass(container_type, field_type):
                    return container
                if container_type == field_type:
                    return container
        
        raise ValueError(f"No bean found with qualifier '{qualifier}' for type {field_type.__name__}")
    
    def _find_by_type_with_primary(self, field_type: type) -> "Container":
        """타입으로 빈 찾기 (@Primary 우선)
        
        1. 정확한 타입 매칭 시도
        2. 서브타입 중 @Primary 찾기
        3. 서브타입 중 하나 반환 (여러 개면 에러)
        """
        from ...injection import PRIMARY_ELEMENT_KEY
        from .types import containers
        
        # 1. 정확한 타입 매칭
        if field_type in containers:
            container_dict = containers[field_type]
            if container_dict:
                return next(iter(container_dict.values()))
        
        # 2. 서브타입 찾기
        candidates: list["Container"] = []
        primary_candidate: "Container | None" = None
        
        for container_type, container_dict in containers.items():
            if not isinstance(container_type, type):
                continue
            
            try:
                if issubclass(container_type, field_type):
                    for container in container_dict.values():
                        candidates.append(container)
                        # Primary 체크
                        if container.get_element(PRIMARY_ELEMENT_KEY, False):
                            primary_candidate = container
            except TypeError:
                continue
        
        # Primary가 있으면 반환
        if primary_candidate:
            return primary_candidate
        
        # 후보가 하나면 반환
        if len(candidates) == 1:
            return candidates[0]
        
        # 후보가 여러 개면 에러
        if len(candidates) > 1:
            candidate_names = [c.kls.__name__ for c in candidates]
            raise ValueError(
                f"Multiple beans found for type {field_type.__name__}: {candidate_names}. "
                f"Use @Primary or @Qualifier to disambiguate."
            )
        
        raise ValueError(f"No container registered for type: {field_type.__name__}")

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
