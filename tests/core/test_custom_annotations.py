"""
사용자 정의 어노테이션 예제 및 테스트
"""

import pytest
import time
from functools import wraps
from typing import Any

from bloom.core.aop import (
    MethodInterceptor,
    MethodInvocation,
    InterceptorInfo,
    MethodDescriptor,
    ensure_method_descriptor,
    get_method_descriptor,
    get_interceptor_registry,
    reset_interceptor_registry,
    create_component_proxy,
    Around,
)


@pytest.fixture(autouse=True)
def reset_registry():
    """각 테스트 전후에 레지스트리 초기화"""
    reset_interceptor_registry()
    yield
    reset_interceptor_registry()


# ============================================================
# 예제 1: 간단한 메타데이터 어노테이션 (라우팅용)
# ============================================================


def GetMapping(path: str):
    """HTTP GET 라우팅 어노테이션"""

    def decorator(func):
        descriptor = ensure_method_descriptor(func)
        descriptor.set_metadata("http_method", "GET")
        descriptor.set_metadata("path", path)
        return func

    return decorator


def PostMapping(path: str):
    """HTTP POST 라우팅 어노테이션"""

    def decorator(func):
        descriptor = ensure_method_descriptor(func)
        descriptor.set_metadata("http_method", "POST")
        descriptor.set_metadata("path", path)
        return func

    return decorator


class TestMetadataAnnotation:
    """메타데이터 어노테이션 테스트"""

    def test_get_mapping_stores_metadata(self):
        """@GetMapping은 HTTP 메서드와 경로를 저장"""

        class Controller:
            @GetMapping("/users/{id}")
            async def get_user(self, id: int):
                return {"id": id}

        descriptor = get_method_descriptor(Controller.get_user)
        assert descriptor is not None
        assert descriptor.get_metadata("http_method") == "GET"
        assert descriptor.get_metadata("path") == "/users/{id}"

    def test_post_mapping_stores_metadata(self):
        """@PostMapping은 HTTP 메서드와 경로를 저장"""

        class Controller:
            @PostMapping("/users")
            async def create_user(self, data: dict):
                return data

        descriptor = get_method_descriptor(Controller.create_user)
        assert descriptor is not None
        assert descriptor.get_metadata("http_method") == "POST"
        assert descriptor.get_metadata("path") == "/users"


# ============================================================
# 예제 2: 인터셉터 연동 어노테이션 (Rate Limiting)
# ============================================================


class RateLimitInterceptor(MethodInterceptor):
    """호출 횟수 제한 인터셉터"""

    # 클래스 레벨에서 호출 기록 공유
    _calls: dict[str, list[float]] = {}

    def __init__(self, limit: int, window: int, order: int = 0):
        self.limit = limit
        self.window = window
        self.order = order

    async def intercept(self, invocation: MethodInvocation, proceed):
        key = invocation.signature
        now = time.time()

        # 오래된 호출 기록 제거
        if key not in self._calls:
            self._calls[key] = []
        self._calls[key] = [t for t in self._calls[key] if now - t < self.window]

        # 제한 확인
        if len(self._calls[key]) >= self.limit:
            raise RuntimeError(
                f"Rate limit exceeded: {self.limit} calls per {self.window}s"
            )

        self._calls[key].append(now)
        return await proceed()

    @classmethod
    def reset(cls):
        """테스트용 리셋"""
        cls._calls.clear()


def RateLimited(limit: int, *, window: int = 60, order: int = -80):
    """호출 횟수 제한 어노테이션"""

    def decorator(func):
        descriptor = ensure_method_descriptor(func)
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type="rate_limited",
                order=order,
                metadata={"limit": limit, "window": window},
            )
        )
        return func

    return decorator


class TestRateLimitAnnotation:
    """Rate Limit 어노테이션 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """각 테스트 전 인터셉터 초기화"""
        RateLimitInterceptor.reset()

        # 팩토리 등록
        registry = get_interceptor_registry()

        @registry.register_factory("rate_limited")
        def rate_limited_factory(info: InterceptorInfo) -> MethodInterceptor:
            return RateLimitInterceptor(
                limit=info.metadata["limit"],
                window=info.metadata["window"],
                order=info.order,
            )

        yield
        RateLimitInterceptor.reset()

    @pytest.mark.asyncio
    async def test_rate_limit_allows_within_limit(self):
        """제한 내에서는 호출 허용"""

        class ApiService:
            @RateLimited(limit=3, window=60)
            async def api_call(self) -> str:
                return "success"

        service = ApiService()
        proxied = create_component_proxy(service)

        # 3번까지는 성공
        assert await proxied.api_call() == "success"
        assert await proxied.api_call() == "success"
        assert await proxied.api_call() == "success"

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_over_limit(self):
        """제한 초과 시 예외 발생"""

        class ApiService:
            @RateLimited(limit=2, window=60)
            async def limited_call(self) -> str:
                return "success"

        service = ApiService()
        proxied = create_component_proxy(service)

        # 2번까지는 성공
        await proxied.limited_call()
        await proxied.limited_call()

        # 3번째는 실패
        with pytest.raises(RuntimeError, match="Rate limit exceeded"):
            await proxied.limited_call()


# ============================================================
# 예제 3: 파이썬 데코레이터와 AOP 동시 지원
# ============================================================


class AuthInterceptor(MethodInterceptor):
    """권한 검사 인터셉터"""

    def __init__(self, roles: list[str], order: int = 0):
        self.roles = roles
        self.order = order

    async def intercept(self, invocation: MethodInvocation, proceed):
        # invocation.attributes에서 current_user 확인
        current_user = invocation.attributes.get("current_user")

        if not current_user:
            raise PermissionError("Not authenticated")

        user_roles = getattr(current_user, "roles", [])
        if not any(role in user_roles for role in self.roles):
            raise PermissionError(f"Required roles: {self.roles}")

        return await proceed()


def Authorized(roles: list[str], *, order: int = -200):
    """
    권한 검사 어노테이션

    - AOP 프록시에서 인터셉터로 동작
    - 프록시 없이 직접 호출 시 파이썬 데코레이터로 동작
    """

    def decorator(func):
        # 1. AOP 메타데이터 등록
        descriptor = ensure_method_descriptor(func)
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type="authorized",
                order=order,
                metadata={"roles": roles},
            )
        )

        # 2. 파이썬 표준 데코레이터 (프록시 없이 직접 호출 시)
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            current_user = kwargs.pop("current_user", None) or getattr(
                self, "current_user", None
            )

            if not current_user:
                raise PermissionError("Not authenticated")

            user_roles = getattr(current_user, "roles", [])
            if not any(role in user_roles for role in roles):
                raise PermissionError(f"Required roles: {roles}")

            return await func(self, *args, **kwargs)

        # 원본 함수 참조 보존
        wrapper.__wrapped__ = func
        return wrapper

    return decorator


class TestDualModeAnnotation:
    """이중 모드 어노테이션 테스트 (파이썬 데코레이터 + AOP)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """팩토리 등록"""
        registry = get_interceptor_registry()

        @registry.register_factory("authorized")
        def auth_factory(info: InterceptorInfo) -> MethodInterceptor:
            return AuthInterceptor(
                roles=info.metadata["roles"],
                order=info.order,
            )

    @pytest.mark.asyncio
    async def test_decorator_mode_without_proxy(self):
        """프록시 없이 파이썬 데코레이터로 동작"""

        class User:
            def __init__(self, roles: list[str]):
                self.roles = roles

        class AdminService:
            @Authorized(["admin"])
            async def admin_action(self) -> str:
                return "admin done"

        service = AdminService()

        # 권한 없이 호출 - 실패
        with pytest.raises(PermissionError, match="Not authenticated"):
            await service.admin_action()

        # admin 권한으로 호출 - 성공
        result = await service.admin_action(current_user=User(["admin"]))
        assert result == "admin done"

        # 다른 권한으로 호출 - 실패
        with pytest.raises(PermissionError, match="Required roles"):
            await service.admin_action(current_user=User(["user"]))


# ============================================================
# 예제 4: 여러 어노테이션 조합
# ============================================================


def Logged(*, level: str = "INFO", order: int = 100):
    """로깅 어노테이션"""

    def decorator(func):
        descriptor = ensure_method_descriptor(func)
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type="logged",
                order=order,
                metadata={"level": level},
            )
        )
        return func

    return decorator


class LoggedInterceptor(MethodInterceptor):
    """로깅 인터셉터"""

    logs: list[str] = []  # 테스트용 로그 저장

    def __init__(self, level: str, order: int = 0):
        self.level = level
        self.order = order

    async def intercept(self, invocation: MethodInvocation, proceed):
        self.logs.append(f"[{self.level}] Calling {invocation.signature}")
        try:
            result = await proceed()
            self.logs.append(
                f"[{self.level}] {invocation.signature} returned: {result}"
            )
            return result
        except Exception as e:
            self.logs.append(f"[{self.level}] {invocation.signature} raised: {e}")
            raise

    @classmethod
    def reset(cls):
        cls.logs.clear()


class TestCombinedAnnotations:
    """여러 어노테이션 조합 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """팩토리 등록"""
        RateLimitInterceptor.reset()
        LoggedInterceptor.reset()

        registry = get_interceptor_registry()

        @registry.register_factory("rate_limited")
        def rate_limited_factory(info: InterceptorInfo) -> MethodInterceptor:
            return RateLimitInterceptor(
                limit=info.metadata["limit"],
                window=info.metadata["window"],
                order=info.order,
            )

        @registry.register_factory("logged")
        def logged_factory(info: InterceptorInfo) -> MethodInterceptor:
            return LoggedInterceptor(
                level=info.metadata["level"],
                order=info.order,
            )

        yield
        RateLimitInterceptor.reset()
        LoggedInterceptor.reset()

    @pytest.mark.asyncio
    async def test_multiple_annotations_in_order(self):
        """여러 어노테이션이 order 순으로 실행"""
        execution_order = []

        async def trace_advice(jp):
            execution_order.append("trace:before")
            result = await jp.proceed()
            execution_order.append("trace:after")
            return result

        class ComplexService:
            @RateLimited(limit=10, window=60, order=-80)  # 먼저
            @Logged(level="DEBUG", order=100)  # 나중
            @Around(trace_advice, order=0)  # 중간
            async def complex_method(self) -> str:
                execution_order.append("method")
                return "done"

        service = ComplexService()
        proxied = create_component_proxy(service)

        result = await proxied.complex_method()

        assert result == "done"
        # RateLimit(-80) -> Around(0) -> Logged(100) -> method
        assert execution_order == ["trace:before", "method", "trace:after"]
        assert "[DEBUG] Calling ComplexService.complex_method" in LoggedInterceptor.logs


# ============================================================
# 예제 5: 라우터 스캐닝 (Spring MVC 스타일)
# ============================================================


class Route:
    """라우트 정보"""

    def __init__(self, method: str, path: str, handler):
        self.method = method
        self.path = path
        self.handler = handler


def scan_routes(controller_class) -> list[Route]:
    """컨트롤러 클래스에서 라우트 정보 추출"""
    routes = []

    for name in dir(controller_class):
        if name.startswith("_"):
            continue

        method = getattr(controller_class, name, None)
        if not callable(method):
            continue

        descriptor = get_method_descriptor(method)
        if descriptor is None:
            continue

        http_method = descriptor.get_metadata("http_method")
        path = descriptor.get_metadata("path")

        if http_method and path:
            routes.append(Route(http_method, path, method))

    return routes


class TestRouterScanning:
    """라우터 스캐닝 테스트"""

    def test_scan_controller_routes(self):
        """컨트롤러에서 라우트 정보 추출"""

        class UserController:
            @GetMapping("/users")
            async def list_users(self):
                return []

            @GetMapping("/users/{id}")
            async def get_user(self, id: int):
                return {"id": id}

            @PostMapping("/users")
            async def create_user(self, data: dict):
                return data

            async def helper_method(self):
                """이 메서드는 라우트가 아님"""
                pass

        routes = scan_routes(UserController)

        assert len(routes) == 3

        methods = {(r.method, r.path) for r in routes}
        assert ("GET", "/users") in methods
        assert ("GET", "/users/{id}") in methods
        assert ("POST", "/users") in methods
