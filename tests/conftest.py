"""Test utilities for ASGI applications"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
import pytest
from httpx import AsyncClient
from httpx._transports.asgi import ASGITransport
from bloom.web.asgi import ASGIApplication
from bloom.web import GetMapping, Controller
from bloom import Application
from bloom.core import Component, Service, Handler, Factory
from bloom.web.decorators import PostMapping
from bloom.web.params import Cookie, Header, KeyValue


# =============================================================================
# Factory 테스트용 데이터 클래스
# =============================================================================


@dataclass
class User:
    """테스트용 User 클래스"""

    name: str
    email: str = ""
    enhanced: bool = False
    processed: bool = False
    notified: bool = False


@dataclass
class Config:
    """테스트용 Config 클래스"""

    debug: bool = False
    timeout: int = 30


# =============================================================================
# Factory 테스트용 서비스 및 Factory 클래스
# =============================================================================


@Service
class EmailService:
    """이메일 서비스 (Factory 의존성 테스트용)"""

    def send_welcome(self, user: User) -> None:
        user.notified = True


@Factory
class UserFactory:
    """User 생성 및 수정 Factory"""

    email_service: EmailService

    def create(self, name: str, email: str = "") -> User:
        """동기 Creator: User 생성"""
        return User(name=name, email=email)

    async def create_async(self, name: str) -> User:
        """비동기 Creator: User 생성"""
        return User(name=name, processed=True)

    def create_and_notify(self, name: str) -> User:
        """의존성 주입을 사용하는 Creator"""
        user = User(name=name)
        self.email_service.send_welcome(user)
        return user

    def enhance(self, user: User) -> User:
        """동기 Modifier: User 강화"""
        user.enhanced = True
        return user

    async def process_async(self, user: User) -> User:
        """비동기 Modifier: User 처리"""
        user.processed = True
        return user


@Factory
class ConfigFactory:
    """Config 생성 및 수정 Factory"""

    def create(self) -> Config:
        """Config 생성"""
        return Config()

    def update(self, config: Config) -> Config:
        """Config 수정 (Modifier)"""
        config.debug = True
        return config


@Factory
class UserEnhancerFactory:
    """User 강화 전용 Factory (다중 Factory 테스트용)"""

    def enhance_extra(self, user: User) -> User:
        """추가 강화 Modifier"""
        user.enhanced = True
        return user


@Factory
class UserProcessorFactory:
    """User 처리 전용 Factory (다중 Factory 테스트용)"""

    def process_extra(self, user: User) -> User:
        """추가 처리 Modifier"""
        user.processed = True
        return user


# =============================================================================
# 복잡한 Factory 체인 테스트용 컴포넌트
# =============================================================================


@dataclass
class Order:
    """주문 데이터 클래스"""

    id: str
    user_name: str
    total: float = 0.0
    validated: bool = False
    discounted: bool = False
    notified: bool = False
    logged: bool = False


@dataclass
class Product:
    """상품 데이터 클래스"""

    name: str
    price: float
    in_stock: bool = True


@dataclass
class Report:
    """리포트 데이터 클래스"""

    title: str
    data: dict | None = None
    formatted: bool = False
    exported: bool = False


# 레벨 1: 기본 서비스들
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


@Service
class DiscountService:
    """할인 서비스"""

    def calculate_discount(self, total: float, rate: float = 0.1) -> float:
        return total * (1 - rate)


# 레벨 2: 레벨 1 서비스에 의존하는 컴포넌트
@Component
class ValidationComponent:
    """검증 컴포넌트 - LoggingService에 의존"""

    logging_service: LoggingService

    def validate_order(self, order: Order) -> bool:
        self.logging_service.log(f"Validating order {order.id}")
        return order.total > 0

    def validate_product(self, product: Product) -> bool:
        self.logging_service.log(f"Validating product {product.name}")
        return product.price > 0 and product.in_stock


# 레벨 3: 레벨 1, 2에 의존하는 Factory
@Factory
class OrderFactory:
    """주문 Factory - 여러 서비스에 의존"""

    logging_service: LoggingService
    notification_service: NotificationService
    discount_service: DiscountService
    validation_component: ValidationComponent

    def create_order(self, id: str, user_name: str, total: float) -> Order:
        """Creator: 주문 생성"""
        self.logging_service.log(f"Creating order {id}")
        return Order(id=id, user_name=user_name, total=total)

    async def create_with_notification(
        self, id: str, user_name: str, total: float
    ) -> Order:
        """Async Creator: 알림과 함께 주문 생성"""
        order = Order(id=id, user_name=user_name, total=total)
        self.notification_service.notify(f"Order {id} created for {user_name}")
        self.logging_service.log(f"Order {id} created with notification")
        return order

    def validate(self, order: Order) -> Order:
        """Modifier: 주문 검증"""
        if self.validation_component.validate_order(order):
            order.validated = True
        return order

    def apply_discount(self, order: Order) -> Order:
        """Modifier: 할인 적용"""
        order.total = self.discount_service.calculate_discount(order.total)
        order.discounted = True
        self.logging_service.log(f"Discount applied to order {order.id}")
        return order

    async def notify_order(self, order: Order) -> Order:
        """Async Modifier: 주문 알림"""
        self.notification_service.notify(
            f"Order {order.id} processed for {order.user_name}"
        )
        order.notified = True
        return order


@Factory
class ProductFactory:
    """상품 Factory"""

    logging_service: LoggingService
    validation_component: ValidationComponent

    def create_product(self, name: str, price: float) -> Product:
        """Creator: 상품 생성"""
        self.logging_service.log(f"Creating product {name}")
        return Product(name=name, price=price)

    def mark_out_of_stock(self, product: Product) -> Product:
        """Modifier: 품절 처리"""
        product.in_stock = False
        self.logging_service.log(f"Product {product.name} marked out of stock")
        return product


# 레벨 4: 다른 Factory에 의존하는 Factory (Factory 체인)
@Factory
class ReportFactory:
    """리포트 Factory - 다른 서비스들과 Factory에 의존"""

    logging_service: LoggingService
    notification_service: NotificationService

    def create_report(self, title: str) -> Report:
        """Creator: 리포트 생성"""
        self.logging_service.log(f"Creating report: {title}")
        return Report(title=title)

    def create_order_report(self, title: str, order: Order) -> Report:
        """Creator: 주문 리포트 생성"""
        self.logging_service.log(f"Creating order report: {title}")
        return Report(title=title, data={"order_id": order.id, "total": order.total})

    def format_report(self, report: Report) -> Report:
        """Modifier: 리포트 포맷팅"""
        report.formatted = True
        self.logging_service.log(f"Report '{report.title}' formatted")
        return report

    async def export_report(self, report: Report) -> Report:
        """Async Modifier: 리포트 내보내기"""
        report.exported = True
        self.notification_service.notify(f"Report '{report.title}' exported")
        self.logging_service.log(f"Report '{report.title}' exported")
        return report


# 순환 의존성 없는 복잡한 컴포넌트
@Component
class OrderProcessingComponent:
    """주문 처리 컴포넌트 - 여러 서비스에 의존"""

    logging_service: LoggingService
    notification_service: NotificationService
    discount_service: DiscountService
    validation_component: ValidationComponent

    async def process_order(self, order: Order) -> Order:
        """주문 전체 처리 파이프라인"""
        self.logging_service.log(f"Processing order {order.id}")

        # 검증
        if self.validation_component.validate_order(order):
            order.validated = True

        # 할인 적용
        order.total = self.discount_service.calculate_discount(order.total)
        order.discounted = True

        # 알림
        self.notification_service.notify(f"Order {order.id} processed")
        order.notified = True

        return order


# =============================================================================
# 기존 ASGI 테스트용 컴포넌트
# =============================================================================


@Service
class MyService:
    @Handler
    async def greet(self, name: str) -> str:
        return f"Hello, {name}!"

    async def auto_converted_handler(self, name: str) -> str:
        await self.greet(name)  # This will be auto-converted to async
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
    # 애플리케이션 종료 로직이 필요하면 여기에 추가


@pytest.fixture(scope="session", autouse=True)
def asgi(application) -> ASGIApplication:
    """ASGI 애플리케이션 초기화 fixture"""
    asgi_app = ASGIApplication(application, debug=True)

    return asgi_app


@pytest.fixture
def asgi_client(asgi) -> AsyncClient:
    """ASGI 앱을 테스트하기 위한 httpx 클라이언트 fixture"""
    # httpx 클라이언트 생성 (ASGI transport 사용)

    transport = ASGITransport(app=asgi)
    client = AsyncClient(transport=transport, base_url="http://testserver")
    return client
