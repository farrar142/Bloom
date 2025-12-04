"""CALL 스코프 Repository 의존성 테스트

Controller → Service → Repository → AsyncSession 체인에서
CALL 스코프 의존성이 제대로 주입되는지 테스트합니다.
"""

import pytest
import asyncio
from dataclasses import dataclass
from typing import Any

from bloom.core import (
    Component,
    Service,
    Configuration,
    Factory,
    PostConstruct,
    get_container_manager,
    reset_container_manager,
)
from bloom.core.scope import ScopeEnum
from bloom.core.manager import ContainerManager
from bloom.core.proxy import LazyProxy
from bloom.core.decorators import register_factories_from_configuration


# =============================================================================
# Mock Components (Repository 패턴 시뮬레이션)
# =============================================================================


@dataclass
class MockAsyncSession:
    """AsyncSession 시뮬레이션"""
    id: int
    
    @property
    def dialect(self):
        return MockDialect()


class MockDialect:
    def select_sql(self, meta, where=None):
        return f"SELECT * FROM table WHERE {where}"


# =============================================================================
# Tests
# =============================================================================


class TestCallScopeRepositoryChain:
    """Controller → Service → Repository → AsyncSession 체인 테스트"""
    
    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        """테스트 전후 컨테이너 초기화"""
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()
    
    @pytest.mark.asyncio
    async def test_repository_async_session_injection(self):
        """Repository에 AsyncSession이 제대로 주입되는지 확인"""
        
        # CALL 스코프로 AsyncSession 팩토리 등록
        @Configuration
        class TestDatabaseConfig:
            _session_counter: int = 0
            
            @Factory(scope=ScopeEnum.CALL)
            async def async_session(self) -> MockAsyncSession:
                """매 CALL마다 새 세션 생성"""
                TestDatabaseConfig._session_counter += 1
                return MockAsyncSession(id=TestDatabaseConfig._session_counter)

        # Repository - AsyncSession 의존성
        @Component
        class TestUserRepository:
            async_session: MockAsyncSession  # CALL 스코프 의존성
            
            async def find_by_email(self, email: str) -> dict | None:
                # async_session.dialect 접근 시 LazyProxy가 resolve되어야 함
                sql = self.async_session.dialect.select_sql(None, where=f"email='{email}'")
                return {"email": email, "sql": sql}
        
        manager = get_container_manager()
        scope_manager = manager.scope_manager
        
        # Factory 메서드를 컨테이너에 등록
        register_factories_from_configuration(TestDatabaseConfig, manager)
        
        # CALL 스코프 시작
        frame_id = scope_manager.start_call()
        
        try:
            # Repository 인스턴스 가져오기
            repo = await manager.get_instance_async(TestUserRepository)
            
            # CALL 스코프 의존성은 LazyProxy가 아니라 실제 인스턴스가 주입됨
            async_session_field = vars(repo).get("async_session")
            print(f"async_session field type: {type(async_session_field)}")
            # CALL 스코프는 eager하게 resolve되므로 실제 MockAsyncSession이어야 함
            assert isinstance(async_session_field, MockAsyncSession), "async_session should be MockAsyncSession (eager resolved)"
            
            # find_by_email 호출 시 async_session.dialect 접근
            result = await repo.find_by_email("test@example.com")
            
            print(f"Result: {result}")
            assert result is not None
            assert "email" in result
            assert "sql" in result
        finally:
            await scope_manager.end_call(frame_id)
    
    @pytest.mark.asyncio
    async def test_service_to_repository_chain(self):
        """Service → Repository 체인에서 AsyncSession 접근"""
        
        @Configuration
        class TestDatabaseConfig2:
            _session_counter: int = 0
            
            @Factory(scope=ScopeEnum.CALL)
            async def async_session(self) -> MockAsyncSession:
                TestDatabaseConfig2._session_counter += 1
                return MockAsyncSession(id=TestDatabaseConfig2._session_counter)

        @Component
        class TestUserRepository2:
            async_session: MockAsyncSession
            
            async def find_by_email(self, email: str) -> dict | None:
                sql = self.async_session.dialect.select_sql(None, where=f"email='{email}'")
                return {"email": email, "sql": sql}

        @Service
        class TestUserService2:
            user_repo: TestUserRepository2
            
            async def get_user_by_email(self, email: str) -> dict | None:
                return await self.user_repo.find_by_email(email)
        
        manager = get_container_manager()
        scope_manager = manager.scope_manager
        
        # Factory 메서드를 컨테이너에 등록
        register_factories_from_configuration(TestDatabaseConfig2, manager)
        
        # CALL 스코프 컨텍스트 내에서 SINGLETON들을 미리 초기화
        frame_id = scope_manager.start_call()
        
        try:
            # 의존성 체인의 모든 SINGLETON을 미리 생성 (ScopeManager 캐싱)
            # Repository → Service 순서로 생성
            await manager.get_instance_async(TestUserRepository2)
            service = await manager.get_instance_async(TestUserService2)
            
            # 이제 Service 메서드 호출 시 LazyProxy가 캐시된 Repository를 반환
            result = await service.get_user_by_email("test@example.com")
            
            print(f"Service result: {result}")
            assert result is not None
            assert "email" in result
        finally:
            await scope_manager.end_call(frame_id)
    
    @pytest.mark.asyncio
    async def test_controller_full_chain(self):
        """Controller → Service → Repository → AsyncSession 전체 체인"""
        
        @Configuration
        class TestDatabaseConfig3:
            _session_counter: int = 0
            
            @Factory(scope=ScopeEnum.CALL)
            async def async_session(self) -> MockAsyncSession:
                TestDatabaseConfig3._session_counter += 1
                return MockAsyncSession(id=TestDatabaseConfig3._session_counter)

        @Component
        class TestUserRepository3:
            async_session: MockAsyncSession
            
            async def find_by_email(self, email: str) -> dict | None:
                sql = self.async_session.dialect.select_sql(None, where=f"email='{email}'")
                return {"email": email, "sql": sql}

        @Service
        class TestUserService3:
            user_repo: TestUserRepository3
            
            async def get_user_by_email(self, email: str) -> dict | None:
                return await self.user_repo.find_by_email(email)

        @Component
        class TestUserController3:
            user_service: TestUserService3
            
            async def get_user(self, email: str) -> dict:
                user = await self.user_service.get_user_by_email(email)
                return user or {"error": "not found"}
        
        manager = get_container_manager()
        scope_manager = manager.scope_manager
        
        # Factory 메서드를 컨테이너에 등록
        register_factories_from_configuration(TestDatabaseConfig3, manager)
        
        frame_id = scope_manager.start_call()
        
        try:
            # 의존성 체인의 모든 SINGLETON을 미리 생성 (의존성 순서대로)
            await manager.get_instance_async(TestUserRepository3)
            await manager.get_instance_async(TestUserService3)
            controller = await manager.get_instance_async(TestUserController3)
            
            result = await controller.get_user("test@example.com")
            
            print(f"Controller result: {result}")
            assert result is not None
            assert "email" in result
        finally:
            await scope_manager.end_call(frame_id)
    
    @pytest.mark.asyncio
    async def test_call_scope_creates_new_session_per_call(self):
        """각 CALL마다 새 AsyncSession이 생성되는지 확인"""
        
        @Configuration
        class TestDatabaseConfig4:
            _session_counter: int = 0
            
            @Factory(scope=ScopeEnum.CALL)
            async def async_session(self) -> MockAsyncSession:
                TestDatabaseConfig4._session_counter += 1
                return MockAsyncSession(id=TestDatabaseConfig4._session_counter)
        
        manager = get_container_manager()
        scope_manager = manager.scope_manager
        
        # Factory 메서드를 컨테이너에 등록
        register_factories_from_configuration(TestDatabaseConfig4, manager)
        
        # 첫 번째 CALL
        frame_id1 = scope_manager.start_call()
        try:
            session1 = await manager.get_instance_async(MockAsyncSession)
            session1_id = session1.id
        finally:
            await scope_manager.end_call(frame_id1)
        
        # 두 번째 CALL
        frame_id2 = scope_manager.start_call()
        try:
            session2 = await manager.get_instance_async(MockAsyncSession)
            session2_id = session2.id
        finally:
            await scope_manager.end_call(frame_id2)
        
        # 서로 다른 세션이어야 함
        print(f"Session 1 ID: {session1_id}, Session 2 ID: {session2_id}")
        assert session1_id != session2_id
