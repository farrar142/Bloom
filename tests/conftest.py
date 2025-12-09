"""Test utilities for ASGI applications"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal
import pytest
from httpx import AsyncClient
from httpx._transports.asgi import ASGITransport
from bloom.web.asgi import ASGIApplication
from bloom.web import GetMapping, Controller
from bloom import Application
from bloom.core import (
    Component,
    Service,
    Handler,
    Configuration,
    Factory,
    Scoped,
    Scope,
)
from bloom.core.decorators import Transactional
from bloom.core.abstract.autocloseable import AutoCloseable, AsyncAutoCloseable
from bloom.web.decorators import PostMapping
from bloom.web.params import Cookie, Header, KeyValue


# =============================================================================
# Factory 테스트용 데이터 클래스 (외부 라이브러리처럼 @Service 없는 클래스)
# =============================================================================


@dataclass
class DatabaseConnection:
    """데이터베이스 연결 (외부 라이브러리 클래스 시뮬레이션)"""

    host: str
    port: int
    connected: bool = False


@dataclass
class CacheClient:
    """캐시 클라이언트 (외부 라이브러리 클래스 시뮬레이션)"""

    host: str
    ttl: int = 300


@dataclass
class AppSettings:
    """애플리케이션 설정"""

    debug: bool = False
    timeout: int = 30
    max_connections: int = 100


# =============================================================================
# Scope 테스트용 AutoCloseable 클래스들
# =============================================================================


class DatabaseSession(AutoCloseable):
    """데이터베이스 세션 - CALL 스코프에서 자동 close"""

    _instance_count: int = 0
    _close_count: int = 0

    def __init__(self, connection: DatabaseConnection):
        self.connection = connection
        self.session_id = DatabaseSession._instance_count
        DatabaseSession._instance_count += 1
        self.is_active = False
        self.queries: list[str] = []

    def __enter__(self):
        self.is_active = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.is_active = False
        DatabaseSession._close_count += 1

    def execute(self, query: str) -> str:
        if not self.is_active:
            raise RuntimeError("Session is not active")
        self.queries.append(query)
        return f"Executed: {query}"

    @classmethod
    def reset_counters(cls):
        cls._instance_count = 0
        cls._close_count = 0


class AsyncDatabaseSession(AsyncAutoCloseable):
    """비동기 데이터베이스 세션 - CALL 스코프에서 자동 close"""

    _instance_count: int = 0
    _close_count: int = 0

    def __init__(self, connection: DatabaseConnection):
        self.connection = connection
        self.session_id = AsyncDatabaseSession._instance_count
        AsyncDatabaseSession._instance_count += 1
        self.is_active = False
        self.queries: list[str] = []

    async def __aenter__(self):
        self.is_active = True
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        self.is_active = False
        AsyncDatabaseSession._close_count += 1

    async def execute(self, query: str) -> str:
        if not self.is_active:
            raise RuntimeError("Session is not active")
        self.queries.append(query)
        return f"Executed: {query}"

    @classmethod
    def reset_counters(cls):
        cls._instance_count = 0
        cls._close_count = 0


@dataclass
class RequestContext:
    """요청 컨텍스트 - REQUEST 스코프에서 공유"""

    request_id: str = ""
    user_id: str | None = None
    data: dict = field(default_factory=dict)


# =============================================================================
# Factory으로 생성될 클래스들 (외부 라이브러리처럼 @Service 없음)
# Configuration 클래스보다 먼저 정의해야 타입 힌트 해석이 가능
# =============================================================================


class UserRepository:
    """사용자 저장소 - @Service 없이 Factory으로만 등록"""

    def __init__(self, db: DatabaseConnection):
        self.db = db
        self.users: dict[str, dict] = {}

    def save(self, user_id: str, data: dict) -> None:
        self.users[user_id] = data

    def find(self, user_id: str) -> dict | None:
        return self.users.get(user_id)


class UserService:
    """사용자 서비스 - @Service 없이 Factory으로만 등록"""

    def __init__(self, repository: UserRepository, cache: CacheClient):
        self.repository = repository
        self.cache = cache
        self.initialized = False

    async def initialize(self) -> None:
        """비동기 초기화"""
        self.initialized = True

    def create_user(self, user_id: str, name: str) -> dict:
        user = {"id": user_id, "name": name}
        self.repository.save(user_id, user)
        return user

    def get_user(self, user_id: str) -> dict | None:
        return self.repository.find(user_id)


# =============================================================================
# 기본 서비스들 (@Service로 등록)
# =============================================================================


@Service
class LoggingService:
    """로깅 서비스"""

    logs: list[str]

    def __init__(self):
        self.logs = []

    def log(self, message: str) -> None:
        self.logs.append(message)


@Service
class NotificationService:
    """알림 서비스"""

    notifications: list[str]

    def __init__(self):
        self.notifications = []

    def notify(self, message: str) -> None:
        self.notifications.append(message)


# =============================================================================
# Configuration 클래스 - @Factory으로 외부 클래스 인스턴스 생성
# =============================================================================


@Configuration
class InfrastructureConfig:
    """인프라 설정 - 외부 라이브러리 클래스들을 Factory으로 등록"""

    @Factory
    def database_connection(self) -> DatabaseConnection:
        """데이터베이스 연결 Factory 생성"""
        conn = DatabaseConnection(host="localhost", port=5432)
        conn.connected = True
        return conn

    @Factory
    def cache_client(self) -> CacheClient:
        """캐시 클라이언트 Factory 생성"""
        return CacheClient(host="localhost", ttl=600)

    @Factory
    def app_settings(self) -> AppSettings:
        """애플리케이션 설정 Factory 생성"""
        return AppSettings(debug=True, timeout=60, max_connections=50)


@Configuration
class ServiceConfig:
    """서비스 설정 - 다른 Factory에 의존하는 Factory들"""

    logging_service: LoggingService  # @Service로 등록된 서비스 주입

    @Factory
    def user_repository(self, db: DatabaseConnection) -> UserRepository:
        """UserRepository Factory 생성 - DatabaseConnection Factory에 의존"""
        self.logging_service.log("Creating UserRepository Factory")
        return UserRepository(db)

    @Factory
    async def user_service(
        self, user_repo: UserRepository, cache: CacheClient
    ) -> UserService:
        """UserService Factory 생성 - 비동기 초기화"""
        self.logging_service.log("Creating UserService Factory")
        service = UserService(user_repo, cache)
        await service.initialize()
        return service


@Configuration
class ScopedFactoryConfig:
    """Scope가 적용된 Factory들"""

    @Factory
    @Scoped(Scope.CALL)
    def database_session(self, db: DatabaseConnection) -> DatabaseSession:
        """CALL 스코프 세션 - 핸들러 호출마다 새로 생성, 자동 close"""
        return DatabaseSession(db)

    @Factory
    @Scoped(Scope.CALL)
    async def async_database_session(
        self, db: DatabaseConnection
    ) -> AsyncDatabaseSession:
        """CALL 스코프 비동기 세션"""
        return AsyncDatabaseSession(db)

    @Factory
    @Scoped(Scope.REQUEST)
    def request_context(self) -> RequestContext:
        """REQUEST 스코프 컨텍스트 - HTTP 요청 내 공유"""
        import uuid

        return RequestContext(request_id=str(uuid.uuid4()))


# =============================================================================
# Scoped Component 테스트용 클래스들
# =============================================================================


@Component
@Scoped(Scope.CALL)
class CallScopedComponent(AutoCloseable):
    """CALL 스코프 컴포넌트 - 핸들러 호출마다 새로 생성, 자동 close"""

    _instances: list["CallScopedComponent"] = []
    _close_order: list[int] = []

    def __init__(self):
        self.id = len(CallScopedComponent._instances)
        self.is_active = True
        CallScopedComponent._instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.is_active = False
        CallScopedComponent._close_order.append(self.id)

    @classmethod
    def _reset(cls):
        cls._instances = []
        cls._close_order = []


@Scoped(Scope.REQUEST)
@Component
class RequestScopedComponent:
    """REQUEST 스코프 컴포넌트 - HTTP 요청 내 공유"""

    _instances: list["RequestScopedComponent"] = []

    def __init__(self):
        self.id = len(RequestScopedComponent._instances)
        self.data: dict = {}
        RequestScopedComponent._instances.append(self)

    @classmethod
    def _reset(cls):
        cls._instances = []


@Service
class ServiceUsingCallScopedComponent:
    """CALL 스코프 컴포넌트를 사용하는 서비스"""

    call_scoped: CallScopedComponent

    @Handler
    @Transactional
    async def do_work(self) -> int:
        """CALL 스코프 컴포넌트 사용"""
        return self.call_scoped.id


@Service
class ServiceUsingRequestScopedComponent:
    """REQUEST 스코프 컴포넌트를 사용하는 서비스"""

    request_scoped: RequestScopedComponent

    @Handler
    async def set_data(self, key: str, value: str) -> None:
        """REQUEST 스코프 컴포넌트에 데이터 설정"""
        self.request_scoped.data[key] = value

    @Handler
    async def get_data(self, key: str) -> str | None:
        """REQUEST 스코프 컴포넌트에서 데이터 조회"""
        return self.request_scoped.data.get(key)


# =============================================================================
# 기존 ASGI 테스트용 컴포넌트
# =============================================================================


@Service
class MyService:
    @Handler
    async def greet(self, name: str) -> str:
        return f"Hello, {name}!"

    async def auto_converted_handler(self, name: str) -> str:
        await self.greet(name)
        return f"Hi, {name}!"


@Service
class SyncAsyncService:
    async def async_handler(self, value: int) -> int:
        return value * 2

    @Handler
    def sync_handler(self, value: int) -> int:
        return value + 2


@Component
class MyComponent:
    service: MyService
    synca_async_service: SyncAsyncService
    cache_client: CacheClient


@Controller
class MyController:
    component: MyComponent

    @GetMapping(path="/greet/{name}")
    async def greet_handler(self, name: str) -> dict:
        print(f"greet_handler called with name={name}")
        return {"message": await self.component.service.greet(name)}

    @PostMapping(path="/post/{post}")
    async def post_handler(self, field: int, post: int) -> dict:
        return {"field": field, "post": post}

    @PostMapping(path="/post/static")
    async def static_post_handler(
        self,
        authorization: Cookie[Literal["X-AUTHORIZATION"]],
        user_agent: Header,
    ) -> dict:
        print(authorization.value)
        return {"authorization": authorization.value, "user_agent": user_agent.value}


@pytest.fixture(scope="session", autouse=True)
def application() -> Application:
    """애플리케이션 초기화 및 종료를 위한 fixture"""
    return Application()


@pytest.fixture(scope="session", autouse=True)
def asgi(application) -> ASGIApplication:
    """ASGI 애플리케이션 초기화 fixture"""
    asgi_app = ASGIApplication(application, debug=True)
    return asgi_app


@pytest.fixture
def asgi_client(asgi) -> AsyncClient:
    """ASGI 앱을 테스트하기 위한 httpx 클라이언트 fixture"""
    transport = ASGITransport(app=asgi)
    client = AsyncClient(transport=transport, base_url="http://testserver")
    return client
