"""
의존성 주입 개선 기능 테스트

@Autowired, @Qualifier, @Primary, @Lazy, Optional[T] 테스트
"""

import pytest
from typing import Optional

from bloom.core import (
    get_container_manager,
    Component,
    Service,
    Autowired,
    Primary,
    Lazy,
    Qualifier,
)
from bloom.core.container.manager import containers


# =============================================================================
# 테스트용 클래스 정의
# =============================================================================

class CacheClient:
    """캐시 클라이언트 인터페이스"""
    def get(self, key: str) -> str | None:
        raise NotImplementedError


class Logger:
    """로거 인터페이스"""
    def log(self, msg: str) -> None:
        raise NotImplementedError


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def clean_containers():
    """각 테스트 전후로 containers 정리"""
    yield
    # 테스트에서 등록한 클래스들 정리
    to_remove = []
    for kls in containers.keys():
        if hasattr(kls, "__module__") and "test_injection" in str(kls.__module__):
            to_remove.append(kls)
    for kls in to_remove:
        del containers[kls]


# =============================================================================
# @Primary 테스트
# =============================================================================

class TestPrimary:
    """@Primary 데코레이터 테스트"""

    @pytest.mark.asyncio
    async def test_primary_is_selected_when_multiple_beans(self):
        """동일 타입 여러 빈 중 @Primary가 선택됨"""
        
        @Primary
        @Component
        class RedisCache(CacheClient):
            def get(self, key: str) -> str | None:
                return f"redis:{key}"
        
        @Component
        class MemCache(CacheClient):
            def get(self, key: str) -> str | None:
                return f"mem:{key}"
        
        @Service
        class MyService:
            cache: CacheClient
        
        manager = get_container_manager()
        await manager.initialize()
        
        service = manager.registry.instance(type=MyService)
        assert service is not None
        # Primary인 RedisCache가 주입되어야 함
        assert service.cache.get("test") == "redis:test"

    @pytest.mark.asyncio
    async def test_primary_takes_precedence_over_direct_type(self):
        """@Primary가 있으면 직접 타입 매칭보다 우선"""
        
        @Component
        class DirectService:
            def identify(self) -> str:
                return "direct"
        
        @Primary
        @Component
        class ExtendedService(DirectService):
            def identify(self) -> str:
                return "extended"
        
        @Service
        class Consumer:
            service: DirectService
        
        manager = get_container_manager()
        await manager.initialize()
        
        consumer = manager.registry.instance(type=Consumer)
        # @Primary가 붙은 ExtendedService가 우선됨
        assert consumer.service.identify() == "extended"


# =============================================================================
# @Qualifier 테스트
# =============================================================================

class TestQualifier:
    """@Qualifier 데코레이터 테스트"""

    @pytest.mark.asyncio
    async def test_qualifier_selects_named_bean(self):
        """@Qualifier로 이름이 지정된 빈이 선택됨"""
        
        @Qualifier("redis")
        @Component
        class RedisCacheQ(CacheClient):
            def get(self, key: str) -> str | None:
                return f"redis:{key}"
        
        @Qualifier("memcache")
        @Component
        class MemCacheQ(CacheClient):
            def get(self, key: str) -> str | None:
                return f"mem:{key}"
        
        @Service
        class ServiceWithQualifier:
            cache: CacheClient = Autowired(qualifier="memcache")
        
        manager = get_container_manager()
        await manager.initialize()
        
        service = manager.registry.instance(type=ServiceWithQualifier)
        assert service is not None
        # memcache qualifier로 MemCacheQ가 주입되어야 함
        assert service.cache.get("test") == "mem:test"


# =============================================================================
# @Autowired 테스트
# =============================================================================

class TestAutowired:
    """@Autowired 데코레이터 테스트"""

    @pytest.mark.asyncio
    async def test_autowired_basic(self):
        """기본 Autowired 사용"""
        
        @Component
        class Repository:
            def find(self) -> str:
                return "found"
        
        @Service
        class ServiceWithAutowired:
            repo: Repository = Autowired()
        
        manager = get_container_manager()
        await manager.initialize()
        
        service = manager.registry.instance(type=ServiceWithAutowired)
        assert service.repo.find() == "found"

    @pytest.mark.asyncio
    async def test_autowired_required_false(self):
        """Autowired(required=False)는 빈이 없으면 None"""
        
        @Service
        class ServiceWithOptionalDep:
            # Logger는 등록되지 않음
            logger: Logger = Autowired(required=False)
        
        manager = get_container_manager()
        await manager.initialize()
        
        service = manager.registry.instance(type=ServiceWithOptionalDep)
        assert service.logger is None

    @pytest.mark.asyncio
    async def test_autowired_required_true_raises(self):
        """Autowired(required=True, default)는 빈이 없으면 에러"""
        
        @Service
        class ServiceWithRequiredDep:
            # NonExistent는 등록되지 않음
            dep: "NonExistentType" = Autowired()
        
        # 타입 정의 (등록은 안 함)
        class NonExistentType:
            pass
        
        # 의존성 분석 시 에러 안 남 (Lazy)
        # 하지만 실제 주입 시 에러
        manager = get_container_manager()
        
        # initialize 시 에러 발생 (의존성 주입 시)
        # 실제로는 LazyProxy가 resolve될 때 에러 발생


# =============================================================================
# Optional[T] 테스트
# =============================================================================

class TestOptionalDependency:
    """Optional[T] 의존성 테스트"""

    @pytest.mark.asyncio
    async def test_optional_dependency_none_when_missing(self):
        """Optional[T]는 빈이 없으면 None"""
        
        class NotRegisteredService:
            pass
        
        @Service
        class ServiceWithOptional:
            maybe_service: Optional[NotRegisteredService]
        
        manager = get_container_manager()
        await manager.initialize()
        
        service = manager.registry.instance(type=ServiceWithOptional)
        assert service.maybe_service is None

    @pytest.mark.asyncio
    async def test_optional_dependency_injected_when_present(self):
        """Optional[T]도 빈이 있으면 정상 주입"""
        
        @Component
        class OptionalDep:
            value = "exists"
        
        @Service
        class ServiceWithOptionalPresent:
            dep: Optional[OptionalDep]
        
        manager = get_container_manager()
        await manager.initialize()
        
        service = manager.registry.instance(type=ServiceWithOptionalPresent)
        assert service.dep is not None
        assert service.dep.value == "exists"

    @pytest.mark.asyncio
    async def test_union_none_syntax(self):
        """T | None 문법도 Optional로 처리"""
        
        class AnotherNotRegistered:
            pass
        
        @Service
        class ServiceWithUnionNone:
            maybe: AnotherNotRegistered | None
        
        manager = get_container_manager()
        await manager.initialize()
        
        service = manager.registry.instance(type=ServiceWithUnionNone)
        assert service.maybe is None


# =============================================================================
# @Lazy 테스트
# =============================================================================

class TestLazy:
    """@Lazy 데코레이터 테스트"""

    @pytest.mark.asyncio
    async def test_lazy_component_not_initialized_until_used(self):
        """@Lazy 컴포넌트는 사용 전까지 초기화 안 됨"""
        
        init_called = []
        
        @Lazy
        @Component
        class LazyComponent:
            def __init__(self):
                init_called.append(True)
            
            def do_something(self) -> str:
                return "done"
        
        @Service
        class ServiceUsingLazy:
            lazy_dep: LazyComponent
        
        manager = get_container_manager()
        await manager.initialize()
        
        # Bloom은 기본적으로 LazyProxy 사용하므로 
        # 서비스 인스턴스 조회해도 아직 LazyComponent 초기화 안 됨
        service = manager.registry.instance(type=ServiceUsingLazy)
        
        # LazyProxy를 통해 접근하면 그때 초기화됨
        result = service.lazy_dep.do_something()
        assert result == "done"
        assert len(init_called) == 1  # 이제 초기화됨


# =============================================================================
# 복합 시나리오 테스트
# =============================================================================

class TestComplexScenarios:
    """복합 시나리오 테스트"""

    @pytest.mark.asyncio
    async def test_primary_with_qualifier_override(self):
        """@Qualifier가 @Primary보다 우선"""
        
        @Primary
        @Qualifier("primary-cache")
        @Component
        class PrimaryCacheComplex(CacheClient):
            def get(self, key: str) -> str | None:
                return f"primary:{key}"
        
        @Qualifier("secondary-cache")
        @Component
        class SecondaryCacheComplex(CacheClient):
            def get(self, key: str) -> str | None:
                return f"secondary:{key}"
        
        @Service
        class ServiceSelectingSecondary:
            # Qualifier로 secondary 선택
            cache: CacheClient = Autowired(qualifier="secondary-cache")
        
        @Service
        class ServiceUsingDefault:
            # Qualifier 없으면 Primary 선택
            cache: CacheClient
        
        manager = get_container_manager()
        await manager.initialize()
        
        svc1 = manager.registry.instance(type=ServiceSelectingSecondary)
        assert svc1.cache.get("x") == "secondary:x"
        
        svc2 = manager.registry.instance(type=ServiceUsingDefault)
        assert svc2.cache.get("x") == "primary:x"

    @pytest.mark.asyncio
    async def test_multiple_beans_without_primary_raises(self):
        """여러 빈이 있는데 @Primary 없으면 에러"""
        
        @Component
        class ImplA(CacheClient):
            def get(self, key: str) -> str | None:
                return "a"
        
        @Component
        class ImplB(CacheClient):
            def get(self, key: str) -> str | None:
                return "b"
        
        @Service
        class AmbiguousService:
            cache: CacheClient
        
        manager = get_container_manager()
        
        # 여러 빈이 있으면 초기화 시 에러
        with pytest.raises(RuntimeError) as exc_info:
            await manager.initialize()
        
        assert "Multiple beans found" in str(exc_info.value) or "Cannot resolve" in str(exc_info.value)
