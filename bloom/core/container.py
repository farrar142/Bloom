from dataclasses import dataclass
import inspect
from typing import Any, Callable, Concatenate, get_type_hints
from uuid import uuid4
from functools import reduce
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


class HandlerWrapper[**P, T: type, R]:
    pass


class Container[T]:
    instance: T | None
    kls: type[T]
    elements: list[Element]
    dependencies: list[DependencyInfo]
    _handler_methods: dict[str, "HandlerContainer"]  # 핸들러 메서드 캐시

    def __init__(self, kls: type[T], component_id: str):
        self.kls = kls
        self.component_id = component_id
        self.instance = None
        self.elements = []
        self.dependencies = self._analyze_dependencies()
        self._handler_methods = {}

    # def _find_handler_methods(self) -> dict[str, "HandlerContainer"]:
    #     """클래스에서 @Handler가 달린 메서드들을 찾아서 반환"""
    #     handlers: dict[str, HandlerContainer] = {}
    #     registry = get_container_registry()

    #     for name in dir(self.kls):
    #         if name.startswith("_"):
    #             continue
    #         attr = getattr(self.kls, name, None)
    #         if attr is None:
    #             continue

    #         # __is_handler__ 마커가 있는지 확인
    #         if attr in registry:
    #             component_id = getattr(attr, "__component_id__", None)
    #             if component_id and component_id in registry[attr]:
    #                 handlers[name] = registry[attr][component_id]

    #     return handlers

    async def initialize(self) -> T:
        """컨테이너 초기화 메서드 (비동기)"""
        instance = self.kls()

        # @Handler 메서드들을 초기화된 버전으로 교체
        await self._bind_handlers(instance)

        return instance

    async def _bind_handlers(self, instance: T) -> None:
        """인스턴스의 @Handler 메서드들을 초기화된 버전으로 바인딩"""
        import types

        for method_name, handler_container in self._handler_methods.items():
            # HandlerContainer에서 초기화된 메서드(wrapper 적용된) 가져오기
            initialized_func = await handler_container.initialize()

            # 인스턴스에 바인딩된 메서드로 만들기
            bound_method = types.MethodType(initialized_func, instance)

            # 인스턴스의 메서드 교체
            setattr(instance, method_name, bound_method)

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
            registry[kls][kls.__component_id__] = Container(kls, kls.__component_id__)
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


type Method[**P, T, R] = Callable[Concatenate[T, P], R]


class HandlerContainer[**P, T, R](Container[Method[P, T, R]]):
    """핸들러 컨테이너 클래스"""

    wrappers: list[Callable[[Method[P, T, R]], Method[P, T, R]]]

    def __init__(self, kls: Method[P, T, R], component_id: str) -> None:
        super().__init__(kls, component_id)
        self.func = kls
        self.wrappers = []

    async def initialize(self) -> Method[P, T, R]:
        final_method = reduce(
            lambda next_func, wrapper_factory: wrapper_factory(next_func),
            reversed(self.wrappers),
            self.func,
        )
        return final_method

    @classmethod
    def register(cls, func: Method[P, T, R]) -> "HandlerContainer[P, T, R]":
        if not hasattr(func, "__component_id__"):
            func.__component_id__ = str(uuid4())

        registry = get_container_registry()

        if func not in registry:
            registry[func] = {}

        if func.__component_id__ not in registry[func]:

            registry[func][func.__component_id__] = HandlerContainer(
                func, func.__component_id__
            )
        container: HandlerContainer[P, T, R] = registry[func][
            func.__component_id__
        ]  # type:ignore

        def first_wrapper(wrapper_func: Method[P, T, R]) -> Method[P, T, R]:
            return wrapper_func

        container.wrappers.append(first_wrapper)
        return container


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
