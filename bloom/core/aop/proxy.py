"""
ComponentProxy: 컴포넌트의 모든 메서드를 프록시로 감쌈

인터셉터 체인을 통해 AOP 기능을 제공.
"""

from typing import Any, Callable, TypeVar, TYPE_CHECKING
from functools import wraps
import inspect

from .interceptor import (
    MethodInterceptor,
    InterceptorChain,
    MethodInvocation,
)
from .descriptor import (
    MethodDescriptor,
    InterceptorInfo,
    get_method_descriptor,
)
from .registry import get_interceptor_registry

if TYPE_CHECKING:
    from ..manager import ContainerManager


T = TypeVar("T")


class ProxiedMethod:
    """
    프록시된 메서드.

    원본 메서드 호출 시 인터셉터 체인을 통해 실행.
    """

    def __init__(
        self,
        target: Any,
        method_name: str,
        method: Callable[..., Any],
        chain: InterceptorChain,
        container_manager: "ContainerManager | None" = None,
    ):
        self._target = target
        self._method_name = method_name
        self._method = method
        self._chain = chain
        self._container_manager = container_manager

        # 원본 메서드의 속성 복사
        self.__name__ = method.__name__
        self.__doc__ = method.__doc__
        self.__annotations__ = getattr(method, "__annotations__", {})

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """프록시 메서드 호출"""
        invocation = MethodInvocation(
            target=self._target,
            method_name=self._method_name,
            args=args,
            kwargs=kwargs,
            method=self._method,
        )

        # 컨테이너 매니저 주입 (InjectableInterceptor에서 사용)
        if self._container_manager is not None:
            invocation.attributes["container_manager"] = self._container_manager

        return await self._chain.invoke(invocation)

    def __repr__(self) -> str:
        return f"<ProxiedMethod {self._method_name}>"


def create_component_proxy[T](
    instance: T,
    cls: type[T] | None = None,
    container_manager: "ContainerManager | None" = None,
) -> T:
    """
    컴포넌트 인스턴스의 모든 메서드를 프록시로 감쌈.

    MethodDescriptor가 있는 메서드만 프록시 처리.

    Args:
        instance: 프록시할 인스턴스
        cls: 원본 클래스 (None이면 instance.__class__ 사용)
        container_manager: DI 컨테이너 매니저 (인터셉터에서 의존성 주입에 사용)

    Returns:
        프록시된 인스턴스 (원본 인스턴스를 수정)
    """
    if cls is None:
        cls = type(instance)

    registry = get_interceptor_registry()

    # 모든 메서드 검사
    for name in dir(cls):
        if name.startswith("_"):
            continue

        attr = getattr(cls, name, None)
        if attr is None or not callable(attr):
            continue

        # MethodDescriptor 확인
        descriptor = get_method_descriptor(attr)

        # descriptor가 없어도 글로벌 인터셉터가 있으면 프록시 처리
        global_interceptors = registry.get_global_interceptors()

        if descriptor is None and not global_interceptors:
            continue

        # 인터셉터 체인 구성
        chain = InterceptorChain()

        # 1. 글로벌 인터셉터 추가
        for interceptor in global_interceptors:
            chain.add(interceptor)

        # 2. 메서드별 인터셉터 추가
        if descriptor:
            method_interceptors = registry.create_interceptors_from_descriptor(
                descriptor
            )
            for interceptor in method_interceptors:
                chain.add(interceptor)

        # 체인이 비어있으면 스킵
        if not chain.interceptors:
            continue

        # 바운드 메서드 얻기
        bound_method = getattr(instance, name)

        # ProxiedMethod로 교체
        proxied = ProxiedMethod(
            target=instance,
            method_name=name,
            method=bound_method,
            chain=chain,
            container_manager=container_manager,
        )

        # 인스턴스에 프록시 메서드 설정
        setattr(instance, name, proxied)

    return instance


class ComponentProxyFactory:
    """
    컴포넌트 프록시를 생성하는 팩토리.

    ContainerManager와 통합하여 사용.
    """

    def __init__(self, container_manager: "ContainerManager | None" = None):
        self._registry = get_interceptor_registry()
        self._container_manager = container_manager

    def should_proxy(self, cls: type) -> bool:
        """이 클래스가 프록시 처리가 필요한지 확인"""
        # 클래스의 메서드 중 하나라도 MethodDescriptor가 있으면 프록시 필요
        for name in dir(cls):
            if name.startswith("_"):
                continue
            attr = getattr(cls, name, None)
            if attr and callable(attr) and get_method_descriptor(attr):
                return True

        # 글로벌 인터셉터가 있으면 모든 컴포넌트 프록시
        return bool(self._registry.get_global_interceptors())

    def create_proxy[T](self, instance: T) -> T:
        """프록시 인스턴스 생성"""
        return create_component_proxy(instance, container_manager=self._container_manager)
