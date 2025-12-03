"""bloom.web.auth - Authentication & Authorization"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar


T = TypeVar("T")


@dataclass
class AuthenticationInfo(Generic[T]):
    """
    인증 정보 객체.

    Spring Security의 Authentication/Principal과 유사합니다.

    사용 예:
        # 미들웨어에서 인증 정보 설정
        request.state.authentication = AuthenticationInfo(
            id=user.id,
            principal=user,
            roles=["admin"],
        )

        # 컨트롤러에서 사용
        @GetMapping("/me")
        async def get_current_user(auth: Authentication[int]):
            return {"user_id": auth.id}
    """

    id: T
    """사용자 ID (제네릭 타입)"""

    principal: Any = None
    """전체 사용자 정보 (User 객체 등)"""

    is_authenticated: bool = True
    """인증 여부"""

    roles: list[str] = field(default_factory=list)
    """사용자 역할/권한"""

    attributes: dict[str, Any] = field(default_factory=dict)
    """추가 속성"""

    def has_role(self, role: str) -> bool:
        """특정 역할 보유 여부"""
        return role in self.roles

    def has_any_role(self, *roles: str) -> bool:
        """주어진 역할 중 하나라도 보유 여부"""
        return any(role in self.roles for role in roles)

    def has_all_roles(self, *roles: str) -> bool:
        """주어진 역할을 모두 보유 여부"""
        return all(role in self.roles for role in roles)


class AnonymousAuthentication(AuthenticationInfo[None]):
    """익명 사용자 인증 정보"""

    def __init__(self) -> None:
        super().__init__(
            id=None,
            principal=None,
            is_authenticated=False,
            roles=[],
        )


# === Decorators ===


def Authenticated(func=None, *, roles: list[str] | None = None):
    """
    인증 필수 데코레이터.

    인증되지 않은 요청은 401 Unauthorized를 반환합니다.
    roles가 지정되면 해당 역할이 필요합니다.

    사용 예:
        @Controller
        class AdminController:
            @GetMapping("/admin")
            @Authenticated(roles=["admin"])
            async def admin_page(self, auth: Authentication[int]):
                return {"admin_id": auth.id}
    """

    def decorator(fn):
        fn.__bloom_authenticated__ = True  # type: ignore
        fn.__bloom_required_roles__ = roles or []  # type: ignore
        return fn

    if func is not None:
        return decorator(func)
    return decorator


def get_authentication_metadata(func) -> dict[str, Any] | None:
    """함수의 인증 메타데이터 조회"""
    if not getattr(func, "__bloom_authenticated__", False):
        return None

    return {
        "authenticated": True,
        "roles": getattr(func, "__bloom_required_roles__", []),
    }
