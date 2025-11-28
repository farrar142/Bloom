"""파라미터 리졸버 프로파일링 테스트"""

import time
import cProfile
import pstats
from io import StringIO
from dataclasses import dataclass

import pytest
from pydantic import BaseModel

from bloom import Application, Component, Controller
from bloom.web import Get, Post, RequestMapping
from bloom.web.http import HttpRequest
from bloom.web.params import RequestBody, HttpHeader, resolve_parameters
from bloom.web.params.registry import get_default_registry
from bloom.web.params.types import KeyValue


@dataclass
class UserCreate:
    name: str
    email: str


class UserModel(BaseModel):
    name: str
    email: str


class TestParameterResolverProfiling:
    """파라미터 리졸버 성능 프로파일링"""

    @pytest.fixture
    def sample_request(self):
        """샘플 HTTP 요청"""
        return HttpRequest(
            method="POST",
            path="/users",
            headers={
                "content-type": "application/json",
                "authorization": "Bearer token123",
            },
            body=b'{"name": "John", "email": "john@example.com"}',
            query_params={"page": "1", "limit": "10"},
        )

    @pytest.fixture
    def path_params(self):
        return {"user_id": "123"}

    @pytest.mark.asyncio
    async def test_profile_simple_params(self, sample_request, path_params):
        """단순 파라미터 리졸빙 프로파일링"""
        # 단순 타입 힌트
        type_hints = {
            "user_id": str,
            "page": str,
            "limit": str,
        }

        # 웜업
        for _ in range(100):
            await resolve_parameters(type_hints, sample_request, path_params)

        # 벤치마크
        iterations = 10000
        start = time.perf_counter()
        for _ in range(iterations):
            await resolve_parameters(type_hints, sample_request, path_params)
        elapsed = time.perf_counter() - start

        per_call = (elapsed / iterations) * 1_000_000  # μs
        print(f"\n단순 파라미터 ({len(type_hints)}개): {per_call:.2f} μs/call")
        print(f"처리량: {iterations / elapsed:.0f} calls/sec")

    @pytest.mark.asyncio
    async def test_profile_complex_params(self, sample_request, path_params):
        """복잡한 파라미터 리졸빙 프로파일링"""
        # 복잡한 타입 힌트
        type_hints = {
            "user_id": str,
            "body": RequestBody[UserCreate],
            "auth": HttpHeader["authorization"],
            "page": int,
            "limit": int,
        }

        # 웜업
        for _ in range(100):
            await resolve_parameters(type_hints, sample_request, path_params)

        # 벤치마크
        iterations = 5000
        start = time.perf_counter()
        for _ in range(iterations):
            await resolve_parameters(type_hints, sample_request, path_params)
        elapsed = time.perf_counter() - start

        per_call = (elapsed / iterations) * 1_000_000  # μs
        print(f"\n복잡한 파라미터 ({len(type_hints)}개): {per_call:.2f} μs/call")
        print(f"처리량: {iterations / elapsed:.0f} calls/sec")

    @pytest.mark.asyncio
    async def test_profile_with_cprofile(self, sample_request, path_params):
        """cProfile로 상세 프로파일링"""
        type_hints = {
            "user_id": str,
            "body": RequestBody[UserCreate],
            "auth": HttpHeader["authorization"],
            "page": int,
        }

        # cProfile로 1000회 호출 프로파일링
        profiler = cProfile.Profile()
        profiler.enable()

        for _ in range(1000):
            await resolve_parameters(type_hints, sample_request, path_params)

        profiler.disable()

        # 결과 출력
        stream = StringIO()
        stats = pstats.Stats(profiler, stream=stream)
        stats.strip_dirs()
        stats.sort_stats("cumulative")
        stats.print_stats(20)  # 상위 20개

        print("\n=== cProfile 결과 (상위 20개 함수) ===")
        print(stream.getvalue())

    @pytest.mark.asyncio
    async def test_profile_resolver_find(self, sample_request, path_params):
        """리졸버 탐색 시간 측정"""
        registry = get_default_registry()

        test_cases = [
            ("path_param", str),
            ("query_param", int),
            ("body", RequestBody[UserCreate]),
            ("header", HttpHeader["x-custom"]),
            ("request", HttpRequest),
        ]

        print("\n=== 리졸버 탐색 시간 ===")
        for param_name, param_type in test_cases:
            iterations = 10000

            start = time.perf_counter()
            for _ in range(iterations):
                registry.find_resolver(param_name, param_type)
            elapsed = time.perf_counter() - start

            per_call = (elapsed / iterations) * 1_000_000  # μs
            print(f"{param_name} ({param_type}): {per_call:.3f} μs")

    @pytest.mark.asyncio
    async def test_profile_type_hint_extraction(self):
        """타입 힌트 추출 시간 측정"""
        from typing import get_type_hints
        import inspect

        @Controller
        class TestController:
            @Get("/users/{user_id}")
            def get_user(
                self,
                user_id: str,
                body: RequestBody[UserCreate],
                auth: HttpHeader["authorization"],
                page: int = 1,
                limit: int = 10,
            ):
                pass

        app = Application("test").ready()

        handler_method = TestController.get_user

        # 웜업
        for _ in range(100):
            get_type_hints(handler_method)
            inspect.signature(handler_method)

        # 벤치마크
        iterations = 10000

        # get_type_hints 측정
        start = time.perf_counter()
        for _ in range(iterations):
            get_type_hints(handler_method)
        type_hints_time = time.perf_counter() - start

        # inspect.signature 측정
        start = time.perf_counter()
        for _ in range(iterations):
            inspect.signature(handler_method)
        sig_time = time.perf_counter() - start

        print("\n=== 타입 힌트 추출 시간 ===")
        print(f"get_type_hints: {(type_hints_time / iterations) * 1_000_000:.3f} μs")
        print(f"inspect.signature: {(sig_time / iterations) * 1_000_000:.3f} μs")
        print(f"합계: {((type_hints_time + sig_time) / iterations) * 1_000_000:.3f} μs")


class TestEndToEndProfiling:
    """엔드투엔드 프로파일링"""

    @pytest.mark.asyncio
    async def test_full_dispatch_profiling(self, reset_container_manager):
        """전체 디스패치 과정 프로파일링"""

        @Controller
        @RequestMapping("/api")
        class ApiController:
            @Get("/users/{user_id}")
            def get_user(self, user_id: str, page: int = 1) -> dict:
                return {"user_id": user_id, "page": page}

            @Post("/users")
            def create_user(self, body: RequestBody[UserCreate]) -> dict:
                return {"name": body.name}

        app = Application("profile_test").ready()

        # GET 요청
        get_request = HttpRequest(
            method="GET",
            path="/api/users/123",
            query_params={"page": "5"},
        )

        # POST 요청
        post_request = HttpRequest(
            method="POST",
            path="/api/users",
            headers={"content-type": "application/json"},
            body=b'{"name": "John", "email": "john@example.com"}',
        )

        # 웜업
        for _ in range(100):
            await app.router.dispatch(get_request)
            await app.router.dispatch(post_request)

        print("\n=== 전체 디스패치 프로파일링 ===")

        # GET 벤치마크
        iterations = 5000
        start = time.perf_counter()
        for _ in range(iterations):
            await app.router.dispatch(get_request)
        get_time = time.perf_counter() - start

        print(f"GET /api/users/123: {(get_time / iterations) * 1_000_000:.2f} μs")
        print(f"처리량: {iterations / get_time:.0f} req/sec")

        # POST 벤치마크
        start = time.perf_counter()
        for _ in range(iterations):
            await app.router.dispatch(post_request)
        post_time = time.perf_counter() - start

        print(f"POST /api/users: {(post_time / iterations) * 1_000_000:.2f} μs")
        print(f"처리량: {iterations / post_time:.0f} req/sec")

        # cProfile로 상세 분석
        profiler = cProfile.Profile()
        profiler.enable()

        for _ in range(1000):
            await app.router.dispatch(get_request)

        profiler.disable()

        stream = StringIO()
        stats = pstats.Stats(profiler, stream=stream)
        stats.strip_dirs()
        stats.sort_stats("cumulative")
        stats.print_stats(30)

        print("\n=== cProfile 상세 결과 ===")
        print(stream.getvalue())
