"""
Proxy 모듈 테스트

단위 테스트:
- LazyProxy
- AsyncProxy
- ScopedProxy

통합 테스트:
- Proxy와 ScopeContext 통합
- AutoCloseable 자동 관리

엣지 케이스:
- 미해결 proxy 접근
- 잘못된 스코프에서 접근
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from bloom.core.container.proxy import LazyProxy, AsyncProxy, ScopedProxy
from bloom.core.container.scope import (
    Scope,
    ScopeContext,
    call_scope_manager,
    request_scope,
    transactional_scope,
    set_call_scope,
    set_request_scope,
    set_transactional_scope,
    get_call_scope,
)
from bloom.core.abstract.autocloseable import AutoCloseable, AsyncAutoCloseable


# =============================================================================
# Mock 클래스들
# =============================================================================


class MockService:
    """테스트용 서비스 클래스"""

    def __init__(self, name: str = "default"):
        self.name = name
        self.data = {"key": "value"}
        self.call_count = 0

    def do_something(self) -> str:
        self.call_count += 1
        return f"done by {self.name}"

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, key: str):
        return self.data[key]

    def __setitem__(self, key: str, value):
        self.data[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self.data

    def __iter__(self):
        return iter(self.data)

    def __call__(self, x: int) -> int:
        return x * 2


class MockContainer:
    """테스트용 Container mock"""

    def __init__(self, kls: type):
        self.kls = kls
        self.component_id = "mock-component-id"


class MockManager:
    """테스트용 ContainerManager mock"""

    def __init__(self, instance=None):
        self._instance = instance

    def instance(self, type=None):
        return self._instance


class MockAutoCloseableService(AutoCloseable):
    """AutoCloseable 서비스"""

    instances: list["MockAutoCloseableService"] = []
    close_order: list[int] = []

    def __init__(self, id: int = 0):
        self.id = id
        self.entered = False
        self.exited = False
        MockAutoCloseableService.instances.append(self)

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exited = True
        MockAutoCloseableService.close_order.append(self.id)

    def do_work(self) -> str:
        return f"work done by {self.id}"

    @classmethod
    def reset(cls):
        cls.instances = []
        cls.close_order = []


class MockAsyncAutoCloseableService(AsyncAutoCloseable):
    """AsyncAutoCloseable 서비스"""

    instances: list["MockAsyncAutoCloseableService"] = []
    close_order: list[int] = []

    def __init__(self, id: int = 0):
        self.id = id
        self.entered = False
        self.exited = False
        MockAsyncAutoCloseableService.instances.append(self)

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        self.exited = True
        MockAsyncAutoCloseableService.close_order.append(self.id)

    async def do_work(self) -> str:
        return f"async work done by {self.id}"

    @classmethod
    def reset(cls):
        cls.instances = []
        cls.close_order = []


class MockFactoryContainer:
    """테스트용 FactoryContainer mock"""

    def __init__(self, return_type: type, is_async: bool = False):
        self.return_type = return_type
        self.component_id = f"factory-{return_type.__name__}"
        self.is_async = is_async


# =============================================================================
# 단위 테스트: LazyProxy
# =============================================================================


class TestLazyProxy:
    """LazyProxy 단위 테스트"""

    def test_lazy_proxy_creation(self):
        """LazyProxy 생성 테스트"""
        service = MockService("test")
        container = MockContainer(MockService)
        manager = MockManager(service)

        proxy = LazyProxy(container, manager)

        assert not proxy._lp_resolved
        assert proxy._lp_instance is None

    def test_lazy_proxy_resolve_on_access(self):
        """LazyProxy 접근 시 해결 테스트"""
        service = MockService("test")
        container = MockContainer(MockService)
        manager = MockManager(service)

        proxy = LazyProxy(container, manager)

        # 속성 접근 시 해결
        result = proxy.do_something()

        assert proxy._lp_resolved
        assert proxy._lp_instance is service
        assert result == "done by test"

    def test_lazy_proxy_transparent_attribute_access(self):
        """LazyProxy 투명 속성 접근 테스트"""
        service = MockService("test")
        container = MockContainer(MockService)
        manager = MockManager(service)

        proxy = LazyProxy(container, manager)

        assert proxy.name == "test"
        proxy.name = "modified"
        assert proxy.name == "modified"
        assert service.name == "modified"

    def test_lazy_proxy_container_protocol(self):
        """LazyProxy 컨테이너 프로토콜 테스트"""
        service = MockService()
        container = MockContainer(MockService)
        manager = MockManager(service)

        proxy = LazyProxy(container, manager)

        # __len__
        assert len(proxy) == 1

        # __getitem__
        assert proxy["key"] == "value"

        # __setitem__
        proxy["new_key"] = "new_value"
        assert service.data["new_key"] == "new_value"

        # __contains__
        assert "key" in proxy

        # __iter__
        assert list(proxy) == list(service.data)

    def test_lazy_proxy_callable(self):
        """LazyProxy callable 테스트"""
        service = MockService()
        container = MockContainer(MockService)
        manager = MockManager(service)

        proxy = LazyProxy(container, manager)

        assert proxy(5) == 10

    def test_lazy_proxy_repr(self):
        """LazyProxy repr 테스트"""
        service = MockService()
        container = MockContainer(MockService)
        manager = MockManager(service)

        proxy = LazyProxy(container, manager)

        repr_str = repr(proxy)
        assert "LazyProxy" in repr_str
        assert "MockService" in repr_str
        assert "pending" in repr_str

        # resolve 후
        _ = proxy.name
        repr_str = repr(proxy)
        assert "resolved" in repr_str

    def test_lazy_proxy_str(self):
        """LazyProxy str 테스트"""
        service = MockService("test")
        container = MockContainer(MockService)
        manager = MockManager(service)

        proxy = LazyProxy(container, manager)

        # str() 호출 시 resolve 되고 대상의 str 반환
        str_val = str(proxy)
        assert proxy._lp_resolved

    def test_lazy_proxy_bool(self):
        """LazyProxy bool 테스트"""
        service = MockService()
        container = MockContainer(MockService)
        manager = MockManager(service)

        proxy = LazyProxy(container, manager)

        assert bool(proxy)

    def test_lazy_proxy_equality(self):
        """LazyProxy 동등성 테스트"""
        service = MockService()
        container = MockContainer(MockService)
        manager = MockManager(service)

        proxy1 = LazyProxy(container, manager)
        proxy2 = LazyProxy(container, manager)

        assert proxy1 == proxy2  # 둘 다 같은 서비스로 resolve
        assert proxy1 == service  # 서비스와 직접 비교

    def test_lazy_proxy_hash(self):
        """LazyProxy hash 테스트"""
        service = MockService()
        container = MockContainer(MockService)
        manager = MockManager(service)

        proxy = LazyProxy(container, manager)

        assert hash(proxy) == hash(service)

    def test_lazy_proxy_get_target_type(self):
        """LazyProxy 대상 타입 반환 테스트"""
        container = MockContainer(MockService)
        manager = MockManager(MockService())

        proxy = LazyProxy(container, manager)

        assert proxy._lp_get_target_type() == MockService

    def test_lazy_proxy_resolve_failure(self):
        """LazyProxy 해결 실패 테스트"""
        container = MockContainer(MockService)
        manager = MockManager(None)  # None 반환

        proxy = LazyProxy(container, manager)

        with pytest.raises(RuntimeError, match="failed to resolve"):
            _ = proxy.name


# =============================================================================
# 단위 테스트: AsyncProxy
# =============================================================================


class TestAsyncProxy:
    """AsyncProxy 단위 테스트"""

    def setup_method(self):
        MockAsyncAutoCloseableService.reset()
        set_call_scope(None)
        set_transactional_scope(None)

    def teardown_method(self):
        set_call_scope(None)
        set_transactional_scope(None)

    def test_async_proxy_creation(self):
        """AsyncProxy 생성 테스트"""
        factory = MockFactoryContainer(MockAsyncAutoCloseableService, is_async=True)
        manager = MagicMock()

        proxy = AsyncProxy(factory, manager, Scope.CALL)

        assert not proxy._ap_resolved
        assert proxy._ap_scope == Scope.CALL

    def test_async_proxy_repr(self):
        """AsyncProxy repr 테스트"""
        factory = MockFactoryContainer(MockAsyncAutoCloseableService)
        manager = MagicMock()

        proxy = AsyncProxy(factory, manager, Scope.CALL)

        repr_str = repr(proxy)
        assert "AsyncProxy" in repr_str
        assert "MockAsyncAutoCloseableService" in repr_str
        assert "call" in repr_str

    def test_async_proxy_get_target_type(self):
        """AsyncProxy 대상 타입 반환 테스트"""
        factory = MockFactoryContainer(MockAsyncAutoCloseableService)
        manager = MagicMock()

        proxy = AsyncProxy(factory, manager, Scope.CALL)

        assert proxy._ap_get_target_type() == MockAsyncAutoCloseableService


# =============================================================================
# 단위 테스트: ScopedProxy
# =============================================================================


class TestScopedProxy:
    """ScopedProxy 단위 테스트"""

    def setup_method(self):
        MockAutoCloseableService.reset()
        set_call_scope(None)
        set_transactional_scope(None)

    def teardown_method(self):
        set_call_scope(None)
        set_transactional_scope(None)

    def test_scoped_proxy_creation(self):
        """ScopedProxy 생성 테스트"""
        factory = MockFactoryContainer(MockAutoCloseableService)
        manager = MagicMock()

        proxy = ScopedProxy(factory, manager, Scope.CALL)

        assert proxy._sp_scope == Scope.CALL

    def test_scoped_proxy_repr(self):
        """ScopedProxy repr 테스트"""
        factory = MockFactoryContainer(MockAutoCloseableService)
        manager = MagicMock()

        proxy = ScopedProxy(factory, manager, Scope.CALL)

        repr_str = repr(proxy)
        assert "ScopedProxy" in repr_str
        assert "MockAutoCloseableService" in repr_str
        assert "call" in repr_str

    def test_scoped_proxy_get_target_type(self):
        """ScopedProxy 대상 타입 반환 테스트"""
        factory = MockFactoryContainer(MockAutoCloseableService)
        manager = MagicMock()

        proxy = ScopedProxy(factory, manager, Scope.CALL)

        assert proxy._sp_get_target_type() == MockAutoCloseableService


# =============================================================================
# 통합 테스트: LazyProxy와 Container
# =============================================================================


class TestLazyProxyIntegration:
    """LazyProxy 통합 테스트"""

    def test_lazy_proxy_caches_instance(self):
        """LazyProxy 인스턴스 캐싱 테스트"""
        service = MockService()
        container = MockContainer(MockService)
        manager = MockManager(service)

        proxy = LazyProxy(container, manager)

        # 여러 번 접근해도 같은 인스턴스
        _ = proxy.name
        _ = proxy.do_something()
        _ = proxy.data

        assert proxy._lp_instance is service

    def test_lazy_proxy_delattr(self):
        """LazyProxy delattr 테스트"""
        service = MockService()
        service.temp_attr = "temp"
        container = MockContainer(MockService)
        manager = MockManager(service)

        proxy = LazyProxy(container, manager)

        del proxy.temp_attr
        assert not hasattr(service, "temp_attr")

    def test_lazy_proxy_delitem(self):
        """LazyProxy delitem 테스트"""

        # MockService에 __delitem__ 구현이 없으므로
        # 직접 dict를 가진 객체로 테스트
        class DictLikeService:
            def __init__(self):
                self.data = {"key": "value"}

            def __delitem__(self, key):
                del self.data[key]

        service = DictLikeService()
        container = MockContainer(DictLikeService)
        manager = MockManager(service)

        proxy = LazyProxy(container, manager)

        del proxy["key"]
        assert "key" not in service.data


# =============================================================================
# 통합 테스트: ScopedProxy와 ScopeContext
# =============================================================================


class TestScopedProxyWithScopeContext:
    """ScopedProxy와 ScopeContext 통합 테스트"""

    def setup_method(self):
        MockAutoCloseableService.reset()
        set_call_scope(None)
        set_transactional_scope(None)

    def teardown_method(self):
        set_call_scope(None)
        set_transactional_scope(None)

    def test_scoped_proxy_stores_in_context(self):
        """ScopedProxy가 ScopeContext에 저장하는지 테스트"""
        # 이 테스트는 실제 FactoryContainer와 Manager가 필요하므로
        # 단순화된 테스트만 수행

        ctx = ScopeContext(Scope.CALL)
        service = MockAutoCloseableService(1)
        service.__enter__()

        ctx.set("test-factory-id", service)
        ctx.register_closeable(service)

        assert ctx.get("test-factory-id") == service

    def test_scoped_proxy_reuses_from_context(self):
        """ScopedProxy가 ScopeContext에서 재사용하는지 테스트"""
        ctx = ScopeContext(Scope.CALL)
        service = MockAutoCloseableService(1)

        ctx.set("my-component-id", service)
        set_call_scope(ctx)

        # 같은 component_id로 조회하면 같은 인스턴스 반환
        assert ctx.get("my-component-id") == service


# =============================================================================
# 엣지 케이스 테스트
# =============================================================================


class TestProxyEdgeCases:
    """Proxy 엣지 케이스 테스트"""

    def setup_method(self):
        MockAutoCloseableService.reset()
        MockAsyncAutoCloseableService.reset()
        set_call_scope(None)
        set_transactional_scope(None)

    def teardown_method(self):
        set_call_scope(None)
        set_transactional_scope(None)

    def test_lazy_proxy_internal_attrs_not_proxied(self):
        """LazyProxy 내부 속성은 프록시되지 않음 테스트"""
        service = MockService()
        container = MockContainer(MockService)
        manager = MockManager(service)

        proxy = LazyProxy(container, manager)

        # _lp_ 접두사 속성은 프록시 자체 속성
        assert proxy._lp_resolved == False
        assert proxy._lp_container is container

    def test_scoped_proxy_internal_attrs_not_proxied(self):
        """ScopedProxy 내부 속성은 프록시되지 않음 테스트"""
        factory = MockFactoryContainer(MockAutoCloseableService)
        manager = MagicMock()

        proxy = ScopedProxy(factory, manager, Scope.CALL)

        # _sp_ 접두사 속성은 프록시 자체 속성
        assert proxy._sp_scope == Scope.CALL
        assert proxy._sp_factory_container is factory

    def test_scoped_proxy_without_scope_context(self):
        """스코프 컨텍스트 없이 ScopedProxy 접근 시 에러"""
        factory = MockFactoryContainer(MockAutoCloseableService)
        manager = MagicMock()
        manager.configuration_for.return_value = None

        proxy = ScopedProxy(factory, manager, Scope.CALL)

        # CALL 스코프에서 context 없이 접근 시
        # scope_context가 None이면 계속 진행하지만
        # configuration이 없으면 에러
        with pytest.raises(RuntimeError, match="No Configuration found"):
            _ = proxy.do_work()

    def test_scoped_proxy_async_factory_in_sync_context(self):
        """sync context에서 async Factory 접근 시 에러"""
        factory = MockFactoryContainer(MockAsyncAutoCloseableService, is_async=True)

        mock_config = MagicMock()
        manager = MagicMock()
        manager.configuration_for.return_value = mock_config
        manager._configurations.return_value = []

        proxy = ScopedProxy(factory, manager, Scope.CALL)

        # async Factory를 sync에서 접근 시 에러
        with pytest.raises(RuntimeError, match="Cannot resolve async Factory"):
            _ = proxy.do_work

    def test_lazy_proxy_multiple_resolves_same_instance(self):
        """LazyProxy 여러 번 resolve해도 같은 인스턴스"""
        service = MockService()
        container = MockContainer(MockService)
        manager = MockManager(service)

        proxy = LazyProxy(container, manager)

        # 여러 번 _lp_resolve 호출
        inst1 = proxy._lp_resolve()
        inst2 = proxy._lp_resolve()
        inst3 = proxy._lp_resolve()

        assert inst1 is inst2 is inst3 is service

    def test_scoped_proxy_container_protocols(self):
        """ScopedProxy 컨테이너 프로토콜 테스트 (resolve 실패 케이스)"""
        factory = MockFactoryContainer(MockAutoCloseableService)
        manager = MagicMock()
        manager.configuration_for.return_value = None

        proxy = ScopedProxy(factory, manager, Scope.CALL)

        # 컨테이너 프로토콜 사용 시도 시 resolve 실패로 에러
        with pytest.raises(RuntimeError):
            len(proxy)

        with pytest.raises(RuntimeError):
            iter(proxy)

        with pytest.raises(RuntimeError):
            "key" in proxy

        with pytest.raises(RuntimeError):
            proxy["key"]

        with pytest.raises(RuntimeError):
            proxy["key"] = "value"

        with pytest.raises(RuntimeError):
            del proxy["key"]

        with pytest.raises(RuntimeError):
            proxy()

    def test_scoped_proxy_equality_and_hash(self):
        """ScopedProxy 동등성과 해시 (resolve 실패 케이스)"""
        factory = MockFactoryContainer(MockAutoCloseableService)
        manager = MagicMock()
        manager.configuration_for.return_value = None

        proxy = ScopedProxy(factory, manager, Scope.CALL)

        with pytest.raises(RuntimeError):
            proxy == "something"

        with pytest.raises(RuntimeError):
            hash(proxy)

        with pytest.raises(RuntimeError):
            bool(proxy)

        with pytest.raises(RuntimeError):
            str(proxy)


# =============================================================================
# 동시성 테스트
# =============================================================================


class TestProxyConcurrency:
    """Proxy 동시성 테스트"""

    def test_lazy_proxy_thread_safety_basic(self):
        """LazyProxy 기본 스레드 안전성 테스트"""
        import threading

        service = MockService()
        container = MockContainer(MockService)
        manager = MockManager(service)

        proxy = LazyProxy(container, manager)
        results = []

        def access_proxy():
            result = proxy.do_something()
            results.append(result)

        threads = [threading.Thread(target=access_proxy) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10
        assert all(r == "done by default" for r in results)
