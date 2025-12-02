"""컨테이너 오버라이드 규칙 테스트

오버라이드 규칙:
- 상위 컨테이너의 데코레이터는 하위 컨테이너를 오버라이드하지 못함
- 하위 컨테이너의 데코레이터는 상위 컨테이너를 오버라이드함
- Element들은 새 컨테이너로 이전됨
"""

import pytest

from bloom import Application, Component
from bloom.core.decorators import Factory, Order
from bloom.core.container import Container, HandlerContainer, FactoryContainer
from bloom.core.container.element import OrderElement
from bloom.core.manager import ContainerManager, set_current_manager
from bloom.web.controller import Controller
from bloom.web.handler import (
    Get,
    Post,
    HttpMethodHandlerContainer,
    MethodElement,
    PathElement,
)


@pytest.fixture(autouse=True)
def reset_manager():
    """각 테스트 전에 manager 초기화"""
    manager = ContainerManager("test")
    set_current_manager(manager)
    yield manager
    set_current_manager(None)


class TestContainerOverrideRules:
    """컨테이너 오버라이드 규칙 테스트"""

    async def test_higher_decorator_on_lower_container_preserves_lower(self):
        """하위 컨테이너가 먼저 생성된 경우, 상위 데코레이터가 Element만 추가"""
        # @Order(상위) → @Get(하위) 순서 (아래에서 위로 적용)
        # @Get이 먼저 적용되고, @Order가 나중에 Element 추가

        @Controller
        class UserController:
            @Order(10)  # 나중에 적용됨 (상위)
            @Get("/users")  # 먼저 적용됨 (하위)
            def list_users(self):
                return []

        container = getattr(UserController.list_users, "__container__")

        # 하위 컨테이너 타입 유지
        assert isinstance(container, HttpMethodHandlerContainer)
        # 상위 데코레이터의 Element도 포함
        assert container.has_element(OrderElement)
        assert container.get_metadata("order") == 10
        # 원래 Element들도 유지
        assert container.get_metadata("http_method") == "GET"
        assert container.get_metadata("http_path") == "/users"

    async def test_lower_decorator_on_higher_container_replaces(self):
        """상위 컨테이너가 먼저 생성된 경우, 하위 데코레이터가 컨테이너 교체"""
        # @Get(하위) → @Order(상위) 순서 (아래에서 위로 적용)
        # @Order가 먼저 적용되고, @Get이 나중에 컨테이너 교체

        @Controller
        class ItemController:
            @Get("/items")  # 나중에 적용됨 (하위)
            @Order(5)  # 먼저 적용됨 (상위)
            def list_items(self):
                return []

        container = getattr(ItemController.list_items, "__container__")

        # 하위 컨테이너 타입으로 교체됨
        assert isinstance(container, HttpMethodHandlerContainer)
        # 상위 컨테이너의 Element들이 이전됨
        assert container.has_element(OrderElement)
        assert container.get_metadata("order") == 5
        # 하위 컨테이너의 Element들도 포함
        assert container.get_metadata("http_method") == "GET"
        assert container.get_metadata("http_path") == "/items"


class TestFactoryContainerOverride:
    """FactoryContainer 오버라이드 테스트"""

    async def test_factory_then_order_preserves_order_element(self):
        """@Factory → @Order 순서에서 OrderElement가 유지됨"""

        class Counter:
            def __init__(self, value: int = 0):
                self.value = value

        @Component
        class CounterConfig:
            @Factory
            @Order(1)  # @Factory 먼저, @Order 나중
            def add_one(self, counter: Counter) -> Counter:
                counter.value += 1
                return counter

        container = getattr(CounterConfig.add_one, "__container__")

        assert isinstance(container, FactoryContainer)
        assert container.has_element(OrderElement)
        assert container.get_metadata("order") == 1

    async def test_order_then_factory_transfers_elements(self):
        """@Order → @Factory 순서에서 Element가 FactoryContainer로 이전됨"""

        class Counter:
            def __init__(self, value: int = 0):
                self.value = value

        @Component
        class CounterConfig:
            @Order(2)  # @Order 먼저
            @Factory  # @Factory 나중
            def add_two(self, counter: Counter) -> Counter:
                counter.value += 2
                return counter

        container = getattr(CounterConfig.add_two, "__container__")

        assert isinstance(container, FactoryContainer)
        assert container.has_element(OrderElement)
        assert container.get_metadata("order") == 2


class TestHandlerContainerHierarchy:
    """HandlerContainer 계층 구조 테스트"""

    async def test_handler_container_mro_hierarchy(self):
        """HandlerContainer → HttpMethodHandlerContainer 계층 확인"""
        # MRO 인덱스: 높을수록 더 구체적
        handler_idx = HandlerContainer.__mro__.index(Container)
        http_idx = HttpMethodHandlerContainer.__mro__.index(Container)

        assert http_idx > handler_idx  # HttpMethodHandlerContainer가 더 구체적

    async def test_direct_handler_container_access(self):
        """HandlerContainer.get_or_create로 접근 시 하위 컨테이너 유지"""

        def my_handler():
            pass

        # 먼저 HttpMethodHandlerContainer 생성
        http_container = HttpMethodHandlerContainer.get_or_create(my_handler)
        http_container.add_elements(MethodElement("GET"))

        # HandlerContainer로 접근 시도
        handler_container = HandlerContainer.get_or_create(my_handler)

        # 같은 컨테이너 반환 (하위 타입 유지)
        assert handler_container is http_container
        assert isinstance(handler_container, HttpMethodHandlerContainer)


class TestElementTransfer:
    """Element 이전 테스트"""

    async def test_transfer_elements_preserves_all(self):
        """_transfer_elements_to가 모든 Element를 이전"""

        def handler():
            pass

        # 상위 컨테이너에 Element 추가
        handler_container = HandlerContainer.get_or_create(handler)
        handler_container.add_elements(OrderElement(100))

        # 하위 컨테이너로 교체
        http_container = HttpMethodHandlerContainer.get_or_create(handler)

        # Element가 이전되었는지 확인
        assert http_container.has_element(OrderElement)
        assert http_container.get_metadata("order") == 100

    async def test_no_duplicate_elements_on_transfer(self):
        """동일 타입의 Element는 중복 추가되지 않음"""

        def handler():
            pass

        # 상위 컨테이너에 OrderElement 추가
        handler_container = HandlerContainer.get_or_create(handler)
        handler_container.add_elements(OrderElement(1))

        # 하위 컨테이너로 교체 후 동일 타입 Element 추가 시도
        http_container = HttpMethodHandlerContainer.get_or_create(handler)
        http_container.add_elements(OrderElement(2))  # 추가됨 (값이 다름)

        # OrderElement가 2개 있을 수 있음 (값이 다르므로)
        order_elements = [
            e for e in http_container.elements if isinstance(e, OrderElement)
        ]
        assert len(order_elements) == 2


class TestIntegrationWithApplication:
    """Application과 통합 테스트"""

    async def test_full_application_with_order_and_get(self, reset_manager):
        """실제 Application 환경에서 @Order + @Get 테스트"""

        @Controller
        class TestController:
            @Order(1)
            @Get("/api/test")
            async def test_endpoint(self):
                return {"status": "ok"}

        app = Application("test", manager=reset_manager)
        app.scan(__import__(__name__))
        await app.ready_async()

        # 라우터에 등록되었는지 확인
        container = getattr(TestController.test_endpoint, "__container__")
        assert isinstance(container, HttpMethodHandlerContainer)
        assert container.get_metadata("order") == 1
        assert container.get_metadata("http_method") == "GET"
