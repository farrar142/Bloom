"""멀티프로세스 성능 프로파일링"""

import asyncio
import multiprocessing
import time
import os
import sys
import threading
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Any

# 프로젝트 루트를 path에 추가
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def setup_path():
    """워커 프로세스에서 모듈 경로 설정"""
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)


# 워커 프로세스에서 실행될 코드
def worker_init():
    """각 워커 프로세스 초기화"""
    setup_path()

    from bloom import Application, Controller, Get, RequestMapping, Component
    from bloom.core.manager import set_current_manager

    # 새 매니저로 시작 (프로세스 격리)
    set_current_manager(None)

    @Component
    class UserService:
        def get_user(self, id: str) -> dict:
            return {"id": id, "name": f"User {id}"}

    @Controller
    @RequestMapping("/api")
    class UserController:
        user_service: UserService

        @Get("/users/{id}")
        async def get_user(self, id: str):
            return self.user_service.get_user(id)

        @Get("/health")
        async def health(self):
            return {"status": "ok", "pid": os.getpid()}

    # 현재 모듈 스캔
    import tests.test_multiprocess_profile as module

    app = Application(f"worker_{os.getpid()}").scan(module).ready()

    return app


def run_requests_in_worker(args: tuple[int, int]) -> dict[str, Any]:
    """
    워커 프로세스에서 요청 처리 성능 측정

    Args:
        args: (worker_id, request_count)

    Returns:
        성능 측정 결과
    """
    worker_id, request_count = args

    setup_path()
    from bloom.web.http import HttpRequest

    # 워커 초기화
    app = worker_init()
    router = app.router

    async def run_test():
        request = HttpRequest(
            method="GET", path="/api/users/123", query_params={}, headers={}, body=b""
        )

        # 워밍업
        for _ in range(100):
            await router.dispatch(request)

        # 측정
        start = time.perf_counter()
        for _ in range(request_count):
            await router.dispatch(request)
        end = time.perf_counter()

        return {
            "worker_id": worker_id,
            "pid": os.getpid(),
            "request_count": request_count,
            "elapsed_sec": end - start,
            "requests_per_sec": request_count / (end - start),
            "avg_latency_us": (end - start) / request_count * 1_000_000,
        }

    return asyncio.run(run_test())


def run_multiprocess_benchmark(num_workers: int, requests_per_worker: int) -> dict:
    """
    멀티프로세스 벤치마크 실행

    Args:
        num_workers: 워커 프로세스 수
        requests_per_worker: 워커당 요청 수

    Returns:
        전체 벤치마크 결과
    """
    print(f"\n{'='*60}")
    print(
        f"멀티프로세스 벤치마크: {num_workers} workers x {requests_per_worker} requests"
    )
    print(f"{'='*60}")

    args_list = [(i, requests_per_worker) for i in range(num_workers)]

    start_time = time.perf_counter()

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        results = list(executor.map(run_requests_in_worker, args_list))

    total_time = time.perf_counter() - start_time

    # 결과 집계
    total_requests = sum(r["request_count"] for r in results)
    total_throughput = total_requests / total_time
    avg_latency = sum(r["avg_latency_us"] for r in results) / len(results)

    print(f"\n워커별 결과:")
    print("-" * 60)
    for r in results:
        print(
            f"  Worker {r['worker_id']} (PID {r['pid']}): "
            f"{r['requests_per_sec']:.0f} req/s, "
            f"{r['avg_latency_us']:.2f} μs/req"
        )

    print(f"\n전체 결과:")
    print("-" * 60)
    print(f"  총 요청 수: {total_requests:,}")
    print(f"  총 소요 시간: {total_time:.2f}s")
    print(f"  총 처리량: {total_throughput:,.0f} req/s")
    print(f"  평균 지연: {avg_latency:.2f} μs/req")

    return {
        "num_workers": num_workers,
        "requests_per_worker": requests_per_worker,
        "total_requests": total_requests,
        "total_time_sec": total_time,
        "total_throughput": total_throughput,
        "avg_latency_us": avg_latency,
        "worker_results": results,
    }


def run_scaling_test():
    """워커 수에 따른 스케일링 테스트"""
    print("\n" + "=" * 70)
    print("스케일링 테스트: 워커 수 증가에 따른 처리량 변화")
    print("=" * 70)

    requests_per_worker = 5000
    results = []

    # 1, 2, 4, 8 워커 테스트 (CPU 코어 수에 따라 조정)
    max_workers = min(8, multiprocessing.cpu_count())
    worker_counts = [1, 2, 4, max_workers] if max_workers >= 4 else [1, 2, max_workers]

    for num_workers in worker_counts:
        result = run_multiprocess_benchmark(num_workers, requests_per_worker)
        results.append(result)

    # 스케일링 효율성 분석
    print("\n" + "=" * 70)
    print("스케일링 효율성 분석")
    print("=" * 70)
    print(
        f"{'워커 수':>8} | {'처리량 (req/s)':>15} | {'스케일링 효율':>15} | {'지연 (μs)':>12}"
    )
    print("-" * 60)

    baseline_throughput = results[0]["total_throughput"]
    for r in results:
        scaling_efficiency = (
            r["total_throughput"] / baseline_throughput / r["num_workers"]
        ) * 100
        print(
            f"{r['num_workers']:>8} | {r['total_throughput']:>15,.0f} | {scaling_efficiency:>14.1f}% | {r['avg_latency_us']:>11.2f}"
        )

    return results


def compare_single_vs_multi():
    """싱글 프로세스 vs 멀티 프로세스 비교"""
    print("\n" + "=" * 70)
    print("싱글 vs 멀티 프로세스 비교")
    print("=" * 70)

    request_count = 10000
    num_workers = min(4, multiprocessing.cpu_count())

    # 싱글 프로세스
    print(f"\n1. 싱글 프로세스 ({request_count:,} requests)...")
    single_result = run_requests_in_worker((0, request_count))

    # 멀티 프로세스 (같은 총 요청 수)
    requests_per_worker = request_count // num_workers
    print(
        f"\n2. 멀티 프로세스 ({num_workers} workers x {requests_per_worker:,} requests)..."
    )
    multi_result = run_multiprocess_benchmark(num_workers, requests_per_worker)

    print("\n" + "=" * 70)
    print("비교 결과")
    print("=" * 70)
    print(f"{'':>20} | {'싱글':>15} | {'멀티 ({num_workers}w)':>15} | {'향상율':>10}")
    print("-" * 65)

    throughput_improvement = (
        multi_result["total_throughput"] / single_result["requests_per_sec"]
    )
    latency_improvement = (
        single_result["avg_latency_us"] / multi_result["avg_latency_us"]
    )

    print(
        f"{'처리량 (req/s)':>20} | {single_result['requests_per_sec']:>15,.0f} | {multi_result['total_throughput']:>15,.0f} | {throughput_improvement:>9.2f}x"
    )
    print(
        f"{'지연 (μs)':>20} | {single_result['avg_latency_us']:>15.2f} | {multi_result['avg_latency_us']:>15.2f} | {latency_improvement:>9.2f}x"
    )


def uvicorn_style_worker(worker_id: int, request_count: int, result_queue):
    """
    uvicorn 워커 시뮬레이션
    - 시작 시 한 번만 초기화
    - 이후 계속 대기하며 요청 처리
    """
    setup_path()

    from bloom import Application, Controller, Get, RequestMapping, Component
    from bloom.web.http import HttpRequest
    from bloom.core.manager import set_current_manager

    set_current_manager(None)

    @Component
    class UserService:
        def get_user(self, id: str) -> dict:
            return {"id": id, "name": f"User {id}"}

    @Controller
    @RequestMapping("/api")
    class UserController:
        user_service: UserService

        @Get("/users/{id}")
        async def get_user(self, id: str):
            return self.user_service.get_user(id)

    # 한 번만 초기화 (uvicorn 시작과 동일)
    import tests.test_multiprocess_profile as module

    app = Application(f"worker_{worker_id}").scan(module).ready()
    router = app.router

    async def handle_requests():
        request = HttpRequest(
            method="GET", path="/api/users/123", query_params={}, headers={}, body=b""
        )

        # 워밍업
        for _ in range(500):
            await router.dispatch(request)

        # 측정 - 워커가 대기하면서 요청을 계속 처리
        start = time.perf_counter()
        for _ in range(request_count):
            await router.dispatch(request)
        end = time.perf_counter()

        return end - start

    elapsed = asyncio.run(handle_requests())
    throughput = request_count / elapsed
    result_queue.put(
        {
            "worker_id": worker_id,
            "pid": os.getpid(),
            "requests": request_count,
            "elapsed": elapsed,
            "throughput": throughput,
        }
    )


def run_uvicorn_style_benchmark():
    """uvicorn 방식: 워커가 한 번 초기화 후 계속 대기하며 요청 처리"""
    print("\n" + "=" * 70)
    print("uvicorn 스타일 벤치마크 (워커 프로세스 재사용)")
    print("=" * 70)

    num_workers = 4
    requests_per_worker = 10000

    print(f"워커 수: {num_workers}, 워커당 요청: {requests_per_worker:,}")

    result_queue = multiprocessing.Queue()
    processes = []

    # 모든 워커 동시 시작
    start_time = time.perf_counter()
    for i in range(num_workers):
        p = multiprocessing.Process(
            target=uvicorn_style_worker, args=(i, requests_per_worker, result_queue)
        )
        processes.append(p)
        p.start()

    # 모든 워커 완료 대기
    for p in processes:
        p.join()

    total_time = time.perf_counter() - start_time

    # 결과 수집
    results = []
    while not result_queue.empty():
        results.append(result_queue.get())

    if not results:
        print("워커 실행 실패")
        return

    print("\n워커별 결과:")
    print("-" * 50)
    for r in sorted(results, key=lambda x: x["worker_id"]):
        print(
            f"  Worker {r['worker_id']} (PID {r['pid']}): {r['throughput']:,.0f} req/s"
        )

    total_requests = num_workers * requests_per_worker
    total_throughput = total_requests / total_time
    avg_worker_throughput = sum(r["throughput"] for r in results) / len(results)

    print()
    print(f"총 요청 수: {total_requests:,}")
    print(f"총 소요 시간: {total_time:.2f}s")
    print(f"합산 처리량 (동시): {total_throughput:,.0f} req/s")
    print(f"워커 평균 처리량: {avg_worker_throughput:,.0f} req/s")
    print()
    print(f"싱글 대비 (17,000 기준): {total_throughput/17000:.2f}x 향상")


def run_multithread_benchmark():
    """GIL-free 멀티스레드 벤치마크"""
    print("\n" + "=" * 70)
    print("🚀 GIL-FREE 멀티스레드 벤치마크")
    print("=" * 70)

    setup_path()

    from bloom import Application, Controller, Get, RequestMapping, Component
    from bloom.web.http import HttpRequest
    from bloom.core.manager import set_current_manager

    set_current_manager(None)

    @Component
    class UserService:
        def get_user(self, id: str) -> dict:
            return {"id": id, "name": f"User {id}"}

    @Controller
    @RequestMapping("/api")
    class UserController:
        user_service: UserService

        @Get("/users/{id}")
        async def get_user(self, id: str):
            return self.user_service.get_user(id)

    import tests.test_multiprocess_profile as module

    app = Application("thread_test").scan(module).ready()
    router = app.router

    request = HttpRequest(
        method="GET", path="/api/users/123", query_params={}, headers={}, body=b""
    )

    # 워밍업
    async def warmup():
        for _ in range(1000):
            await router.dispatch(request)

    asyncio.run(warmup())

    num_threads = 4
    requests_per_thread = 10000
    results = []

    def thread_worker(thread_id: int):
        async def run():
            start = time.perf_counter()
            for _ in range(requests_per_thread):
                await router.dispatch(request)
            end = time.perf_counter()
            return {
                "thread_id": thread_id,
                "elapsed": end - start,
                "throughput": requests_per_thread / (end - start),
            }

        return asyncio.run(run())

    print(f"스레드 수: {num_threads}, 스레드당 요청: {requests_per_thread:,}")

    start_time = time.perf_counter()
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(thread_worker, i) for i in range(num_threads)]
        results = [f.result() for f in futures]
    total_time = time.perf_counter() - start_time

    print("\n스레드별 결과:")
    print("-" * 50)
    for r in results:
        print(f"  Thread {r['thread_id']}: {r['throughput']:,.0f} req/s")

    total_requests = num_threads * requests_per_thread
    total_throughput = total_requests / total_time
    avg_thread_throughput = sum(r["throughput"] for r in results) / len(results)

    print()
    print(f"총 요청 수: {total_requests:,}")
    print(f"총 소요 시간: {total_time:.2f}s")
    print(f"합산 처리량: {total_throughput:,.0f} req/s")
    print(f"스레드 평균 처리량: {avg_thread_throughput:,.0f} req/s")
    print()
    print(f"싱글 대비 (17,000 기준): {total_throughput/17000:.2f}x 향상")


if __name__ == "__main__":
    # Windows에서 필수
    multiprocessing.freeze_support()

    # GIL 상태 출력
    gil_status = (
        "DISABLED (Free-threaded)"
        if hasattr(sys, "_is_gil_enabled") and not sys._is_gil_enabled()
        else "ENABLED"
    )

    print("=" * 70)
    print("Bloom Framework 멀티프로세스 성능 프로파일링")
    print(f"Python: {sys.version.split()[0]}")
    print(f"GIL: {gil_status}")
    print(f"CPU 코어 수: {multiprocessing.cpu_count()}")
    print("=" * 70)

    # GIL-free인 경우 멀티스레드 벤치마크 추가
    if hasattr(sys, "_is_gil_enabled") and not sys._is_gil_enabled():
        run_multithread_benchmark()

    # uvicorn 방식 시뮬레이션 (워커가 대기하며 처리)
    run_uvicorn_style_benchmark()

    # 스케일링 테스트
    run_scaling_test()
