"""테스트 유틸리티 함수 및 클래스"""

from __future__ import annotations

from typing import Any, TypeVar
from contextlib import asynccontextmanager
import asyncio

from ..application import Application
from ..core.manager import ContainerManager, try_get_current_manager


T = TypeVar("T")


def create_test_app(
    name: str = "test",
    *modules: object,
    ready: bool = True,
    config: dict[str, Any] | None = None,
) -> Application:
    """
    테스트용 Application 생성 헬퍼

    Usage:
        # 기본 사용
        app = create_test_app(MyController, MyService)

        # 설정 포함
        app = create_test_app(
            MyController,
            config={"database.url": "sqlite:///:memory:"}
        )

        # ready() 호출 없이 생성
        app = create_test_app(MyController, ready=False)
        app.scan(AnotherModule).ready()

    Args:
        name: 애플리케이션 이름
        *modules: 스캔할 모듈들
        ready: True면 자동으로 ready() 호출
        config: 설정 딕셔너리 (Application.config에 주입)

    Returns:
        설정된 Application 인스턴스
    """
    app = Application(name)

    # 설정 주입
    if config:
        app.load_config(config, source_type="dict")

    # 모듈 스캔
    for module in modules:
        app.scan(module)

    # ready() 호출 (선택적)
    if ready and modules:
        app.ready()

    return app


class AsyncTestHelper:
    """
    비동기 테스트 헬퍼

    pytest-asyncio 없이도 비동기 코드를 테스트할 수 있게 합니다.

    Usage:
        helper = AsyncTestHelper()
        result = helper.run(async_function())

        # 또는 컨텍스트 매니저로
        async with helper.session():
            result = await async_function()
    """

    def __init__(self, loop: asyncio.AbstractEventLoop | None = None):
        self._loop = loop

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """이벤트 루프 반환 (없으면 생성)"""
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
        return self._loop

    def run(self, coro: Any) -> Any:
        """
        코루틴 실행

        Args:
            coro: 실행할 코루틴

        Returns:
            코루틴 결과
        """
        return self.loop.run_until_complete(coro)

    @asynccontextmanager
    async def session(self):
        """비동기 세션 컨텍스트 매니저"""
        yield

    def close(self):
        """이벤트 루프 정리"""
        if self._loop and not self._loop.is_running():
            self._loop.close()
            self._loop = None


def assert_instance_of(obj: Any, expected_type: type) -> None:
    """
    타입 검증 헬퍼

    Args:
        obj: 검증할 객체
        expected_type: 예상 타입

    Raises:
        AssertionError: 타입이 일치하지 않을 때
    """
    assert isinstance(obj, expected_type), (
        f"Expected instance of {expected_type.__name__}, " f"got {type(obj).__name__}"
    )


def assert_injected(
    obj: Any, field_name: str, expected_type: type | None = None
) -> Any:
    """
    필드 주입 검증 헬퍼

    Args:
        obj: 검증할 객체
        field_name: 필드 이름
        expected_type: 예상 타입 (None이면 타입 검증 생략)

    Returns:
        주입된 필드 값

    Raises:
        AssertionError: 필드가 없거나 타입이 일치하지 않을 때
    """
    assert hasattr(
        obj, field_name
    ), f"Field '{field_name}' not found in {type(obj).__name__}"
    value = getattr(obj, field_name)
    assert value is not None, f"Field '{field_name}' is None (not injected)"

    if expected_type:
        assert isinstance(value, expected_type), (
            f"Field '{field_name}' expected {expected_type.__name__}, "
            f"got {type(value).__name__}"
        )

    return value


def assert_has_container(target: type) -> None:
    """
    컨테이너 존재 검증 헬퍼

    Args:
        target: 검증할 클래스

    Raises:
        AssertionError: 컨테이너가 없을 때
    """
    from ..core.container import Container

    container = Container.get_container(target)
    assert container is not None, (
        f"Container not found for {target.__name__}. "
        f"Did you forget to add @Component decorator?"
    )


def get_container_info(target: type) -> dict[str, Any]:
    """
    컨테이너 정보 조회 헬퍼 (디버깅용)

    Args:
        target: 조회할 클래스

    Returns:
        컨테이너 정보 딕셔너리
    """
    from ..core.container import Container

    container = Container.get_container(target)
    if container is None:
        return {"exists": False}

    return {
        "exists": True,
        "target": container.target.__name__,
        "elements": [type(e).__name__ for e in container.elements],
        "owner_cls": container.owner_cls.__name__ if container.owner_cls else None,
        "metadata": dict(container.element.metadata) if container.element else {},
    }


def print_container_tree(manager: ContainerManager | None = None) -> str:
    """
    컨테이너 트리 출력 (디버깅용)

    Args:
        manager: ContainerManager (없으면 현재 활성 매니저)

    Returns:
        트리 문자열
    """
    if manager is None:
        manager = try_get_current_manager()
        if manager is None:
            return "No active ContainerManager"

    lines = [f"ContainerManager: {manager.app_name}"]
    lines.append("=" * 40)

    # 컨테이너 목록
    lines.append("\nContainers:")
    for target, containers in manager.container_registry.items():
        lines.append(f"  {target.__name__}: {len(containers)} container(s)")
        for container in containers:
            elements = [type(e).__name__ for e in container.elements]
            lines.append(f"    - elements: {elements}")

    # 인스턴스 목록
    lines.append("\nInstances:")
    for target, instances in manager.instance_registry.items():
        lines.append(f"  {target.__name__}: {len(instances)} instance(s)")

    return "\n".join(lines)


class SpyComponent:
    """
    호출 추적용 Spy 컴포넌트 래퍼

    Usage:
        spy = SpyComponent(real_service)
        spy.call_method("do_something", arg1, arg2)

        assert spy.call_count("do_something") == 1
        assert spy.get_calls("do_something")[0].args == (arg1, arg2)
    """

    def __init__(self, target: Any):
        self._target = target
        self._calls: dict[str, list["CallRecord"]] = {}

    def call_method(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """
        메서드 호출 및 추적

        Args:
            method_name: 호출할 메서드 이름
            *args: 위치 인자
            **kwargs: 키워드 인자

        Returns:
            메서드 반환값
        """
        if method_name not in self._calls:
            self._calls[method_name] = []

        method = getattr(self._target, method_name)
        record = CallRecord(args=args, kwargs=kwargs)

        try:
            result = method(*args, **kwargs)
            record.result = result
            return result
        except Exception as e:
            record.exception = e
            raise
        finally:
            self._calls[method_name].append(record)

    def call_count(self, method_name: str) -> int:
        """메서드 호출 횟수 반환"""
        return len(self._calls.get(method_name, []))

    def get_calls(self, method_name: str) -> list["CallRecord"]:
        """메서드 호출 기록 반환"""
        return self._calls.get(method_name, [])

    def reset(self) -> None:
        """호출 기록 초기화"""
        self._calls.clear()

    @property
    def target(self) -> Any:
        """래핑된 대상 반환"""
        return self._target


class CallRecord:
    """메서드 호출 기록"""

    def __init__(
        self,
        args: tuple = (),
        kwargs: dict[str, Any] | None = None,
        result: Any = None,
        exception: Exception | None = None,
    ):
        self.args = args
        self.kwargs = kwargs or {}
        self.result = result
        self.exception = exception

    def __repr__(self) -> str:
        return (
            f"CallRecord(args={self.args}, kwargs={self.kwargs}, result={self.result})"
        )
