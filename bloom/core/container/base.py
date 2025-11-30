"""Container 베이스 클래스"""

from typing import (
    Any,
    Callable,
    Self,
    Optional,
    cast,
    overload,
    TYPE_CHECKING,
    get_type_hints,
)

if TYPE_CHECKING:
    from ..manager import ContainerManager

from ..manager import get_current_manager, try_get_current_manager
from .element import Element


class Container[T]:
    """
    @Component
    class MyService:
        pass
    에서 MyService 클래스에 대한 컨테이너 역할을 한다
    Container 인스턴스는 MyService.__container__ 속성으로 접근 가능하다
    initialize후에 인스턴스가 생성되고
    인스턴스에 필드 주입이 이루어진 후
    글로벌인스턴스레지스트리에 인스턴스가 저장된다
    """

    def __init__(self, target: type[T]):
        self.target = target
        self.elements = list[Element[T]]()
        self.element = Element[T]()  # 단일 element (메타데이터 저장용)
        self.owner_cls: type | None = None  # Factory/Handler의 부모 클래스
        self.manager: "ContainerManager | None" = None  # scan 시점에 주입됨

    def _get_manager(self) -> "ContainerManager":
        """manager 반환 (없으면 현재 활성 매니저 반환)"""
        if self.manager is not None:
            return self.manager
        return get_current_manager()

    def add_elements(self, *elements: Element[T]) -> None:
        self.elements.extend(elements)

    def __repr__(self) -> str:
        return f"Container(target={self.target.__name__}, elements={self.elements})"

    @classmethod
    def get_container(cls, obj: Any) -> Self | None:
        """
        객체에 연결된 컨테이너를 반환한다.

        Args:
            obj: 클래스, 메서드, 또는 함수

        Returns:
            Container 인스턴스 또는 None (컨테이너가 없는 경우)
        """
        container = getattr(obj, "__container__", None)
        if container is not None and isinstance(container, cls):
            return container
        return None

    def get_dependencies(self) -> list[type]:
        """이 컨테이너가 의존하는 타입들을 반환

        Note: 모든 필드 주입이 LazyFieldProxy로 래핑되므로,
        순환 의존성은 자동으로 해결됩니다. 이 메서드는 주로
        Factory 파라미터 의존성 분석에 사용됩니다.
        """
        from typing import get_type_hints

        dependencies: list[type] = []

        # get_type_hints로 forward reference 해석
        try:
            hints = get_type_hints(self.target)
        except Exception:
            # 해석 실패 시 원본 어노테이션 사용
            hints = getattr(self.target, "__annotations__", {})

        for field_type in hints.values():
            # 문자열(forward ref)이면 건너뜀 (해석 실패)
            if isinstance(field_type, str):
                continue
            # 타입이 아니면 건너뜀
            if not isinstance(field_type, type):
                continue
            dependencies.append(field_type)
        return dependencies

    def get_lazy_dependencies(self) -> list[type]:
        """이 컨테이너가 Lazy[T]로 명시적으로 의존하는 타입들을 반환

        Lazy[T] 타입 힌트에서 T를 추출합니다.
        Note: 모든 필드가 기본적으로 Lazy이므로 이 메서드는
        명시적으로 Lazy[T]로 선언된 필드만 반환합니다.
        """
        from typing import get_origin, get_args
        from ..lazy import is_lazy_wrapper_type, get_lazy_inner_type

        lazy_deps = []

        for field_type in getattr(self.target, "__annotations__", {}).values():
            # Lazy[T] 타입 힌트 처리
            if is_lazy_wrapper_type(field_type):
                inner_type = get_lazy_inner_type(field_type)
                if inner_type is not None and isinstance(inner_type, type):
                    lazy_deps.append(inner_type)

        return lazy_deps

    def _get_cached_instance(self) -> T | None:
        """캐시된 인스턴스가 있으면 반환"""
        # 정확한 타입으로 등록된 인스턴스 찾기
        instances = self._get_manager().instance_registry.get(self.target, [])
        if instances:
            return instances[0]
        return None

    def _inject_dependencies(self, annotations: dict[str, type]) -> dict[str, Any]:
        """어노테이션 기반으로 의존성을 주입하여 kwargs 반환"""
        from typing import ForwardRef, get_type_hints
        from ..lazy import (
            LazyFieldProxy,
            is_lazy_wrapper_type,
            get_lazy_inner_type,
        )
        from ...config.env import is_env_type, resolve_env_value

        manager = self._get_manager()
        kwargs = {}
        for name, dep_type in annotations.items():
            if name == "return":
                continue
            # 환경변수 타입 처리 (Env[Literal["KEY"]])
            if is_env_type(dep_type):
                env_value = resolve_env_value(dep_type)
                if env_value is not None:
                    kwargs[name] = env_value
                continue

            # Lazy[T] 필드 타입 처리 - 명시적 Lazy 선언
            if is_lazy_wrapper_type(dep_type):
                inner_type = get_lazy_inner_type(dep_type)
                if inner_type is not None:
                    # ForwardRef 해결 (문자열 타입 참조)
                    if isinstance(inner_type, ForwardRef):
                        # __forward_arg__가 문자열 타입 이름
                        type_name = inner_type.__forward_arg__
                        # 현재 등록된 모든 컨테이너에서 타입 이름으로 검색
                        resolved_type = None
                        for t in manager.container_registry.keys():
                            if t.__name__ == type_name:
                                resolved_type = t
                                break
                        if resolved_type is None:
                            raise Exception(
                                f"Cannot resolve Lazy['{type_name}']: type not found in registry"
                            )
                        inner_type = resolved_type

                    # LazyFieldProxy 생성 - 투명 프록시로 동작
                    from .element import Scope as ScopeEnum, ScopeElement

                    # 컨테이너에서 Scope 정보 가져오기
                    inner_scope = ScopeEnum.SINGLETON
                    if inner_container := manager.get_container(inner_type):
                        for elem in inner_container.elements:
                            if isinstance(elem, ScopeElement):
                                inner_scope = elem.scope
                                break

                    def make_resolver(m: "ContainerManager", t: type, s: ScopeEnum):
                        def resolver():
                            # PROTOTYPE은 항상 새 인스턴스 생성
                            if s == ScopeEnum.PROTOTYPE:
                                if container := m.get_container(t):
                                    return container._create_instance()
                                raise Exception(
                                    f"Cannot resolve {t.__name__}: no container found"
                                )

                            # SINGLETON: 캐시 확인
                            instance = m.get_instance(t, raise_exception=False)
                            if instance is not None:
                                return instance
                            if container := m.get_container(t):
                                return container.initialize_instance()
                            raise Exception(
                                f"Cannot resolve Lazy[{t.__name__}]: no container found"
                            )

                        return resolver

                    kwargs[name] = LazyFieldProxy(
                        make_resolver(manager, inner_type, inner_scope),
                        inner_type,
                        inner_scope,
                    )
                continue

            # 모든 필드는 기본적으로 LazyFieldProxy로 주입 (기본 Lazy 동작)
            if dep_container := manager.get_container(dep_type):
                from .element import Scope as ScopeEnum, ScopeElement

                scope = ScopeEnum.SINGLETON  # 기본값
                for elem in dep_container.elements:
                    if isinstance(elem, ScopeElement):
                        scope = elem.scope
                        break

                # PROTOTYPE이 아닌 경우에만 캐시된 인스턴스 사용
                if scope != ScopeEnum.PROTOTYPE:
                    existing_instance = manager.get_instance(
                        dep_type, raise_exception=False
                    )
                    if existing_instance is not None:
                        kwargs[name] = existing_instance
                        continue

                # LazyFieldProxy로 주입 (기본 Lazy 동작)
                # PROTOTYPE: 매번 새 인스턴스 생성
                # SINGLETON: 캐시 확인 후 없으면 생성
                def make_default_resolver(m: "ContainerManager", t: type, s: ScopeEnum):
                    def resolver():
                        # PROTOTYPE은 항상 새 인스턴스 생성
                        if s == ScopeEnum.PROTOTYPE:
                            if container := m.get_container(t):
                                return container._create_instance()
                            raise Exception(
                                f"Cannot resolve {t.__name__}: no container found"
                            )

                        # SINGLETON은 캐시 확인
                        instance = m.get_instance(t, raise_exception=False)
                        if instance is not None:
                            return instance
                        if container := m.get_container(t):
                            return container.initialize_instance()
                        raise Exception(
                            f"Cannot resolve {t.__name__}: no container found"
                        )

                    return resolver

                kwargs[name] = LazyFieldProxy(
                    make_default_resolver(manager, dep_type, scope), dep_type, scope
                )
            else:
                # 컨테이너가 없으면 기존 인스턴스 확인
                existing_instance = manager.get_instance(
                    dep_type, raise_exception=False
                )
                if existing_instance is not None:
                    kwargs[name] = existing_instance
        return kwargs

    def _create_instance(self) -> T:
        """실제 인스턴스 생성 로직"""
        # get_type_hints를 사용하여 forward reference 해결
        try:
            annotations = get_type_hints(self.target)
        except Exception:
            # 타입 힌트 해결 실패 시 __annotations__ 사용
            annotations = getattr(self.target, "__annotations__", {})
        kwargs = self._inject_dependencies(annotations)
        instance = self.target()
        instance.__dict__.update(kwargs)
        return instance

    def invoke_pre_destroy(self, instance: T) -> None:
        """@PreDestroy 메서드들 호출 (ContainerManager.lifecycle에 위임)"""
        self._get_manager().lifecycle.invoke_pre_destroy(self, instance)

    def initialize_instance(self) -> T:
        """인스턴스 초기화 (캐시 확인 후 생성)"""
        if instance := self._get_cached_instance():
            return instance
        instance = self._create_instance()
        # PostConstruct 호출
        self._get_manager().lifecycle.invoke_post_construct(self, instance)
        return instance

    def _transfer_elements_to(self, target_container: "Container") -> None:
        """현재 컨테이너의 Element들을 target_container로 이전"""
        for element in self.elements:
            if not target_container.has_element(type(element)):
                target_container.add_element(element)

    @classmethod
    def _get_mro_index(cls, container_type: type["Container"]) -> int:
        """
        Container 클래스로부터의 MRO 인덱스 반환

        MRO 인덱스가 높을수록 더 구체적(하위) 타입입니다.
        - Container: 0
        - CallableContainer: 1
        - HandlerContainer: 2
        - HttpMethodHandlerContainer: 3
        """
        return container_type.__mro__.index(Container)

    @classmethod
    def _is_more_specific_than(cls, other: type["Container"]) -> bool:
        """
        현재 클래스가 other보다 더 구체적(하위)인지 확인

        사용 예:
            HandlerContainer._is_more_specific_than(Container)  # True
            Container._is_more_specific_than(HandlerContainer)  # False
        """
        return cls._get_mro_index(cls) > cls._get_mro_index(other)

    @classmethod
    def _apply_override_rules(
        cls,
        target: Any,
        create_new: Callable[[], Self],
    ) -> Self:
        """
        컨테이너 오버라이드 규칙을 적용하여 컨테이너를 생성하거나 반환

        오버라이드 규칙:
        1. 기존 컨테이너가 없으면: 새로 생성
        2. 동일 타입이면: 기존 컨테이너 반환
        3. 하위 컨테이너가 이미 존재하면: 하위 컨테이너 반환 (상위는 Element만 추가 가능)
        4. 상위 컨테이너가 이미 존재하면: 하위 컨테이너로 교체하고 Element 이전

        MRO 인덱스가 높을수록 더 구체적(하위) 타입:
        - Container: 0
        - HandlerContainer: 1
        - HttpMethodHandlerContainer: 2

        Args:
            target: 컨테이너를 연결할 대상 (클래스 또는 메서드)
            create_new: 새 컨테이너를 생성하는 함수

        Returns:
            적용된 컨테이너
        """
        existing_container = getattr(target, "__container__", None)

        if existing_container is None:
            # 기존 컨테이너 없음 → 새로 생성
            container = create_new()
            setattr(target, "__container__", container)
            if manager := try_get_current_manager():
                manager.register_container(container)
            return container

        # 기존 컨테이너가 있는 경우 오버라이드 규칙 적용
        if isinstance(existing_container, cls):
            # 동일 타입 → 기존 컨테이너 반환
            return existing_container

        if isinstance(existing_container, Container):
            existing_type = type(existing_container)

            if cls._is_more_specific_than(existing_type):
                # cls가 existing보다 더 구체적(하위)임
                # → 하위 컨테이너로 교체하고, 상위 컨테이너의 Element들을 이전
                new_container = create_new()
                existing_container._transfer_elements_to(new_container)
                setattr(target, "__container__", new_container)
                if manager := try_get_current_manager():
                    manager.unregister_container(existing_container)
                    manager.register_container(new_container)
                return new_container
            else:
                # existing_container가 cls보다 더 구체적(하위)이거나 동등
                # → 하위 컨테이너를 유지하고 반환
                return existing_container  # type: ignore

        # 다른 타입의 객체가 있는 경우 (예상치 못한 상황)
        container = create_new()
        setattr(target, "__container__", container)
        if manager := try_get_current_manager():
            manager.register_container(container)
        return container

    @classmethod
    def get_or_create(cls, kls: type[T]) -> Self:
        """
        컨테이너 어노테이션이 붙은 클래스에 컨테이너 생성

        현재 활성 manager가 있으면 자동으로 등록됨.
        없으면 나중에 scan() 시점에 등록됨.
        """
        return cls._apply_override_rules(kls, lambda: cls(kls))

    def add_element(self, element: "Element[T]") -> None:
        """컨테이너에 엘리먼트 추가"""
        self.elements.append(element)

    def has_element(self, element_type: type["Element"]) -> bool:
        """특정 타입의 Element가 있는지 확인"""
        return any(isinstance(e, element_type) for e in self.elements)

    def get_element[E: Element](self, element_type: type[E]) -> E | None:
        """특정 타입의 Element 반환 (없으면 None)"""
        for element in self.elements:
            if isinstance(element, element_type):
                return element
        return None

    def get_metadatas[U](self, key: str, default: Optional[U] = None) -> list[U]:
        """
        주어진 메타데이터 키에 해당하는 모든 값들을 리스트로 반환한다.

        - elements를 순회하며 element.metadata에 key가 있으면 그 값을 수집한다.
        - 수집된 값이 없다면 default가 제공되었을 경우 [default]를 반환하고,
          그렇지 않으면 빈 리스트를 반환한다.

        사용 예:
            container.get_metadatas("request_mapping") -> ["/api/v1"]
        """
        values: list[U] = []
        for element in self.elements:
            if key in element.metadata:
                val = element.metadata.get(key)
                values.append(cast(U, val))

        if not values and default is not None:
            return [default]

        return values

    @overload
    def get_metadata[U](
        self, key: str, default: Optional[U] = None, raise_exception: bool = True
    ) -> U: ...
    @overload
    def get_metadata[U](
        self, key: str, default: Optional[U] = None, raise_exception: bool = False
    ) -> U | None: ...

    def get_metadata[U](
        self, key: str, default: Optional[U] = None, raise_exception: bool = False
    ) -> U | None:
        """
        주어진 메타데이터 키에 해당하는 첫 번째 값을 반환한다.

        - elements를 순회하며 element.metadata에 key가 있으면 그 값을 반환한다.
        - 수집된 값이 없다면 default가 제공되었을 경우 default를 반환하고,
          그렇지 않으면 None을 반환한다.

        사용 예:
            container.get_metadata("request_mapping") -> "/api/v1"
        """
        for element in self.elements:
            if key in element.metadata:
                val = element.metadata.get(key)
                return cast(U, val)

        if default is not None:
            return default
        if raise_exception:
            raise KeyError(f"Metadata key '{key}' not found in container elements.")
        return None
