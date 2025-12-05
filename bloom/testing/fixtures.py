"""bloom.testing.fixtures - pytest 픽스처 통합"""

from __future__ import annotations

import functools
from typing import Callable, TypeVar, Any

F = TypeVar("F", bound=Callable[..., Any])


def fixture(
    func: F | None = None,
    *,
    autouse: bool = False,
    scope: str = "function",
    name: str | None = None,
) -> F | Callable[[F], F]:
    """
    pytest 스타일 픽스처 데코레이터.

    BloomTestCase와 함께 사용하여 테스트 픽스처를 정의합니다.

    사용 예:
        class MyTest(BloomTestCase):
            @fixture
            async def sample_user(self) -> User:
                return User(name="Test")

            @fixture(autouse=True)
            async def setup_db(self):
                await self.db.connect()
                yield
                await self.db.disconnect()

            async def test_with_user(self, sample_user: User):
                assert sample_user.name == "Test"

    Args:
        func: 데코레이트할 함수
        autouse: True면 모든 테스트에 자동 적용
        scope: 픽스처 스코프 ("function", "class", "module", "session")
        name: 픽스처 이름 (기본값: 함수 이름)

    Returns:
        데코레이트된 픽스처 함수
    """

    def decorator(fn: F) -> F:
        # 픽스처 메타데이터 설정
        fn._bloom_fixture = True
        fn._bloom_fixture_autouse = autouse
        fn._bloom_fixture_scope = scope
        fn._bloom_fixture_name = name or fn.__name__

        @functools.wraps(fn)
        async def wrapper(self, *args, **kwargs):
            result = fn(self, *args, **kwargs)
            # async generator (yield 사용) 지원
            if hasattr(result, "__anext__"):
                return result
            # coroutine 지원
            if hasattr(result, "__await__"):
                return await result
            return result

        # 메타데이터 복사
        wrapper._bloom_fixture = True
        wrapper._bloom_fixture_autouse = autouse
        wrapper._bloom_fixture_scope = scope
        wrapper._bloom_fixture_name = name or fn.__name__

        return wrapper  # type: ignore

    if func is None:
        return decorator
    return decorator(func)


class FixtureManager:
    """
    픽스처 관리자.

    테스트 클래스의 픽스처를 수집하고 실행합니다.
    """

    def __init__(self, test_instance):
        self.test_instance = test_instance
        self._fixtures: dict[str, Callable] = {}
        self._fixture_values: dict[str, Any] = {}
        self._teardown_stack: list[Any] = []

    def collect_fixtures(self) -> None:
        """테스트 클래스에서 픽스처 수집"""
        for name in dir(self.test_instance):
            if name.startswith("_"):
                continue

            attr = getattr(self.test_instance, name, None)
            if attr is None:
                continue

            if getattr(attr, "_bloom_fixture", False):
                fixture_name = getattr(attr, "_bloom_fixture_name", name)
                self._fixtures[fixture_name] = attr

    async def setup_autouse_fixtures(self) -> None:
        """autouse 픽스처 실행"""
        for name, fixture_fn in self._fixtures.items():
            if getattr(fixture_fn, "_bloom_fixture_autouse", False):
                await self.get_fixture(name)

    async def get_fixture(self, name: str) -> Any:
        """픽스처 값 획득"""
        if name in self._fixture_values:
            return self._fixture_values[name]

        if name not in self._fixtures:
            raise ValueError(f"Unknown fixture: {name}")

        fixture_fn = self._fixtures[name]
        result = fixture_fn()

        # async generator (yield 사용)
        if hasattr(result, "__anext__"):
            value = await result.__anext__()
            self._fixture_values[name] = value
            self._teardown_stack.append(result)
            return value

        # coroutine
        if hasattr(result, "__await__"):
            value = await result
            self._fixture_values[name] = value
            return value

        self._fixture_values[name] = result
        return result

    async def teardown(self) -> None:
        """픽스처 정리"""
        # 역순으로 teardown 실행
        for gen in reversed(self._teardown_stack):
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass

        self._fixture_values.clear()
        self._teardown_stack.clear()
