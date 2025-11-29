"""Bloom Framework OpenAPI 예제 앱

복잡한 OpenAPI 스펙을 생성하는 예제입니다.
다양한 HTTP 메서드, 파라미터 타입, 요청/응답 모델을 보여줍니다.

실행 방법:
    uv run uvicorn examples.example_openapi_app:app.asgi --reload

API 문서 확인:
    - Swagger UI: http://localhost:8000/docs
    - ReDoc: http://localhost:8000/redoc
    - OpenAPI JSON: http://localhost:8000/openapi.json
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from bloom import (
    Application,
    Component,
    Controller,
    Get,
    Post,
    Put,
    Delete,
    Patch,
    RequestMapping,
)
from bloom.core.decorators import Factory
from bloom.web.http import HttpResponse
from bloom.web.params import RequestBody, HttpHeader, HttpCookie, UploadedFile
from bloom.web.openapi import (
    OpenAPIConfig,
    OpenAPIContact,
    OpenAPILicense,
    OpenAPIServer,
    OpenAPITag,
)


# ============================================================
# 열거형 정의
# ============================================================


class UserRole(str, Enum):
    """사용자 역할"""

    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


class OrderStatus(str, Enum):
    """주문 상태"""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


# ============================================================
# 요청/응답 모델 정의 (Pydantic)
# ============================================================


class UserCreateRequest(BaseModel):
    """사용자 생성 요청"""

    username: str = Field(..., min_length=3, max_length=50, description="사용자명")
    email: str = Field(..., description="이메일 주소")
    password: str = Field(..., min_length=8, description="비밀번호 (최소 8자)")
    role: UserRole = Field(default=UserRole.USER, description="사용자 역할")
    tags: list[str] = Field(default_factory=list, description="태그 목록")


class UserUpdateRequest(BaseModel):
    """사용자 수정 요청"""

    username: str | None = Field(None, min_length=3, max_length=50)
    email: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    """사용자 응답"""

    id: str
    username: str
    email: str
    role: UserRole
    is_active: bool = True
    created_at: str
    tags: list[str] = []


class UserListResponse(BaseModel):
    """사용자 목록 응답"""

    items: list[UserResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class ProductRequest(BaseModel):
    """상품 요청"""

    name: str = Field(..., min_length=1, max_length=200, description="상품명")
    description: str | None = Field(None, max_length=2000, description="상품 설명")
    price: float = Field(..., gt=0, description="가격 (0보다 큰 값)")
    stock: int = Field(default=0, ge=0, description="재고 수량")
    category_id: str = Field(..., description="카테고리 ID")
    tags: list[str] = Field(default_factory=list, description="상품 태그")
    metadata: dict[str, str] = Field(
        default_factory=dict, description="추가 메타데이터"
    )


class ProductResponse(BaseModel):
    """상품 응답"""

    id: str
    name: str
    description: str | None
    price: float
    stock: int
    category_id: str
    tags: list[str]
    metadata: dict[str, str]
    created_at: str
    updated_at: str | None


class OrderItem(BaseModel):
    """주문 항목"""

    product_id: str
    quantity: int = Field(..., gt=0, description="주문 수량")
    unit_price: float


class OrderCreateRequest(BaseModel):
    """주문 생성 요청"""

    user_id: str
    items: list[OrderItem] = Field(..., min_length=1, description="주문 항목 목록")
    shipping_address: str
    notes: str | None = None


class OrderResponse(BaseModel):
    """주문 응답"""

    id: str
    user_id: str
    items: list[OrderItem]
    status: OrderStatus
    total_amount: float
    shipping_address: str
    notes: str | None
    created_at: str
    updated_at: str | None


class FileUploadResponse(BaseModel):
    """파일 업로드 응답"""

    filename: str
    content_type: str
    size: int
    url: str


class ErrorResponse(BaseModel):
    """에러 응답"""

    error: str
    message: str
    details: dict[str, str] | None = None


class PaginationParams(BaseModel):
    """페이지네이션 파라미터"""

    page: int = Field(default=1, ge=1, description="페이지 번호")
    page_size: int = Field(default=20, ge=1, le=100, description="페이지 크기")


class LoginRequest(BaseModel):
    """로그인 요청"""

    username: str = Field(..., description="사용자명")
    password: str = Field(..., description="비밀번호")


# ============================================================
# Dataclass 모델 (Pydantic 외에도 dataclass 지원)
# ============================================================


@dataclass
class CategoryRequest:
    """카테고리 요청 (dataclass)"""

    name: str
    description: str | None = None
    parent_id: str | None = None


@dataclass
class CategoryResponse:
    """카테고리 응답 (dataclass)"""

    id: str
    name: str
    description: str | None
    parent_id: str | None
    children: list[dict] = field(default_factory=list)  # 순환 참조 방지


# ============================================================
# 서비스 레이어
# ============================================================


@Component
class UserService:
    """사용자 서비스"""

    def get_users(
        self, page: int = 1, page_size: int = 20, role: UserRole | None = None
    ) -> UserListResponse:
        """사용자 목록 조회"""
        users = [
            UserResponse(
                id=f"user-{i}",
                username=f"user{i}",
                email=f"user{i}@example.com",
                role=role or UserRole.USER,
                created_at=datetime.now().isoformat(),
                tags=["active", "verified"] if i % 2 == 0 else [],
            )
            for i in range((page - 1) * page_size + 1, page * page_size + 1)
        ]
        return UserListResponse(
            items=users,
            total=100,
            page=page,
            page_size=page_size,
            has_next=page < 5,
        )

    def get_user(self, user_id: str) -> UserResponse | None:
        """사용자 조회"""
        return UserResponse(
            id=user_id,
            username=f"user_{user_id}",
            email=f"{user_id}@example.com",
            role=UserRole.USER,
            created_at=datetime.now().isoformat(),
        )

    def create_user(self, data: UserCreateRequest) -> UserResponse:
        """사용자 생성"""
        import uuid

        return UserResponse(
            id=str(uuid.uuid4())[:8],
            username=data.username,
            email=data.email,
            role=data.role,
            created_at=datetime.now().isoformat(),
            tags=data.tags,
        )

    def update_user(self, user_id: str, data: UserUpdateRequest) -> UserResponse:
        """사용자 수정"""
        return UserResponse(
            id=user_id,
            username=data.username or "unchanged",
            email=data.email or "unchanged@example.com",
            role=data.role or UserRole.USER,
            is_active=data.is_active if data.is_active is not None else True,
            created_at=datetime.now().isoformat(),
        )

    def delete_user(self, user_id: str) -> bool:
        """사용자 삭제"""
        return True


@Component
class ProductService:
    """상품 서비스"""

    def get_products(
        self,
        category_id: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        in_stock: bool | None = None,
    ) -> list[ProductResponse]:
        """상품 목록 조회"""
        return [
            ProductResponse(
                id=f"prod-{i}",
                name=f"Product {i}",
                description=f"Description for product {i}",
                price=100.0 * i,
                stock=10 * i,
                category_id=category_id or "cat-1",
                tags=["featured", "new"],
                metadata={"brand": "Bloom"},
                created_at=datetime.now().isoformat(),
                updated_at=None,
            )
            for i in range(1, 6)
        ]

    def create_product(self, data: ProductRequest) -> ProductResponse:
        """상품 생성"""
        import uuid

        return ProductResponse(
            id=str(uuid.uuid4())[:8],
            name=data.name,
            description=data.description,
            price=data.price,
            stock=data.stock,
            category_id=data.category_id,
            tags=data.tags,
            metadata=data.metadata,
            created_at=datetime.now().isoformat(),
            updated_at=None,
        )


@Component
class OrderService:
    """주문 서비스"""

    def create_order(self, data: OrderCreateRequest) -> OrderResponse:
        """주문 생성"""
        import uuid

        total = sum(item.quantity * item.unit_price for item in data.items)
        return OrderResponse(
            id=str(uuid.uuid4())[:8],
            user_id=data.user_id,
            items=data.items,
            status=OrderStatus.PENDING,
            total_amount=total,
            shipping_address=data.shipping_address,
            notes=data.notes,
            created_at=datetime.now().isoformat(),
            updated_at=None,
        )

    def get_order(self, order_id: str) -> OrderResponse | None:
        """주문 조회"""
        return OrderResponse(
            id=order_id,
            user_id="user-1",
            items=[OrderItem(product_id="prod-1", quantity=2, unit_price=100.0)],
            status=OrderStatus.CONFIRMED,
            total_amount=200.0,
            shipping_address="123 Main St",
            notes=None,
            created_at=datetime.now().isoformat(),
            updated_at=None,
        )

    def update_order_status(
        self, order_id: str, status: OrderStatus
    ) -> OrderResponse | None:
        """주문 상태 변경"""
        order = self.get_order(order_id)
        if order:
            order.status = status
            order.updated_at = datetime.now().isoformat()
        return order


# ============================================================
# 컨트롤러
# ============================================================


@Controller
@RequestMapping("/api/v1/users")
class UserController:
    """
    사용자 관리 API

    사용자 CRUD 및 관련 기능을 제공합니다.
    """

    user_service: UserService

    @Get("")
    async def list_users(
        self,
        page: int = 1,
        page_size: int = 20,
        role: UserRole | None = None,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> UserListResponse:
        """
        사용자 목록 조회

        페이지네이션, 역할 필터, 활성화 상태 필터를 지원합니다.
        """
        return self.user_service.get_users(page, page_size, role)

    @Get("/{user_id}")
    async def get_user(self, user_id: str) -> UserResponse | HttpResponse:
        """
        사용자 상세 조회

        특정 사용자의 상세 정보를 조회합니다.
        """
        user = self.user_service.get_user(user_id)
        if not user:
            return HttpResponse.not_found("User not found")
        return user

    @Post("")
    async def create_user(self, body: RequestBody[UserCreateRequest]) -> UserResponse:
        """
        사용자 생성

        새로운 사용자를 생성합니다.
        """
        return self.user_service.create_user(body)

    @Put("/{user_id}")
    async def update_user(
        self,
        user_id: str,
        body: RequestBody[UserUpdateRequest],
    ) -> UserResponse:
        """
        사용자 수정

        기존 사용자 정보를 수정합니다.
        """
        return self.user_service.update_user(user_id, body)

    @Delete("/{user_id}")
    async def delete_user(self, user_id: str) -> dict:
        """
        사용자 삭제

        사용자를 삭제합니다.
        """
        self.user_service.delete_user(user_id)
        return {"deleted": True}

    @Get("/{user_id}/orders")
    async def get_user_orders(
        self,
        user_id: str,
        status: OrderStatus | None = None,
        limit: int = 10,
    ) -> list[OrderResponse]:
        """
        사용자 주문 목록

        특정 사용자의 주문 목록을 조회합니다.
        """
        return [
            OrderResponse(
                id=f"order-{i}",
                user_id=user_id,
                items=[OrderItem(product_id="prod-1", quantity=1, unit_price=100.0)],
                status=status or OrderStatus.CONFIRMED,
                total_amount=100.0,
                shipping_address="123 Main St",
                notes=None,
                created_at=datetime.now().isoformat(),
                updated_at=None,
            )
            for i in range(1, min(limit + 1, 6))
        ]


@Controller
@RequestMapping("/api/v1/products")
class ProductController:
    """
    상품 관리 API

    상품 CRUD 및 검색 기능을 제공합니다.
    """

    product_service: ProductService

    @Get("")
    async def list_products(
        self,
        category_id: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        in_stock: bool | None = None,
        sort_by: Literal["price", "name", "created_at"] = "created_at",
        sort_order: Literal["asc", "desc"] = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> list[ProductResponse]:
        """
        상품 목록 조회

        다양한 필터와 정렬 옵션을 지원합니다.
        """
        return self.product_service.get_products(
            category_id, min_price, max_price, in_stock
        )

    @Get("/{product_id}")
    async def get_product(self, product_id: str) -> ProductResponse | HttpResponse:
        """상품 상세 조회"""
        products = self.product_service.get_products()
        if not products:
            return HttpResponse.not_found("Product not found")
        return products[0]

    @Post("")
    async def create_product(
        self, body: RequestBody[ProductRequest]
    ) -> ProductResponse:
        """
        상품 생성

        새로운 상품을 등록합니다.
        """
        return self.product_service.create_product(body)

    @Put("/{product_id}")
    async def update_product(
        self,
        product_id: str,
        body: RequestBody[ProductRequest],
    ) -> ProductResponse:
        """상품 수정"""
        product = self.product_service.create_product(body)
        product.id = product_id
        return product

    @Delete("/{product_id}")
    async def delete_product(self, product_id: str) -> dict:
        """상품 삭제"""
        return {"deleted": True}


@Controller
@RequestMapping("/api/v1/orders")
class OrderController:
    """
    주문 관리 API

    주문 생성, 조회, 상태 관리 기능을 제공합니다.
    """

    order_service: OrderService

    @Get("/{order_id}")
    async def get_order(self, order_id: str) -> OrderResponse | HttpResponse:
        """주문 상세 조회"""
        order = self.order_service.get_order(order_id)
        if not order:
            return HttpResponse.not_found("Order not found")
        return order

    @Post("")
    async def create_order(
        self, body: RequestBody[OrderCreateRequest]
    ) -> OrderResponse:
        """
        주문 생성

        새로운 주문을 생성합니다.
        """
        return self.order_service.create_order(body)

    @Patch("/{order_id}/status")
    async def update_order_status(
        self,
        order_id: str,
        status: OrderStatus,
    ) -> OrderResponse | HttpResponse:
        """
        주문 상태 변경

        주문의 상태를 변경합니다.
        """
        result = self.order_service.update_order_status(order_id, status)
        if not result:
            return HttpResponse.not_found("Order not found")
        return result

    @Post("/{order_id}/cancel")
    async def cancel_order(
        self, order_id: str, reason: str | None = None
    ) -> OrderResponse | HttpResponse:
        """
        주문 취소

        주문을 취소합니다.
        """
        result = self.order_service.update_order_status(order_id, OrderStatus.CANCELLED)
        if not result:
            return HttpResponse.not_found("Order not found")
        return result


@Controller
@RequestMapping("/api/v1/categories")
class CategoryController:
    """
    카테고리 관리 API

    상품 카테고리 관리 기능을 제공합니다.
    (dataclass 기반 모델 예시)
    """

    @Get("")
    async def list_categories(
        self, parent_id: str | None = None
    ) -> list[CategoryResponse]:
        """카테고리 목록 조회"""
        return [
            CategoryResponse(
                id=f"cat-{i}",
                name=f"Category {i}",
                description=f"Description for category {i}",
                parent_id=parent_id,
            )
            for i in range(1, 6)
        ]

    @Get("/{category_id}")
    async def get_category(self, category_id: str) -> CategoryResponse:
        """카테고리 상세 조회"""
        return CategoryResponse(
            id=category_id,
            name="Electronics",
            description="Electronic products",
            parent_id=None,
            children=[
                {
                    "id": "cat-1-1",
                    "name": "Phones",
                    "description": None,
                    "parent_id": category_id,
                },
                {
                    "id": "cat-1-2",
                    "name": "Laptops",
                    "description": None,
                    "parent_id": category_id,
                },
            ],
        )

    @Post("")
    async def create_category(
        self, body: RequestBody[CategoryRequest]
    ) -> CategoryResponse:
        """카테고리 생성"""
        import uuid

        return CategoryResponse(
            id=str(uuid.uuid4())[:8],
            name=body.name,
            description=body.description,
            parent_id=body.parent_id,
        )


@Controller
@RequestMapping("/api/v1/files")
class FileController:
    """
    파일 관리 API

    파일 업로드/다운로드 기능을 제공합니다.
    """

    @Post("/upload")
    async def upload_file(
        self,
        file: UploadedFile,
        description: str | None = None,
    ) -> FileUploadResponse:
        """
        파일 업로드

        단일 파일을 업로드합니다.
        """
        return FileUploadResponse(
            filename=file.filename,
            content_type=file.content_type,
            size=len(file.content),
            url=f"/files/{file.filename}",
        )

    @Post("/upload-multiple")
    async def upload_multiple_files(
        self,
        files: list[UploadedFile],
    ) -> list[FileUploadResponse]:
        """
        다중 파일 업로드

        여러 파일을 한번에 업로드합니다.
        """
        return [
            FileUploadResponse(
                filename=f.filename,
                content_type=f.content_type,
                size=len(f.content),
                url=f"/files/{f.filename}",
            )
            for f in files
        ]


@Controller
@RequestMapping("/api/v1/auth")
class AuthController:
    """
    인증 API

    로그인, 로그아웃, 토큰 관리 기능을 제공합니다.
    """

    @Post("/login")
    async def login(
        self,
        body: RequestBody[LoginRequest],
    ) -> dict:
        """
        로그인

        사용자 인증 후 토큰을 발급합니다.
        """
        return {
            "access_token": "eyJhbGciOiJIUzI1NiIs...",
            "token_type": "bearer",
            "expires_in": 3600,
        }

    @Post("/logout")
    async def logout(
        self,
        authorization: HttpHeader["Authorization"] | None = None,
    ) -> dict:
        """
        로그아웃

        현재 세션을 종료합니다.
        """
        return {"message": "Logged out successfully"}

    @Post("/refresh")
    async def refresh_token(
        self,
        refresh_token: HttpCookie["refresh_token"] | None = None,
    ) -> dict:
        """
        토큰 갱신

        리프레시 토큰으로 새로운 액세스 토큰을 발급합니다.
        """
        return {
            "access_token": "eyJhbGciOiJIUzI1NiIs...",
            "token_type": "bearer",
            "expires_in": 3600,
        }


@Controller
class HealthController:
    """헬스체크 API"""

    @Get("/health")
    async def health(self) -> dict:
        """
        헬스체크

        서버 상태를 확인합니다.
        """
        import os
        import sys

        return {
            "status": "healthy",
            "pid": os.getpid(),
            "python_version": sys.version.split()[0],
        }

    @Get("/")
    async def root(self) -> dict:
        """API 루트"""
        return {
            "name": "Bloom OpenAPI Example",
            "version": "1.0.0",
            "docs": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
        }


# ============================================================
# OpenAPI 설정
# ============================================================


@Component
class OpenAPIConfiguration:
    @Factory
    def openapi_config(self) -> OpenAPIConfig:
        return OpenAPIConfig(
            title="Bloom E-Commerce API",
            version="1.0.0",
            description=""",
            
# Bloom E-Commerce API

이 API는 Bloom Framework로 구축된 E-Commerce 플랫폼 예제입니다.

## 기능

- **사용자 관리**: 사용자 CRUD, 역할 관리
- **상품 관리**: 상품 CRUD, 카테고리, 검색
- **주문 관리**: 주문 생성, 상태 추적
- **파일 관리**: 파일 업로드/다운로드
- **인증**: 로그인, 토큰 관리

## 인증

API 인증은 Bearer 토큰을 사용합니다:
```
Authorization: Bearer <access_token>
```

## 에러 응답

모든 에러는 다음 형식으로 반환됩니다:
```json
{
    "error": "error_code",
    "message": "Human readable message",
    "details": {}
}
```
            """,
            terms_of_service="https://example.com/terms",
            contact=OpenAPIContact(
                name="Bloom Support",
                email="support@bloom.example.com",
                url="https://bloom.example.com",
            ),
            license=OpenAPILicense(
                name="MIT",
                url="https://opensource.org/licenses/MIT",
            ),
            servers=[
                OpenAPIServer(url="http://localhost:8000", description="Development"),
                OpenAPIServer(
                    url="https://api.bloom.example.com", description="Production"
                ),
            ],
            tags=[
                OpenAPITag(name="Users", description="사용자 관리 API"),
                OpenAPITag(name="Products", description="상품 관리 API"),
                OpenAPITag(name="Orders", description="주문 관리 API"),
                OpenAPITag(name="Categories", description="카테고리 관리 API"),
                OpenAPITag(name="Files", description="파일 관리 API"),
                OpenAPITag(name="Auth", description="인증 API"),
            ],
        )


# ============================================================
# 애플리케이션 생성
# ============================================================

import examples.example_openapi_app as module

app = Application("openapi_example").scan(module).ready()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "examples.example_openapi_app:app.asgi", host="0.0.0.0", port=8000, reload=True
    )
