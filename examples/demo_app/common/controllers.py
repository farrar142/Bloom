"""Demo App - 공통 컨트롤러

헬스 체크, 태스크 결과 조회 등 공통 API를 제공합니다.
"""

from __future__ import annotations

from bloom.web import Controller, GetMapping, Request, JSONResponse


@Controller
class HealthController:
    """헬스체크 API"""

    @GetMapping("/health")
    async def health(self, request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "demo-app"})
