"""DecoratorContainer 함수 내부 인젝션 테스트"""

import pytest
from typing import Any, Awaitable, Callable, Coroutine
from functools import wraps

from bloom.core.container import (
    Container,
    CallableContainer,
    HandlerContainer,
    DecoratorContainer,
    decorator,
)
from bloom.core.container.decorator import ADecorator, ACallable
from bloom.core.decorators import Component, Handler
from bloom.core.container.element import Element, OrderElement
from bloom.core.manager import ContainerManager, set_current_manager


@pytest.fixture(autouse=True)
def reset_manager():
    """각 테스트 전에 manager 초기화"""
    manager = ContainerManager("test")
    set_current_manager(manager)
    yield manager
    set_current_manager(None)


class TestDecoratorInjection:
    async def test_decorator_cannot_injected(self, reset_manager: ContainerManager):
        from bloom import Application

        def outer[**P, R](
            func: ACallable[P, R],
        ) -> ACallable[P, R]:
            @wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs):
                return await func(*args, **kwargs)

            return wrapper

        def outer2[**P, R](
            func: Callable[P, R],
        ) -> Callable[P, R]:
            @wraps(func)
            def wrapper(*args: P.args, **kwargs: P.kwargs):
                return func(*args, **kwargs)

            return wrapper

        @Component
        class MyComponent:
            @decorator(outer)
            async def my_method(self, x: int) -> int:
                return x * 2

            @decorator(outer2)
            def my_method2(self, x: int) -> int:
                return x + 3

        app = Application("test_app", manager=reset_manager)
        app.scan(__import__(__name__))
        await app.ready_async()
        comp = reset_manager.get_instance(MyComponent, raise_exception=True)
        result = await comp.my_method(5)
        result2 = comp.my_method2(7)
        assert result + result2 == 20

        pass
