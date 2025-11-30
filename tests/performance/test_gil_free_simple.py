"""GIL-free 간단 벤치마크 (외부 의존성 없음)"""

import asyncio
import time
import sys
import threading
from concurrent.futures import ThreadPoolExecutor


class SimpleRouter:
    """간단한 라우터 시뮬레이션"""

    def __init__(self):
        self.trie = {}
        routes = {
            "/api/users/{id}": lambda id: {"id": id, "name": f"User {id}"},
            "/api/posts/{id}": lambda id: {"id": id, "title": f"Post {id}"},
            "/api/health": lambda: {"status": "ok"},
        }
        for path, handler in routes.items():
            self._add_route(path, handler)

    def _add_route(self, path: str, handler):
        parts = path.strip("/").split("/")
        node = self.trie
        for part in parts:
            if part not in node:
                node[part] = {}
            node = node[part]
        node["_handler"] = handler

    def dispatch(self, path: str):
        parts = path.strip("/").split("/")
        node = self.trie
        params = {}
        for part in parts:
            if part in node:
                node = node[part]
            else:
                # 파라미터 매칭
                param_key = None
                for key in node:
                    if key.startswith("{") and key.endswith("}"):
                        param_key = key
                        break
                if param_key:
                    params[param_key[1:-1]] = part
                    node = node[param_key]
                else:
                    return None

        handler = node.get("_handler")
        if handler:
            return handler(**params) if params else handler()
        return None


def benchmark_shared_router():
    """공유 라우터 벤치마크 (경합 발생)"""
    print("\n" + "=" * 60)
    print("🔴 공유 라우터 (모든 스레드가 같은 인스턴스 사용)")
    print("=" * 60)

    router = SimpleRouter()  # 하나의 라우터를 공유

    # 워밍업
    for _ in range(1000):
        router.dispatch("/api/users/123")

    # 싱글 스레드
    request_count = 100000
    start = time.perf_counter()
    for _ in range(request_count):
        router.dispatch("/api/users/123")
    single_time = time.perf_counter() - start
    single_throughput = request_count / single_time

    print(f"\n싱글 스레드: {single_throughput:,.0f} req/s")

    # 멀티 스레드 (공유 라우터)
    num_threads = 4
    requests_per_thread = 100000

    def thread_worker_shared(thread_id: int):
        start = time.perf_counter()
        for _ in range(requests_per_thread):
            router.dispatch("/api/users/123")  # 공유 라우터 사용
        end = time.perf_counter()
        return requests_per_thread / (end - start)

    start_time = time.perf_counter()
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(thread_worker_shared, i) for i in range(num_threads)]
        results = [f.result() for f in futures]
    total_time = time.perf_counter() - start_time

    total_requests = num_threads * requests_per_thread
    total_throughput = total_requests / total_time

    print(f"멀티 스레드 ({num_threads}t): {total_throughput:,.0f} req/s")
    print(f"스케일링: {total_throughput/single_throughput:.2f}x")

    return single_throughput, total_throughput


def benchmark_per_thread_router():
    """스레드별 개별 라우터 벤치마크 (경합 없음)"""
    print("\n" + "=" * 60)
    print("🟢 개별 라우터 (각 스레드가 자체 인스턴스 사용)")
    print("=" * 60)

    router = SimpleRouter()

    # 워밍업
    for _ in range(1000):
        router.dispatch("/api/users/123")

    # 싱글 스레드
    request_count = 100000
    start = time.perf_counter()
    for _ in range(request_count):
        router.dispatch("/api/users/123")
    single_time = time.perf_counter() - start
    single_throughput = request_count / single_time

    print(f"\n싱글 스레드: {single_throughput:,.0f} req/s")

    # 멀티 스레드 (개별 라우터)
    num_threads = 4
    requests_per_thread = 100000

    def thread_worker_isolated(thread_id: int):
        # 각 스레드가 자체 라우터 인스턴스 생성
        local_router = SimpleRouter()

        start = time.perf_counter()
        for _ in range(requests_per_thread):
            local_router.dispatch("/api/users/123")  # 개별 라우터 사용
        end = time.perf_counter()
        return requests_per_thread / (end - start)

    start_time = time.perf_counter()
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [
            executor.submit(thread_worker_isolated, i) for i in range(num_threads)
        ]
        results = [f.result() for f in futures]
    total_time = time.perf_counter() - start_time

    total_requests = num_threads * requests_per_thread
    total_throughput = total_requests / total_time

    print(f"멀티 스레드 ({num_threads}t): {total_throughput:,.0f} req/s")
    print(f"스케일링: {total_throughput/single_throughput:.2f}x")

    return single_throughput, total_throughput


if __name__ == "__main__":
    # GIL 상태 출력
    gil_enabled = True
    if hasattr(sys, "_is_gil_enabled"):
        gil_enabled = sys._is_gil_enabled()

    gil_status = "DISABLED (Free-threaded)" if not gil_enabled else "ENABLED"

    print("=" * 60)
    print("GIL-Free 벤치마크: 공유 vs 개별 라우터")
    print(f"Python: {sys.version.split()[0]}")
    print(f"GIL: {gil_status}")
    print("=" * 60)

    # 공유 라우터 테스트
    shared_single, shared_multi = benchmark_shared_router()

    # 개별 라우터 테스트
    isolated_single, isolated_multi = benchmark_per_thread_router()

    # 비교 요약
    print("\n" + "=" * 60)
    print("📊 결과 비교")
    print("=" * 60)
    print(f"{'':20} | {'공유 라우터':>15} | {'개별 라우터':>15} | {'향상':>10}")
    print("-" * 65)
    print(
        f"{'멀티스레드 처리량':20} | {shared_multi:>13,.0f} | {isolated_multi:>13,.0f} | {isolated_multi/shared_multi:>9.2f}x"
    )
    print(
        f"{'스케일링 효율':20} | {shared_multi/shared_single*100:>13.1f}% | {isolated_multi/isolated_single*100:>13.1f}% |"
    )
