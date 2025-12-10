"""
의존성 주입 관련 데코레이터 및 유틸리티

Spring의 @Autowired, @Qualifier, @Primary, @Lazy와 유사한 기능을 제공합니다.

Usage:
    @Component
    class MyService:
        # 기본 의존성 주입 (타입 기반)
        repository: UserRepository
        
        # 명시적 주입 with Qualifier
        cache: CacheClient = Autowired(qualifier="redis")
        
        # Optional 의존성 (없으면 None)
        logger: Optional[Logger] = Autowired(required=False)
        
        # Lazy 초기화 (처음 접근 시 주입)
        heavy_service: HeavyService = Autowired(lazy=True)

    @Primary  # 동일 타입 여러 빈 중 기본
    @Component  
    class RedisCache(CacheClient):
        pass

    @Component(name="memcache")  # 이름 지정
    class MemCache(CacheClient):
        pass
"""

from dataclasses import dataclass
from typing import TypeVar, Generic, overload

T = TypeVar("T")


# =============================================================================
# Autowired - 필드 기반 의존성 주입 마커
# =============================================================================


@dataclass(frozen=True)
class AutowiredField(Generic[T]):
    """Autowired 필드 정보를 담는 마커 클래스
    
    클래스 필드에 기본값으로 지정하면, ContainerFactory가 이 정보를 읽어
    의존성 주입 시 활용합니다.
    """
    qualifier: str | None = None  # 특정 빈 이름으로 주입
    required: bool = True  # False면 없어도 에러 안 남 (None으로 주입)
    lazy: bool = False  # True면 LazyProxy 사용


@overload
def Autowired() -> "AutowiredField": ...
@overload
def Autowired(
    *,
    qualifier: str | None = None,
    required: bool = True,
    lazy: bool = False,
) -> "AutowiredField": ...


def Autowired(
    *,
    qualifier: str | None = None,
    required: bool = True,
    lazy: bool = False,
) -> "AutowiredField":
    """의존성 주입 필드 마커
    
    Args:
        qualifier: 특정 이름의 빈을 주입 (동일 타입 여러 빈 중 선택)
        required: False면 빈이 없어도 에러 없이 None 주입
        lazy: True면 처음 접근 시까지 주입 지연 (LazyProxy)
    
    Usage:
        @Component
        class MyService:
            # 기본 주입
            repo: UserRepository = Autowired()
            
            # Qualifier로 특정 빈 선택
            cache: CacheClient = Autowired(qualifier="redis")
            
            # Optional - 없으면 None
            logger: Logger = Autowired(required=False)
            
            # Lazy - 처음 사용 시 주입
            heavy: HeavyService = Autowired(lazy=True)
    """
    return AutowiredField(qualifier=qualifier, required=required, lazy=lazy)


# =============================================================================
# Primary - 기본 빈 지정
# =============================================================================

# Element key for primary
PRIMARY_ELEMENT_KEY = "primary"


def Primary[T: type](kls: T) -> T:
    """동일 타입의 여러 빈 중 기본으로 사용할 빈 지정
    
    @Primary로 지정된 빈은 @Qualifier 없이 타입만으로 주입 시 우선 선택됩니다.
    
    Usage:
        @Primary
        @Component
        class RedisCache(CacheClient):
            pass
        
        @Component(name="memcache")
        class MemCache(CacheClient):
            pass
        
        @Component
        class MyService:
            # @Primary가 붙은 RedisCache가 주입됨
            cache: CacheClient
    """
    from .container import Container
    from .container.manager import get_container_registry
    
    registry = get_container_registry()
    component_id = getattr(kls, "__component_id__", None)
    
    # 이미 컨테이너가 등록되어 있는 경우
    if kls in registry and component_id and component_id in registry[kls]:
        existing = registry[kls][component_id]
        existing.add_element(PRIMARY_ELEMENT_KEY, True)
        return kls
    
    # 컨테이너가 없는 경우 -> 기본 Container 등록
    container = Container.register(kls)
    container.add_element(PRIMARY_ELEMENT_KEY, True)
    return kls


# =============================================================================
# Lazy - 지연 초기화 명시
# =============================================================================

# Element key for lazy
LAZY_ELEMENT_KEY = "lazy"


def Lazy[T: type](kls: T) -> T:
    """컴포넌트의 지연 초기화 명시
    
    @Lazy로 지정된 컴포넌트는 처음 사용될 때까지 인스턴스화되지 않습니다.
    
    Note: Bloom은 기본적으로 LazyProxy를 사용하므로 대부분의 경우 불필요합니다.
    이 데코레이터는 명시적 의도 표현과 Spring 호환성을 위해 제공됩니다.
    
    Usage:
        @Lazy
        @Component
        class HeavyService:
            def __init__(self):
                # 무거운 초기화 작업
                pass
    """
    from .container import Container
    from .container.manager import get_container_registry
    
    registry = get_container_registry()
    component_id = getattr(kls, "__component_id__", None)
    
    # 이미 컨테이너가 등록되어 있는 경우
    if kls in registry and component_id and component_id in registry[kls]:
        existing = registry[kls][component_id]
        existing.add_element(LAZY_ELEMENT_KEY, True)
        return kls
    
    # 컨테이너가 없는 경우 -> 기본 Container 등록
    container = Container.register(kls)
    container.add_element(LAZY_ELEMENT_KEY, True)
    return kls


# =============================================================================
# Qualifier - 빈 이름 지정 (Component 데코레이터의 name 파라미터로 대체 가능)
# =============================================================================

# Element key for qualifier/name
NAME_ELEMENT_KEY = "name"


def Qualifier[T: type](name: str) -> "Callable[[T], T]":
    """컴포넌트에 이름 부여 (빈 선택 시 사용)
    
    @Qualifier("name")으로 지정된 이름은 Autowired(qualifier="name")으로 선택 가능합니다.
    
    Usage:
        @Qualifier("redis")
        @Component
        class RedisCache(CacheClient):
            pass
        
        @Component
        class MyService:
            cache: CacheClient = Autowired(qualifier="redis")
    """
    from typing import Callable
    from .container import Container
    from .container.manager import get_container_registry
    
    def decorator(kls: T) -> T:
        registry = get_container_registry()
        component_id = getattr(kls, "__component_id__", None)
        
        # 이미 컨테이너가 등록되어 있는 경우
        if kls in registry and component_id and component_id in registry[kls]:
            existing = registry[kls][component_id]
            existing.add_element(NAME_ELEMENT_KEY, name)
            return kls
        
        # 컨테이너가 없는 경우 -> 기본 Container 등록
        container = Container.register(kls)
        container.add_element(NAME_ELEMENT_KEY, name)
        return kls
    
    return decorator


# =============================================================================
# 헬퍼 함수
# =============================================================================

def is_autowired_field(value: object) -> bool:
    """값이 AutowiredField 마커인지 확인"""
    return isinstance(value, AutowiredField)


def get_autowired_info(value: object) -> AutowiredField | None:
    """AutowiredField 정보 추출"""
    if isinstance(value, AutowiredField):
        return value
    return None
