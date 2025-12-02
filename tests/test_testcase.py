"""BloomTestCase 테스트"""

import pytest
from bloom import Application, Component
from bloom.web import Controller, RequestMapping, Get


# ============================================================================
# 테스트용 컴포넌트
# ============================================================================

@Component
class SimpleService:
    """단순 서비스"""
    
    def get_value(self) -> int:
        return 42


@Component
class DependentService:
    """의존성이 있는 서비스"""
    
    simple: SimpleService  # 타입 힌트로 의존성 선언
    
    def get_doubled(self) -> int:
        return self.simple.get_value() * 2


@Controller
@RequestMapping("/api")
class TestController:
    """테스트용 컨트롤러"""
    
    service: SimpleService  # 타입 힌트로 의존성 선언
    
    @Get("/value")
    def get_value(self) -> dict:
        return {"value": self.service.get_value()}


# ============================================================================
# BloomTestCase 기본 테스트
# ============================================================================

from bloom.tests import BloomTestCase


class TestBloomTestCaseBasic(BloomTestCase):
    """BloomTestCase 기본 기능 테스트"""
    
    components = [SimpleService]
    
    async def test_get_instance(self):
        """컨테이너에서 인스턴스 조회"""
        service = self.get_instance(SimpleService)
        assert service is not None
        assert service.get_value() == 42
    
    async def test_has_instance(self):
        """인스턴스 존재 확인"""
        assert self.has_instance(SimpleService)
    
    async def test_app_initialized(self):
        """Application이 초기화되었는지 확인"""
        assert self.app is not None
        assert self.manager is not None


class TestBloomTestCaseDependency(BloomTestCase):
    """의존성 주입 테스트"""
    
    components = [SimpleService, DependentService]
    
    async def test_dependency_injected(self):
        """의존성이 주입되었는지 확인"""
        service = self.get_instance(DependentService)
        assert service.simple is not None
        assert service.get_doubled() == 84
    
    async def test_assert_injected(self):
        """assert_injected 헬퍼 테스트"""
        service = self.get_instance(DependentService)
        simple = self.assert_injected(service, "simple", SimpleService)
        assert simple.get_value() == 42


class TestBloomTestCaseOverride(BloomTestCase):
    """Mock/Override 테스트"""
    
    components = [SimpleService, DependentService]
    
    async def test_override(self):
        """의존성 오버라이드"""
        class FakeSimpleService:
            def get_value(self) -> int:
                return 100
        
        with self.override(SimpleService, FakeSimpleService()):
            service = self.get_instance(SimpleService)
            assert service.get_value() == 100


class TestBloomTestCaseHttp(BloomTestCase):
    """HTTP 테스트"""
    
    components = [SimpleService, TestController]
    
    async def test_get_request(self):
        """GET 요청 테스트"""
        response = await self.get("/api/value")
        response.assert_ok()
        response.assert_json({"value": 42})
    
    async def test_client_property(self):
        """client 속성 테스트"""
        response = await self.client.get("/api/value")
        assert response.status_code == 200


class TestBloomTestCaseConfig(BloomTestCase):
    """설정 테스트"""
    
    components = []
    config = {"test": {"key": "test_value"}}
    
    async def test_config_loaded(self):
        """설정이 로드되었는지 확인"""
        config = self.app._config_manager.get_config()
        assert config["test"]["key"] == "test_value"


class TestBloomTestCaseIsolation(BloomTestCase):
    """테스트 격리 검증"""
    
    components = [SimpleService]
    
    async def test_isolation_a(self):
        """격리 테스트 A"""
        service = self.get_instance(SimpleService)
        assert service.get_value() == 42
    
    async def test_isolation_b(self):
        """격리 테스트 B - 이전 테스트와 독립적"""
        service = self.get_instance(SimpleService)
        assert service.get_value() == 42
