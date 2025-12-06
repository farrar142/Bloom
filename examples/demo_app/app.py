"""Demo Application - 앱 초기화

Application 인스턴스를 생성합니다.
auto_scan()으로 하위 디렉토리를 자동 스캔하므로 import가 필요 없습니다.
"""

from __future__ import annotations

import logging

from bloom import Application
from bloom.web import Controller, GetMapping, Request, JSONResponse

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s: %(levelname)s/%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


# =============================================================================
# Health Controller (공통)
# =============================================================================


@Controller
class HealthController:
    """헬스체크 API"""

    @GetMapping("/health")
    async def health(self, request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "demo-app"})


@Controller
class TaskResultController:
    """태스크 결과 조회 API"""

    @GetMapping("/api/tasks/{task_id}")
    async def get_task_result(self, request: Request, task_id: str) -> JSONResponse:
        """태스크 결과 조회"""
        if not application.queue.backend:
            return JSONResponse({"error": "Backend not configured"}, status_code=500)

        result = await application.queue.backend.get_result(task_id)
        if not result:
            return JSONResponse({"error": "Task not found"}, status_code=404)

        return JSONResponse(
            {
                "task_id": result.task_id,
                "status": result.status.value,
                "result": result.result,
                "error": result.error,
            }
        )


# =============================================================================
# Application 인스턴스
# =============================================================================

# auto_scan()으로 현재 패키지의 모든 하위 디렉토리 자동 스캔
# import 없이도 settings/, users/, products/, orders/, notifications/ 모두 스캔됨
# 주의: __main__으로 실행될 때 중복 로드 방지

# examples.demo_app으로 이미 로드된 경우 기존 application 사용
import sys

_existing_module = sys.modules.get("examples.demo_app.app")
if _existing_module and hasattr(_existing_module, "application"):
    # 이미 로드된 application 재사용
    application = _existing_module.application
else:
    # 새로 생성 - auto_scan() 인자 없이 호출하면 현재 작업 디렉토리 기준 스캔
    application = Application("demo-app").auto_scan()

# ASGI 앱 (uvicorn용)
asgi_app = application.asgi
