from dataclasses import dataclass
import inspect
from typing import Any, get_type_hints
from uuid import uuid4
from .manager import get_container_registry


class Element[T]:
    key: str
    value: T


@dataclass
class DependencyInfo:
    """의존성 정보"""

    field_name: str  # 필드명
    field_type: type  # 타입 (AsyncProxy[T]인 경우 T)
    is_optional: bool = False  # Optional 여부
    default_value: Any = None  # 기본값
    is_async_proxy: bool = False  # AsyncProxy[T]로 선언되었는지 여부
    raw_type_hint: Any = None  # 원본 타입 힌트 (AsyncProxy[T] 등)


class Container[T]:
    instance: T | None
    kls: type[T]
    elements: list[Element]
    dependencies: list[DependencyInfo]

    def __init__(self, kls: type[T]):
        self.kls = kls
        self.instance = None
        self.elements = []
        self.dependencies = self._analyze_dependencies()

    async def initialize(self) -> T:
        """컨테이너 초기화 메서드 (비동기)"""
        return self.kls()

    async def shutdown(self) -> None:
        """컨테이너 종료 메서드 (비동기)"""

    @classmethod
    def register[U: type](cls, kls: U) -> "Container[U]":
        if not hasattr(kls, "__component_id__"):
            kls.__component_id__ = str(uuid4())

        registry = get_container_registry()

        if kls not in registry:
            registry[kls] = {}

        if kls.__component_id__ not in registry[kls]:
            registry[kls][kls.__component_id__] = Container(kls)
        container = registry[kls][kls.__component_id__]
        return container

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
            default = getattr(self.kls, name, _MISSING)
            is_optional = default is not _MISSING

            actual_type = hint

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
                    is_async_proxy=False,
                    raw_type_hint=hint,
                )
            )

        return deps

    def _resolve_type_hints(self) -> dict[str, type]:
        """타입 힌트 해결 (forward reference 포함)"""
        hints: dict[str, type] = {}

        # __annotations__에서 직접 가져오기
        annotations = getattr(self.kls, "__annotations__", {})

        # globalns 구성 (모듈 글로벌 + 클래스 자신 + 부모 클래스 모듈들)
        module = inspect.getmodule(self.kls)
        globalns: dict[str, Any] = {}
        if module:
            globalns.update(vars(module))
        globalns[self.kls.__name__] = self.kls
        # 부모 클래스들의 모듈도 추가 (상속받은 필드의 forward reference 해결용)
        for base in self.kls.__mro__[1:]:
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
            resolved = get_type_hints(self.kls, globalns=globalns, include_extras=True)
            hints.update(resolved)
        except Exception:
            pass

        return hints


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
