"""
Factory Container 모듈

Factory는 Container에 등록된 인스턴스들을 의존성으로 주입받아서:
1. Modifier: 기존 인스턴스를 받아서 수정된 같은 타입의 인스턴스를 반환
2. Creator: 새로운 인스턴스를 생성

두 가지 역할을 모두 수행할 수 있습니다.
"""

from typing import Any, Self, get_type_hints, cast
from uuid import uuid4
import inspect

from .manager import get_container_registry
from .base import Container
from .functions import is_coroutine


# =============================================================================
# Factory Container
# =============================================================================


class FactoryContainer[T](Container[type[T]]):
    """팩토리 컨테이너 클래스

    Factory는 Container에 등록된 다른 서비스들을 의존성으로 주입받아서
    인스턴스를 생성(Creator)하거나 수정(Modifier)하는 역할을 합니다.

    사용 예:
        @Factory
        class UserFactory:
            user_repository: UserRepository  # 의존성 주입
            email_service: EmailService

            def create(self, name: str, email: str) -> User:
                '''Creator: 새 User 인스턴스 생성'''
                user = User(name=name, email=email)
                self.user_repository.save(user)
                return user

            async def create_async(self, name: str) -> User:
                '''Async Creator'''
                user = User(name=name)
                await self.email_service.send_welcome(user)
                return user

            def enhance(self, user: User) -> User:
                '''Modifier: 기존 User 수정'''
                user.enhanced = True
                return user

            async def process(self, user: User) -> User:
                '''Async Modifier'''
                await self.email_service.notify(user)
                user.notified = True
                return user
    """

    # Modifier 메서드들 (target_type -> method_name 매핑)
    _modifier_methods: dict[type, list[str]]
    # Creator 메서드들 (return_type -> method_name 매핑)
    _creator_methods: dict[type, list[str]]

    def __init__(self, kls: type[T], component_id: str) -> None:
        super().__init__(kls, component_id)
        self._modifier_methods = {}
        self._creator_methods = {}
        self._analyze_factory_methods()

    def _analyze_factory_methods(self) -> None:
        """Factory 클래스의 메서드들을 분석하여 Modifier/Creator 구분"""
        for name in dir(self.kls):
            if name.startswith("_"):
                continue

            attr = getattr(self.kls, name, None)
            if attr is None or not callable(attr):
                continue

            if not inspect.isfunction(attr) and not inspect.ismethod(attr):
                continue

            # 타입 힌트 분석
            try:
                hints = get_type_hints(attr)
            except Exception:
                continue

            return_type = hints.get("return")
            if return_type is None:
                continue

            # 파라미터 분석 (self 제외)
            sig = inspect.signature(attr)
            params = list(sig.parameters.values())
            # self 제외
            params = [p for p in params if p.name != "self"]

            if len(params) == 1:
                # 단일 파라미터 - Modifier 후보
                first_param = params[0]
                param_type = hints.get(first_param.name)

                if param_type is not None and param_type == return_type:
                    # 입력 타입 == 출력 타입 -> Modifier
                    if param_type not in self._modifier_methods:
                        self._modifier_methods[param_type] = []
                    self._modifier_methods[param_type].append(name)
                    continue

            # 그 외 -> Creator
            if return_type not in self._creator_methods:
                self._creator_methods[return_type] = []
            self._creator_methods[return_type].append(name)

    async def initialize(self) -> T:
        """Factory 인스턴스 초기화"""
        instance = self.kls()
        return instance

    def get_modifier_methods(self, target_type: type) -> list[str]:
        """특정 타입에 대한 Modifier 메서드 이름들 반환"""
        return self._modifier_methods.get(target_type, [])

    def get_creator_methods(self, return_type: type) -> list[str]:
        """특정 반환 타입에 대한 Creator 메서드 이름들 반환"""
        return self._creator_methods.get(return_type, [])

    def get_all_modifier_types(self) -> list[type]:
        """이 Factory가 지원하는 모든 Modifier 대상 타입들 반환"""
        return list(self._modifier_methods.keys())

    def get_all_creator_types(self) -> list[type]:
        """이 Factory가 생성할 수 있는 모든 타입들 반환"""
        return list(self._creator_methods.keys())

    async def modify[U](self, instance: U, method_name: str | None = None) -> U:
        """Modifier 메서드 실행

        Args:
            instance: 수정할 인스턴스
            method_name: 실행할 메서드 이름 (None이면 해당 타입의 첫 번째 Modifier)

        Returns:
            수정된 인스턴스
        """
        from .manager import get_container_manager

        manager = get_container_manager()
        factory_instance = manager.get_instance(self.kls)

        if factory_instance is None:
            raise RuntimeError(f"Factory '{self.kls.__name__}' is not initialized")

        target_type = type(instance)
        methods = self.get_modifier_methods(target_type)

        if not methods:
            raise ValueError(
                f"No modifier method found for type '{target_type.__name__}' "
                f"in factory '{self.kls.__name__}'"
            )

        if method_name is None:
            method_name = methods[0]
        elif method_name not in methods:
            raise ValueError(
                f"Method '{method_name}' is not a modifier for type '{target_type.__name__}'"
            )

        method = getattr(factory_instance, method_name)
        result = method(instance)

        if is_coroutine(result):
            return await result
        return cast(U, result)

    async def create[R](
        self,
        return_type: type[R],
        method_name: str | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> R:
        """Creator 메서드 실행

        Args:
            return_type: 생성할 인스턴스의 타입
            method_name: 실행할 메서드 이름 (None이면 해당 타입의 첫 번째 Creator)
            *args, **kwargs: Creator 메서드에 전달할 인자

        Returns:
            생성된 인스턴스
        """
        from .manager import get_container_manager

        manager = get_container_manager()
        factory_instance = manager.get_instance(self.kls)

        if factory_instance is None:
            raise RuntimeError(f"Factory '{self.kls.__name__}' is not initialized")

        methods = self.get_creator_methods(return_type)

        if not methods:
            raise ValueError(
                f"No creator method found for type '{return_type.__name__}' "
                f"in factory '{self.kls.__name__}'"
            )

        if method_name is None:
            method_name = methods[0]
        elif method_name not in methods:
            raise ValueError(
                f"Method '{method_name}' is not a creator for type '{return_type.__name__}'"
            )

        method = getattr(factory_instance, method_name)
        result = method(*args, **kwargs)

        if is_coroutine(result):
            return await result
        return cast(R, result)

    @classmethod
    def register[U: type](cls, kls: U) -> "FactoryContainer[U]":
        """Factory 클래스 등록"""
        if not hasattr(kls, "__component_id__"):
            kls.__component_id__ = str(uuid4())  # type: ignore

        registry = get_container_registry()

        if kls not in registry:
            registry[kls] = {}

        if kls.__component_id__ not in registry[kls]:  # type: ignore
            registry[kls][kls.__component_id__] = cls(kls, kls.__component_id__)  # type: ignore

        container: Self = registry[kls][kls.__component_id__]  # type: ignore
        return container
