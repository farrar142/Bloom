"""Users Controller"""

from __future__ import annotations

import logging

from bloom.core import PostConstruct
from bloom.web import (
    Controller,
    GetMapping,
    PostMapping,
    RequestMapping,
    JSONResponse,
    PathVariable,
    RequestField,
)

from .service import UserService

logger = logging.getLogger(__name__)


@Controller
@RequestMapping("/api/users")
class UserController:
    """사용자 API"""

    user_service: UserService

    @PostConstruct
    async def initialize(self):
        logger.info("UserController initialized")

    @GetMapping("")
    async def list_users(self) -> JSONResponse:
        """사용자 목록"""
        users = await self.user_service.get_all_users()
        return JSONResponse(
            {
                "users": [
                    {
                        "id": u.id,
                        "name": u.name,
                        "email": u.email,
                        "is_active": u.is_active,
                        "created_at": (
                            u.created_at.isoformat() if u.created_at else None
                        ),
                    }
                    for u in users
                ]
            }
        )

    @GetMapping("/{user_id}")
    async def get_user(self, user_id: PathVariable[int]) -> JSONResponse:
        """사용자 상세"""
        user = await self.user_service.get_user(user_id)
        if not user:
            return JSONResponse({"error": "User not found"}, status_code=404)
        return JSONResponse(
            {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None,
            }
        )

    @PostMapping("")
    async def create_user(
        self,
        name: RequestField[str],
        email: RequestField[str],
    ) -> JSONResponse:
        """사용자 생성"""
        try:
            user = await self.user_service.create_user(
                name=name,
                email=email,
            )
            return JSONResponse(
                {
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "message": "User created successfully. Welcome email queued.",
                },
                status_code=201,
            )
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
