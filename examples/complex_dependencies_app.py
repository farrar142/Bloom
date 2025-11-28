"""
Bloom Framework - 복잡한 의존성 관계 데모 앱

다양한 DI 패턴을 시연합니다:
1. 기본 의존성 주입
2. 다중 레벨 의존성 (A → B → C → D)
3. 다이아몬드 의존성 (A → B, A → C, B → D, C → D)
4. Factory Chain (Creator → Modifier 체인)
5. 다이아몬드 Factory Chain (외부 의존성 포함)
6. Lazy 의존성 (순환 참조 해결)
7. 라이프사이클 훅 (@PostConstruct, @PreDestroy)
8. 미들웨어 체인
9. 에러 핸들러
10. 핸들러 패턴 (@Handler)
"""

import sys
from dataclasses import dataclass, field
from typing import Protocol

from bloom import Application, Component, Controller, Get, Lazy, Post, RequestMapping
from bloom.core.decorators import Factory, Handler, Order, PostConstruct, PreDestroy
from bloom.logging import generate_dependency_graph
from bloom.web.error import ErrorHandler
from bloom.web.http import HttpResponse, HttpRequest
from bloom.web.middleware import CorsMiddleware, Middleware, MiddlewareChain
from bloom.web.auth import Authentication, Authenticator, AuthMiddleware


@Component
class AuthenticatorA(Authenticator):
    def supports(self, request: HttpRequest) -> bool:
        return True

    def authenticate(self, request: HttpRequest) -> Authentication:
        # 간단한 인증 로직 (예: 헤더에서 토큰 확인)
        token = request.headers.get("Authorization")
        if token == "Bearer valid-token":
            return Authentication(user_id="user123")
        return Authentication(user_id=None)


@Component
class AuthenticatorB(Authenticator):
    def supports(self, request: HttpRequest) -> bool:
        return True

    def authenticate(self, request: HttpRequest) -> Authentication:
        # 간단한 인증 로직 (예: 헤더에서 토큰 확인)
        token = request.headers.get("Authorization")
        if token == "Bearer valid-token":
            return Authentication(user_id="user123")
        return Authentication(user_id=None)


@Component
class AuthenticatorC(Authenticator):
    def supports(self, request: HttpRequest) -> bool:
        return True

    def authenticate(self, request: HttpRequest) -> Authentication:
        # 간단한 인증 로직 (예: 헤더에서 토큰 확인)
        token = request.headers.get("Authorization")
        if token == "Bearer valid-token":
            return Authentication(user_id="user123")
        return Authentication(user_id=None)


@Component
class AuthConfiguration:
    @Factory
    def auth(self, authenticator_a: AuthenticatorA) -> Authenticator:
        return authenticator_a

    @Factory
    def auth_middleware(self, *authenticator: Authenticator) -> AuthMiddleware:
        middle_ware = AuthMiddleware()
        middle_ware.register(*authenticator)
        return middle_ware


# =============================================================================
# 1. 기본 의존성 주입
# =============================================================================


@Component
class Logger:
    """간단한 로거 컴포넌트"""

    def log(self, message: str) -> None:
        print(f"[LOG] {message}")


# =============================================================================
# 2. 다중 레벨 의존성 (A → B → C → D)
# =============================================================================


@Component
class DatabaseConnection:
    """Level 4: 최하위 레이어"""

    def __init__(self):
        self.connected = False

    @PostConstruct
    def connect(self):
        self.connected = True
        print("[DB] Connected to database")

    @PreDestroy
    def disconnect(self):
        self.connected = False
        print("[DB] Disconnected from database")

    def query(self, sql: str) -> list[dict]:
        return [{"id": 1, "name": "test"}]


@Component
class UserRepository:
    """Level 3: Repository 레이어"""

    db: DatabaseConnection
    logger: Logger

    def find_all(self) -> list[dict]:
        self.logger.log("Finding all users")
        return self.db.query("SELECT * FROM users")

    def find_by_id(self, user_id: int) -> dict | None:
        self.logger.log(f"Finding user by id: {user_id}")
        results = self.db.query(f"SELECT * FROM users WHERE id = {user_id}")
        return results[0] if results else None


@Component
class UserService:
    """Level 2: Service 레이어"""

    user_repository: UserRepository
    logger: Logger

    def get_all_users(self) -> list[dict]:
        self.logger.log("Getting all users from service")
        return self.user_repository.find_all()

    def get_user(self, user_id: int) -> dict | None:
        return self.user_repository.find_by_id(user_id)


@Controller
@RequestMapping("/api/users")
class UserController:
    """Level 1: Controller 레이어"""

    user_service: UserService
    logger: Logger

    @Get("")
    async def list_users(self) -> list[dict]:
        self.logger.log("Listing users")
        return self.user_service.get_all_users()

    @Get("/{user_id}")
    async def get_user(self, user_id: int) -> dict:
        user = self.user_service.get_user(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        return user


# =============================================================================
# 3. 다이아몬드 의존성 (A → B, A → C, B → D, C → D)
# =============================================================================


@Component
class CacheService:
    """다이아몬드 하단: 공통 의존성"""

    def __init__(self):
        self._cache: dict[str, object] = {}

    def get(self, key: str) -> object | None:
        return self._cache.get(key)

    def set(self, key: str, value: object) -> None:
        self._cache[key] = value


@Component
class ProductRepository:
    """다이아몬드 좌측: CacheService 의존"""

    cache: CacheService
    db: DatabaseConnection

    def find_product(self, product_id: int) -> dict | None:
        cached = self.cache.get(f"product:{product_id}")
        if cached:
            return cached  # type: ignore
        result = {"id": product_id, "name": f"Product {product_id}"}
        self.cache.set(f"product:{product_id}", result)
        return result


@Component
class OrderRepository:
    """다이아몬드 우측: CacheService 의존"""

    cache: CacheService
    db: DatabaseConnection

    def find_order(self, order_id: int) -> dict | None:
        cached = self.cache.get(f"order:{order_id}")
        if cached:
            return cached  # type: ignore
        result = {"id": order_id, "product_id": 1, "quantity": 2}
        self.cache.set(f"order:{order_id}", result)
        return result


@Component
class OrderService:
    """다이아몬드 상단: ProductRepository, OrderRepository 모두 의존"""

    product_repo: ProductRepository
    order_repo: OrderRepository
    logger: Logger

    def get_order_with_product(self, order_id: int) -> dict:
        order = self.order_repo.find_order(order_id)
        if not order:
            return {"error": "Order not found"}

        product = self.product_repo.find_product(order["product_id"])
        return {"order": order, "product": product}


# =============================================================================
# 4. Factory Chain (Creator → Modifier 체인)
# =============================================================================


@dataclass
class AppConfig:
    """앱 설정 - Factory Chain으로 생성"""

    debug: bool = False
    version: str = "1.0.0"
    features: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)


@Component
class ConfigFactory:
    """Factory Chain: 설정 객체 생성 및 수정 체인"""

    logger: Logger

    @Factory
    def create_config(self) -> AppConfig:
        """Creator: 기본 설정 생성"""
        self.logger.log("Creating base config")
        return AppConfig()

    @Factory
    @Order(1)
    def enable_debug(self, config: AppConfig) -> AppConfig:
        """Modifier 1: 디버그 모드 활성화"""
        self.logger.log("Enabling debug mode")
        config.debug = True
        return config

    @Factory
    @Order(2)
    def add_features(self, config: AppConfig) -> AppConfig:
        """Modifier 2: 기능 추가"""
        self.logger.log("Adding features")
        config.features.extend(["auth", "cache", "logging"])
        return config

    @Factory
    @Order(3)
    def add_metadata(self, config: AppConfig) -> AppConfig:
        """Modifier 3: 메타데이터 추가"""
        self.logger.log("Adding metadata")
        config.metadata["environment"] = "development"
        config.metadata["author"] = "Bloom Framework"
        return config


# =============================================================================
# 5. 다이아몬드 Factory Chain (외부 의존성 포함)
# =============================================================================


@dataclass
class RequestContext:
    """요청 컨텍스트 - 다이아몬드 Factory Chain으로 생성"""

    user_id: str | None = None
    session_id: str | None = None
    permissions: list[str] = field(default_factory=list)
    trace_id: str = ""


@Component
class AuthService:
    """인증 서비스 - RequestContext Factory에 주입됨"""

    logger: Logger

    def get_current_user(self) -> str:
        return "user_12345"

    def get_permissions(self, user_id: str) -> list[str]:
        return ["read", "write", "admin"]


@Component
class SessionService:
    """세션 서비스 - RequestContext Factory에 주입됨"""

    cache: CacheService

    def get_session_id(self) -> str:
        return "session_abc123"


@Component
class RequestContextFactory:
    """다이아몬드 Factory Chain: AuthService와 SessionService에 의존"""

    @Factory
    def create_context(self) -> RequestContext:
        """Creator: 빈 컨텍스트 생성"""
        import uuid

        return RequestContext(trace_id=str(uuid.uuid4())[:8])

    @Factory
    @Order(1)
    def add_auth(self, ctx: RequestContext, auth: AuthService) -> RequestContext:
        """Modifier 1: 인증 정보 추가 (AuthService 의존)"""
        ctx.user_id = auth.get_current_user()
        ctx.permissions = auth.get_permissions(ctx.user_id)
        return ctx

    @Factory
    @Order(2)
    def add_session(
        self, ctx: RequestContext, session: SessionService
    ) -> RequestContext:
        """Modifier 2: 세션 정보 추가 (SessionService 의존)"""
        ctx.session_id = session.get_session_id()
        return ctx


# =============================================================================
# 6. Lazy 의존성 (순환 참조 해결)
# =============================================================================


@Lazy
@Component
class EmailService:
    """이메일 서비스 - @Lazy로 순환 참조 해결"""

    logger: Logger

    def send_email(self, to: str, message: str) -> None:
        self.logger.log(f"Email to {to}: {message}")


@Component
class NotificationService:
    """알림 서비스 - EmailService를 주입 (EmailService가 Lazy이므로 순환 방지됨)"""

    logger: Logger
    email_service: EmailService  # LazyProxy가 주입됨

    def notify(self, message: str) -> None:
        self.logger.log(f"Notification: {message}")
        # Lazy 객체 접근 시 실제 인스턴스 반환
        self.email_service.send_email("admin@example.com", message)


# =============================================================================
# 7. 라이프사이클 훅 (@PostConstruct, @PreDestroy)
# =============================================================================


@Component
class ConnectionPool:
    """연결 풀 - 라이프사이클 훅 데모"""

    logger: Logger

    def __init__(self):
        self.connections: list[str] = []
        self.max_connections = 10

    @PostConstruct
    def initialize(self):
        """DI 완료 후 연결 풀 초기화"""
        self.logger.log("Initializing connection pool")
        for i in range(self.max_connections):
            self.connections.append(f"conn_{i}")
        self.logger.log(f"Created {len(self.connections)} connections")

    @PreDestroy
    def cleanup(self):
        """종료 시 연결 정리"""
        self.logger.log("Cleaning up connection pool")
        self.connections.clear()
        self.logger.log("All connections closed")

    def get_connection(self) -> str | None:
        return self.connections[0] if self.connections else None


# =============================================================================
# 8. 미들웨어 체인
# =============================================================================


@Component
class RequestLoggingMiddleware(Middleware):
    """요청 로깅 미들웨어"""

    async def __call__(self, request, call_next):
        print(f"[MIDDLEWARE] Request: {request.method} {request.path}")
        response = await call_next(request)
        print(f"[MIDDLEWARE] Response: {response.status_code}")
        return response


@Component
class TimingMiddleware(Middleware):
    """타이밍 미들웨어"""

    async def __call__(self, request, call_next):
        import time

        start = time.time()
        response = await call_next(request)
        elapsed = (time.time() - start) * 1000
        print(f"[TIMING] {request.path} took {elapsed:.2f}ms")
        return response


@Component
class CustomCorsMiddleware(CorsMiddleware):
    """커스텀 CORS 미들웨어"""

    allow_origins = ["http://localhost:3000", "https://example.com"]
    allow_methods = ["GET", "POST", "PUT", "DELETE"]
    allow_credentials = True


@Component
class MiddlewareConfig:
    """미들웨어 체인 구성"""

    @Factory
    def middleware_chain(self, *middlewares: Middleware) -> MiddlewareChain:
        chain = MiddlewareChain()
        chain.add_group_after(*middlewares)
        return chain


# =============================================================================
# 9. 에러 핸들러
# =============================================================================


class UserNotFoundError(Exception):
    """사용자를 찾을 수 없음"""

    def __init__(self, user_id: int):
        self.user_id = user_id
        super().__init__(f"User {user_id} not found")


class PermissionDeniedError(Exception):
    """권한 없음"""

    pass


@Component
class GlobalErrorHandlers:
    """글로벌 에러 핸들러"""

    logger: Logger

    @ErrorHandler(UserNotFoundError)
    def handle_user_not_found(self, error: UserNotFoundError) -> HttpResponse:
        self.logger.log(f"User not found: {error.user_id}")
        return HttpResponse(
            status_code=404,
            body={"error": str(error), "user_id": error.user_id},
        )

    @ErrorHandler(PermissionDeniedError)
    def handle_permission_denied(self, error: PermissionDeniedError) -> HttpResponse:
        self.logger.log(f"Permission denied: {error}")
        return HttpResponse(status_code=403, body={"error": "Permission denied"})

    @ErrorHandler(Exception)
    def handle_generic_error(self, error: Exception) -> HttpResponse:
        self.logger.log(f"Unhandled error: {error}")
        return HttpResponse(status_code=500, body={"error": "Internal server error"})


# =============================================================================
# 10. 핸들러 패턴 (@Handler)
# =============================================================================


class EventType:
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"
    ORDER_PLACED = "order.placed"


class EventHandlerProtocol(Protocol):
    """이벤트 핸들러 프로토콜"""

    def handle(self, event: dict) -> None: ...


@Component
class UserCreatedHandler:
    """사용자 생성 이벤트 핸들러"""

    logger: Logger
    email_service: EmailService

    @Handler(EventType.USER_CREATED)
    def handle(self, event: dict) -> None:
        self.logger.log(f"User created: {event}")
        self.email_service.send_email(event.get("email", ""), "Welcome!")


@Component
class UserUpdatedHandler:
    """사용자 업데이트 이벤트 핸들러"""

    logger: Logger

    @Handler(EventType.USER_UPDATED)
    def handle(self, event: dict) -> None:
        self.logger.log(f"User updated: {event}")


@Component
class OrderPlacedHandler:
    """주문 생성 이벤트 핸들러"""

    logger: Logger
    notification_service: NotificationService

    @Handler(EventType.ORDER_PLACED)
    def handle(self, event: dict) -> None:
        self.logger.log(f"Order placed: {event}")
        self.notification_service.notify(f"New order: {event.get('order_id')}")


# =============================================================================
# 추가 컨트롤러
# =============================================================================


@Controller
@RequestMapping("/api/orders")
class OrderController:
    """주문 컨트롤러"""

    order_service: OrderService
    logger: Logger

    @Get("/{order_id}")
    async def get_order(self, order_id: int) -> dict:
        return self.order_service.get_order_with_product(order_id)

    @ErrorHandler(ValueError)
    def handle_value_error(self, error: ValueError) -> HttpResponse:
        """컨트롤러 스코프 에러 핸들러"""
        return HttpResponse(status_code=400, body={"error": str(error)})


@Controller
class HealthController:
    """헬스체크 컨트롤러"""

    config: AppConfig
    context: RequestContext
    pool: ConnectionPool

    @Get("/health")
    async def health(self) -> dict:
        return {
            "status": "ok",
            "debug": self.config.debug,
            "version": self.config.version,
            "features": self.config.features,
            "trace_id": self.context.trace_id,
            "user_id": self.context.user_id,
            "connections": len(self.pool.connections),
        }

    @Get("/")
    async def root(self) -> dict:
        return {
            "message": "Complex Dependencies Demo",
            "endpoints": [
                "/health",
                "/api/users",
                "/api/users/{user_id}",
                "/api/orders/{order_id}",
            ],
        }


# =============================================================================
# 애플리케이션 생성
# =============================================================================

# 앱 인스턴스 (uvicorn에서 사용)
app: Application | None = None


def create_app(module: object | None = None) -> Application:
    """애플리케이션 생성 및 초기화

    Args:
        module: 스캔할 모듈. None이면 현재 모듈 사용.
    """
    global app
    if app is not None:
        return app

    from bloom.core.manager import ContainerManager, set_current_manager
    import sys

    # 새로운 manager 생성 및 설정
    manager = ContainerManager("complex-demo")
    set_current_manager(manager)

    # 스캔할 모듈 결정
    if module is None:
        # __main__으로 실행된 경우에도 현재 모듈 사용
        module = sys.modules.get("complex_dependencies_app") or sys.modules.get(
            "__main__"
        )

    app = Application("complex-demo", manager=manager).scan(module).ready()
    return app


# 직접 실행 시에만 앱 생성 및 그래프 출력
if __name__ == "__main__":
    import sys

    # __main__ 모듈을 complex_dependencies_app으로도 등록
    sys.modules["complex_dependencies_app"] = sys.modules["__main__"]

    app = create_app()
    print("\n" + "=" * 80)
    print("Generating Dependency Graph...")
    print("=" * 80 + "\n")

    graph = generate_dependency_graph(app.manager, "complex-dependency-graph.txt")
    print(graph)

    print("\n" + "=" * 80)
    print("Graph saved to: complex-dependency-graph.txt")
    print("=" * 80)

    # 일부 기능 테스트
    print("\n" + "=" * 80)
    print("Testing Components...")
    print("=" * 80 + "\n")

    # AppConfig 확인
    config = app.manager.get_instance(AppConfig)
    print(f"AppConfig: debug={config.debug}, version={config.version}")
    print(f"Features: {config.features}")
    print(f"Metadata: {config.metadata}")

    # RequestContext 확인
    ctx = app.manager.get_instance(RequestContext)
    print(f"\nRequestContext: user={ctx.user_id}, session={ctx.session_id}")
    print(f"Permissions: {ctx.permissions}")
    print(f"Trace ID: {ctx.trace_id}")

    # Lazy 의존성 테스트
    print("\n--- Testing Lazy Dependencies ---")
    notification = app.manager.get_instance(NotificationService)
    notification.notify("Test notification")

    print("\n" + "=" * 80)
    print("Run server: uv run uvicorn complex_dependencies_app:app.asgi --reload")
    print("=" * 80)
else:
    # uvicorn 등에서 임포트할 때 앱 생성
    app = create_app()
