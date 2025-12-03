"""bloom.web.routing.decorators - Controller and Mapping decorators"""

from __future__ import annotations

from typing import Any, Callable, TypeVar, overload, TYPE_CHECKING

if TYPE_CHECKING:
    from .router import RouteHandler

T = TypeVar("T", bound=type)
F = TypeVar("F", bound=Callable[..., Any])


# =============================================================================
# Controller Metadata
# =============================================================================


def _get_controller_meta(cls: type) -> dict[str, Any]:
    """Controller 메타데이터 가져오기"""
    if not hasattr(cls, "__bloom_controller__"):
        cls.__bloom_controller__ = {
            "prefix": "",
            "routes": [],
            "middlewares": [],
        }
    return cls.__bloom_controller__


def _get_route_meta(func: Callable[..., Any]) -> dict[str, Any]:
    """Route 메타데이터 가져오기"""
    if not hasattr(func, "__bloom_route__"):
        func.__bloom_route__ = {
            "path": "",
            "methods": [],
            "name": None,
        }
    return func.__bloom_route__


# =============================================================================
# @Controller
# =============================================================================


@overload
def Controller(cls: T) -> T:
    """@Controller - 기본 prefix 없음"""
    ...


@overload
def Controller(
    *,
    prefix: str = "",
) -> Callable[[T], T]:
    """@Controller(prefix="/api") - prefix 지정"""
    ...


def Controller(
    cls: T | None = None,
    *,
    prefix: str = "",
) -> T | Callable[[T], T]:
    """
    클래스를 Controller로 등록하는 데코레이터.
    
    @Component도 함께 적용되어 DI 컨테이너에 등록됩니다.
    
    사용 예:
        @Controller
        class UserController:
            user_service: UserService
            
            @GetMapping("/users")
            async def list_users(self):
                return await self.user_service.list_all()
        
        @Controller(prefix="/api/v1")
        class ApiController:
            @GetMapping("/status")
            async def status(self):
                return {"status": "ok"}
    """
    from bloom.core.decorators import Component
    
    def decorator(cls: T) -> T:
        # Controller 메타데이터 설정
        meta = _get_controller_meta(cls)
        # prefix가 이미 설정되어 있으면 (RequestMapping에서) 덮어쓰지 않음
        if prefix or not meta.get("prefix"):
            meta["prefix"] = prefix
        
        # @Component 적용
        Component(cls)
        
        return cls
    
    if cls is not None:
        return decorator(cls)
    return decorator


# =============================================================================
# @RequestMapping
# =============================================================================


def RequestMapping(
    path: str = "",
    methods: list[str] | None = None,
) -> Callable[[T], T]:
    """
    클래스 레벨 경로 매핑 데코레이터.
    
    @Controller와 함께 사용하여 prefix를 설정합니다.
    
    사용 예:
        @Controller
        @RequestMapping("/api/v1/users")
        class UserController:
            @GetMapping("")  # /api/v1/users
            async def list_users(self):
                pass
            
            @GetMapping("/{id}")  # /api/v1/users/{id}
            async def get_user(self, id: int):
                pass
    """
    def decorator(cls: T) -> T:
        meta = _get_controller_meta(cls)
        meta["prefix"] = path
        if methods:
            meta["default_methods"] = methods
        return cls
    
    return decorator


# =============================================================================
# HTTP Method Mappings
# =============================================================================


def _create_method_decorator(
    *methods: str,
) -> Callable[[str, str | None], Callable[[F], F]]:
    """HTTP 메서드 데코레이터 팩토리"""
    
    def mapping(
        path: str = "",
        name: str | None = None,
    ) -> Callable[[F], F]:
        def decorator(func: F) -> F:
            meta = _get_route_meta(func)
            meta["path"] = path
            meta["methods"] = list(methods)
            meta["name"] = name or func.__name__
            return func
        return decorator
    
    return mapping


# 각 HTTP 메서드별 데코레이터
GetMapping = _create_method_decorator("GET")
PostMapping = _create_method_decorator("POST")
PutMapping = _create_method_decorator("PUT")
DeleteMapping = _create_method_decorator("DELETE")
PatchMapping = _create_method_decorator("PATCH")


# 여러 메서드를 지원하는 범용 데코레이터
def Mapping(
    path: str = "",
    methods: list[str] | None = None,
    name: str | None = None,
) -> Callable[[F], F]:
    """
    범용 라우트 매핑 데코레이터.
    
    여러 HTTP 메서드를 한 번에 지정할 수 있습니다.
    
    사용 예:
        @Controller
        class ResourceController:
            @Mapping("/resource", methods=["GET", "HEAD"])
            async def get_resource(self):
                pass
    """
    methods = methods or ["GET"]
    
    def decorator(func: F) -> F:
        meta = _get_route_meta(func)
        meta["path"] = path
        meta["methods"] = methods
        meta["name"] = name or func.__name__
        return func
    
    return decorator


# =============================================================================
# Helper Functions
# =============================================================================


def get_controller_routes(controller_cls: type) -> list[dict[str, Any]]:
    """Controller 클래스에서 모든 라우트 정보 추출
    
    Returns:
        [{"path": "/users", "methods": ["GET"], "handler": <method>, "name": "list_users"}, ...]
    """
    meta = _get_controller_meta(controller_cls)
    prefix = meta.get("prefix", "")
    routes = []
    
    for name in dir(controller_cls):
        if name.startswith("_"):
            continue
        
        method = getattr(controller_cls, name, None)
        if method is None or not callable(method):
            continue
        
        route_meta = getattr(method, "__bloom_route__", None)
        if route_meta is None:
            continue
        
        path = prefix + route_meta.get("path", "")
        methods = route_meta.get("methods", [])
        route_name = route_meta.get("name", name)
        
        routes.append({
            "path": path,
            "methods": methods,
            "handler": method,
            "name": route_name,
            "method_name": name,
        })
    
    return routes


def is_controller(cls: type) -> bool:
    """Controller 클래스인지 확인"""
    return hasattr(cls, "__bloom_controller__")
