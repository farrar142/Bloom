"""Bloom Framework 예제 앱 - uvicorn 멀티워커 테스트용"""

from typing import Annotated, Literal
from bloom import Application, Component, Controller, Get, Post, RequestMapping
from bloom.core.decorators import Factory
from bloom.web.http import HttpResponse
from bloom.web.openapi.config import OpenAPIConfig


# 서비스 레이어
@Component
class UserService:
    def get_user(self, user_id: str) -> dict:
        return {
            "id": user_id,
            "name": f"User {user_id}",
            "email": f"user{user_id}@example.com",
        }

    def get_all_users(self) -> list[dict]:
        return [self.get_user(str(i)) for i in range(1, 6)]

    def create_user(self, name: str, email: str) -> dict:
        import uuid

        return {"id": str(uuid.uuid4())[:8], "name": name, "email": email}


# 컨트롤러
@Controller
@RequestMapping("/api")
class UserController:
    user_service: UserService  # 자동 주입

    @Get("/users")
    async def get_users(self) -> list[dict]:
        """모든 사용자 조회"""
        return self.user_service.get_all_users()

    @Get("/users/{user_id}")
    async def get_user(self, user_id: str) -> dict:
        """특정 사용자 조회"""
        return self.user_service.get_user(user_id)


@Controller
class HealthController:
    @Get("/health")
    async def health(self) -> dict:
        """헬스체크 - 워커 PID 확인용"""
        import os
        import sys

        gil_status = (
            "disabled"
            if hasattr(sys, "_is_gil_enabled") and not sys._is_gil_enabled()
            else "enabled"
        )

        return {
            "status": "ok",
            "pid": os.getpid(),
            "python": sys.version.split()[0],
            "gil": gil_status,
        }

    @Get("/")
    async def root(self) -> dict:
        return {"message": "Welcome to Bloom Framework!", "docs": "/health"}


@Component
class OpenApiConfiguration:
    @Factory
    def openapi_config(self) -> OpenAPIConfig:
        return OpenAPIConfig(title="My API")


class AvailableInitialize:
    val = 1
    pass


# 애플리케이션 생성
import sys

_current_module = sys.modules[__name__]

app = Application("example").scan(_current_module).ready()
