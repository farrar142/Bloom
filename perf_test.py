import asyncio
from typing import Annotated, Literal
import aiohttp
import time
import argparse
import json
from datetime import datetime
from pathlib import Path
from statistics import mean, stdev


async def benchmark(url, num_requests, concurrency) -> dict:
    connector = aiohttp.TCPConnector(limit=concurrency, force_close=True)
    timeout = aiohttp.ClientTimeout(total=120)
    latencies = []
    errors = 0

    async def fetch(session):
        nonlocal errors
        start = time.perf_counter()
        try:
            async with session.get(url) as resp:
                await resp.read()
                latencies.append((time.perf_counter() - start) * 1000)
        except Exception as e:
            errors += 1

    start_time = time.perf_counter()

    session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    try:
        semaphore = asyncio.Semaphore(concurrency)

        async def bounded_fetch():
            async with semaphore:
                await fetch(session)

        await asyncio.gather(*[bounded_fetch() for _ in range(num_requests)])
    finally:
        await session.close()
        await asyncio.sleep(0.25)  # 커넥션 정리 대기

    total_time = time.perf_counter() - start_time

    print(f"=== 성능 테스트 결과 ===")
    print(f"총 요청: {num_requests} | 동시성: {concurrency} | 에러: {errors}")
    print(f"총 시간: {total_time:.2f}초 | RPS: {num_requests / total_time:.2f}")
    if latencies:
        latencies.sort()
        print(
            f"응답시간 - 평균: {mean(latencies):.2f}ms | 최소: {min(latencies):.2f}ms | 최대: {max(latencies):.2f}ms"
        )
        print(
            f"P50: {latencies[int(len(latencies) * 0.5)]:.2f}ms | P95: {latencies[int(len(latencies) * 0.95)]:.2f}ms | P99: {latencies[int(len(latencies) * 0.99)]:.2f}ms"
        )
    print()

    # 결과 반환
    result = {
        "num_requests": num_requests,
        "concurrency": concurrency,
        "errors": errors,
        "total_time": round(total_time, 2),
        "rps": round(num_requests / total_time, 2),
    }
    if latencies:
        result.update(
            {
                "avg_ms": round(mean(latencies), 2),
                "min_ms": round(min(latencies), 2),
                "max_ms": round(max(latencies), 2),
                "p50_ms": round(latencies[int(len(latencies) * 0.5)], 2),
                "p95_ms": round(latencies[int(len(latencies) * 0.95)], 2),
                "p99_ms": round(latencies[int(len(latencies) * 0.99)], 2),
            }
        )
    return result


async def main(name: str):
    results = {"name": name, "timestamp": datetime.now().isoformat(), "tests": {}}

    print(f"=== 성능 테스트: {name} ===")
    print()
    print("=== 워밍업 ===")
    results["tests"]["warmup"] = await benchmark(
        "http://127.0.0.1:8000/health", 1000, 50
    )

    print("=== 본 테스트 ===")
    results["tests"]["main"] = await benchmark(
        "http://127.0.0.1:8000/health", 10000, 100
    )

    print("=== 고부하 테스트 ===")
    results["tests"]["high_load"] = await benchmark(
        "http://127.0.0.1:8000/health", 20000, 200
    )

    # 파일로 저장
    output_dir = Path("perf_results")
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{name}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"결과가 {output_file}에 저장되었습니다.")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HTTP 성능 테스트")
    parser.add_argument("name", help="테스트 이름 (결과 파일명으로 사용)")
    args = parser.parse_args()

    asyncio.run(main(args.name))
