"""
bloom.core.aop - Aspect-Oriented Programming 지원

메서드 인터셉터 체인 패턴을 통해 다양한 데코레이터들이 유기적으로 결합되도록 함.

핵심 개념:
    1. MethodInterceptor: 메서드 호출을 가로채는 인터셉터
    2. InterceptorChain: 인터셉터들의 실행 순서 관리 (Chain of Responsibility)
    3. MethodDescriptor: 메서드 메타데이터 (데코레이터 정보 등)
    4. ComponentProxy: 컴포넌트의 모든 메서드를 프록시로 감쌈

사용 예:
    @Component
    class UserService:
        @Transactional
        @EventEmitter("user.created")
        @Order(1)
        async def create_user(self, name: str) -> User:
            return User(name=name)

    # 실행 순서:
    # 1. Order(1)에 의해 우선순위 결정
    # 2. Transactional 시작 (트랜잭션 열기)
    # 3. EventEmitter 준비
    # 4. 실제 메서드 실행
    # 5. EventEmitter 이벤트 발행
    # 6. Transactional 커밋/롤백
"""

from .interceptor import (
    MethodInterceptor,
    InterceptorChain,
    MethodInvocation,
    ProceedingJoinPoint,
    BeforeInterceptor,
    AfterInterceptor,
    AfterReturningInterceptor,
    AfterThrowingInterceptor,
    AroundInterceptor,
)
from .descriptor import (
    MethodDescriptor,
    InterceptorInfo,
    get_method_descriptor,
    set_method_descriptor,
    ensure_method_descriptor,
)
from .decorators import (
    Before,
    After,
    Around,
    AfterReturning,
    AfterThrowing,
    Order,
    Transactional,
    EventListener,
    EventEmitter,
    Cacheable,
    CacheEvict,
    Async,
    Retry,
    RateLimited,
    Timed,
    Logged,
)
from .proxy import (
    create_component_proxy,
    ProxiedMethod,
    ComponentProxyFactory,
)
from .registry import (
    InterceptorRegistry,
    get_interceptor_registry,
    reset_interceptor_registry,
)
from .factory import (
    DecoratorFactory,
    SimpleDecoratorFactory,
    InjectableDecoratorFactory,
    InjectableInterceptor,
    FlatDecorator,
    FlatInterceptor,
    create_annotation,
    create_injectable_annotation,
)


__all__ = [
    # Interceptor
    "MethodInterceptor",
    "InterceptorChain",
    "MethodInvocation",
    "ProceedingJoinPoint",
    "BeforeInterceptor",
    "AfterInterceptor",
    "AfterReturningInterceptor",
    "AfterThrowingInterceptor",
    "AroundInterceptor",
    # Descriptor
    "MethodDescriptor",
    "InterceptorInfo",
    "get_method_descriptor",
    "set_method_descriptor",
    "ensure_method_descriptor",
    # Decorators
    "Before",
    "After",
    "Around",
    "AfterReturning",
    "AfterThrowing",
    "Order",
    "Transactional",
    "EventListener",
    "EventEmitter",
    "Cacheable",
    "CacheEvict",
    "Async",
    "Retry",
    "RateLimited",
    "Timed",
    "Logged",
    # Proxy
    "create_component_proxy",
    "ProxiedMethod",
    "ComponentProxyFactory",
    # Registry
    "InterceptorRegistry",
    "get_interceptor_registry",
    "reset_interceptor_registry",
    # Factory
    "DecoratorFactory",
    "SimpleDecoratorFactory",
    "InjectableDecoratorFactory",
    "InjectableInterceptor",
    "FlatDecorator",
    "FlatInterceptor",
    "create_annotation",
    "create_injectable_annotation",
]
