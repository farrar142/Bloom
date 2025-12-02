"""Factory Scope 테스트

@Factory + @Scope(PROTOTYPE, CALL_SCOPED) 동작 검증:
1. PROTOTYPE: 매번 새 인스턴스 생성
2. CALL_SCOPED: 같은 호출 스택 내에서는 같은 인스턴스 공유
"""

import pytest
from bloom import Application, Component, Factory
from bloom.core.decorators import Scope
from bloom.core.container.element import Scope as ScopeEnum, PrototypeMode


class TestFactoryPrototypeScope:
    """PROTOTYPE 스코프 Factory 테스트"""

    async def test_prototype_creates_new_instance_each_time(self):
        """PROTOTYPE Factory는 매번 새 인스턴스를 생성해야 함"""
        call_count = 0

        class FakeSession:
            def __init__(self, id: int):
                self.id = id

        @Component
        class SessionFactory:
            def create(self) -> FakeSession:
                nonlocal call_count
                call_count += 1
                return FakeSession(call_count)

        @Component
        class DatabaseConfig:
            factory: SessionFactory

            @Factory
            @Scope(ScopeEnum.CALL)
            def session(self) -> FakeSession:
                return self.factory.create()

        @Component
        class Repository1:
            session: FakeSession

        @Component
        class Repository2:
            session: FakeSession

        app = Application("test")
        app.scan(SessionFactory, DatabaseConfig, Repository1, Repository2)
        await app.ready_async()

        repo1 = app.manager.get_instance(Repository1)
        repo2 = app.manager.get_instance(Repository2)

        # 각각 다른 Session 인스턴스를 가져야 함
        assert repo1.session.id != repo2.session.id
        assert call_count == 2


class TestFactoryCallScopedMode:
    """CALL_SCOPED 모드 Factory 테스트"""

    async def test_call_scoped_shares_instance_in_same_call_stack(self):
        """CALL_SCOPED는 같은 호출 스택 내에서 같은 인스턴스를 공유해야 함"""
        call_count = 0

        class FakeSession:
            def __init__(self, id: int):
                self.id = id

        @Component
        class SessionFactory:
            def create(self) -> FakeSession:
                nonlocal call_count
                call_count += 1
                return FakeSession(call_count)

        @Component
        class DatabaseConfig:
            factory: SessionFactory

            @Factory
            @Scope(ScopeEnum.CALL, PrototypeMode.CALL_SCOPED)
            def session(self) -> FakeSession:
                return self.factory.create()

        @Component
        class UserRepository:
            session: FakeSession

            def get_session_id(self) -> int:
                return self.session.id

        @Component
        class PostRepository:
            session: FakeSession

            def get_session_id(self) -> int:
                return self.session.id

        @Component
        class UserService:
            user_repo: UserRepository
            post_repo: PostRepository

            def get_both_session_ids(self) -> tuple[int, int]:
                """같은 호출 내에서 두 Repository의 session id 반환"""
                return (
                    self.user_repo.get_session_id(),
                    self.post_repo.get_session_id(),
                )

        app = Application("test")
        app.scan(
            SessionFactory, DatabaseConfig, UserRepository, PostRepository, UserService
        )
        await app.ready_async()

        service = app.manager.get_instance(UserService)

        # 핸들러 컨텍스트 시뮬레이션 with call_scope
        from bloom.core.advice.tracing import call_scope

        # 첫 번째 호출 - 핸들러 컨텍스트 내에서 같은 session 공유
        with call_scope(service, "get_both_session_ids", trace_id="test-1"):
            id1, id2 = service.get_both_session_ids()
            assert id1 == id2, "같은 호출 스택 내에서는 같은 Session을 공유해야 함"

        # 두 번째 호출 - 새로운 핸들러 컨텍스트
        with call_scope(service, "get_both_session_ids", trace_id="test-2"):
            id3, id4 = service.get_both_session_ids()
            assert id3 == id4, "같은 호출 스택 내에서는 같은 Session을 공유해야 함"
            assert id1 != id3, "새로운 호출에서는 새로운 Session을 생성해야 함"

    async def test_call_scoped_releases_after_call_ends(self):
        """CALL_SCOPED 인스턴스는 호출 종료 후 해제되어야 함"""
        created_sessions: list = []

        class FakeSession:
            def __init__(self, id: int):
                self.id = id
                self.closed = False
                created_sessions.append(self)

        @Component
        class SessionFactory:
            _counter = 0

            def create(self) -> FakeSession:
                self._counter += 1
                return FakeSession(self._counter)

        @Component
        class DatabaseConfig:
            factory: SessionFactory

            @Factory
            @Scope(ScopeEnum.CALL, PrototypeMode.CALL_SCOPED)
            def session(self) -> FakeSession:
                return self.factory.create()

        @Component
        class Repository:
            session: FakeSession

            def do_work(self) -> int:
                return self.session.id

        app = Application("test")
        app.scan(SessionFactory, DatabaseConfig, Repository)
        await app.ready_async()

        repo = app.manager.get_instance(Repository)

        # 여러 번 호출
        ids = [repo.do_work() for _ in range(3)]

        # 각 호출마다 새로운 Session이 생성되어야 함
        assert len(set(ids)) == 3, "각 호출마다 새로운 Session이 생성되어야 함"
        assert len(created_sessions) == 3


class TestFactorySingletonScope:
    """SINGLETON 스코프 Factory 테스트 (기본값)"""

    async def test_singleton_factory_creates_once(self):
        """SINGLETON Factory는 한 번만 인스턴스를 생성해야 함"""
        call_count = 0

        class FakeConnection:
            def __init__(self, id: int):
                self.id = id

        @Component
        class ConnectionFactory:
            def create(self) -> FakeConnection:
                nonlocal call_count
                call_count += 1
                return FakeConnection(call_count)

        @Component
        class DatabaseConfig:
            factory: ConnectionFactory

            @Factory  # 기본값 SINGLETON
            def connection(self) -> FakeConnection:
                return self.factory.create()

        @Component
        class Service1:
            conn: FakeConnection

        @Component
        class Service2:
            conn: FakeConnection

        app = Application("test")
        app.scan(ConnectionFactory, DatabaseConfig, Service1, Service2)
        await app.ready_async()

        svc1 = app.manager.get_instance(Service1)
        svc2 = app.manager.get_instance(Service2)

        # 같은 인스턴스를 공유해야 함
        assert svc1.conn.id == svc2.conn.id
        assert call_count == 1
