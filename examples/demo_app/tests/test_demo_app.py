"""Demo App 테스트

앱별 마이그레이션, ExceptionHandler, Entity 속성 테스트입니다.

Features:
- 앱별 마이그레이션 테스트
- ExceptionHandler 테스트
- Entity __app__ 속성 테스트
"""

from __future__ import annotations

import pytest
from pathlib import Path


# =============================================================================
# Test: ExceptionHandler 테스트
# =============================================================================


class TestExceptionHandler:
    """ExceptionHandler 테스트"""

    @pytest.mark.asyncio
    async def test_not_found_handler(self):
        """NotFoundError 핸들러 테스트"""
        from bloom.web.error import NotFoundError
        from examples.demo_app.common.error_handlers import GlobalExceptionHandler

        handler = GlobalExceptionHandler()

        # Mock request
        class MockRequest:
            path = "/api/users/999"

        exc = NotFoundError("User not found")
        response = await handler.handle_not_found(MockRequest(), exc)

        assert response.status_code == 404
        import json
        body = json.loads(response.body)
        assert body["error"]["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_business_error_handler(self):
        """BusinessError 핸들러 테스트"""
        from examples.demo_app.common.error_handlers import (
            GlobalExceptionHandler,
            BusinessError,
        )

        handler = GlobalExceptionHandler()

        class MockRequest:
            path = "/api/orders"

        exc = BusinessError("Order cannot be cancelled", code="CANCEL_NOT_ALLOWED")
        response = await handler.handle_business_error(MockRequest(), exc)

        assert response.status_code == 422
        import json
        body = json.loads(response.body)
        assert body["error"]["code"] == "CANCEL_NOT_ALLOWED"

    @pytest.mark.asyncio
    async def test_insufficient_stock_handler(self):
        """InsufficientStockError 핸들러 테스트"""
        from examples.demo_app.common.error_handlers import (
            GlobalExceptionHandler,
            InsufficientStockError,
        )

        handler = GlobalExceptionHandler()

        class MockRequest:
            path = "/api/orders"

        exc = InsufficientStockError(product_id=1, requested=10, available=5)
        response = await handler.handle_insufficient_stock(MockRequest(), exc)

        assert response.status_code == 422
        import json
        body = json.loads(response.body)
        assert body["error"]["code"] == "INSUFFICIENT_STOCK"
        assert body["error"]["details"]["product_id"] == 1
        assert body["error"]["details"]["requested"] == 10
        assert body["error"]["details"]["available"] == 5

    @pytest.mark.asyncio
    async def test_validation_error_handler(self):
        """ValidationError 핸들러 테스트"""
        from bloom.web.error import ValidationError
        from examples.demo_app.common.error_handlers import GlobalExceptionHandler

        handler = GlobalExceptionHandler()

        class MockRequest:
            path = "/api/users"

        exc = ValidationError("Invalid email format")
        response = await handler.handle_validation_error(MockRequest(), exc)

        assert response.status_code == 400
        import json
        body = json.loads(response.body)
        assert body["error"]["code"] == "VALIDATION_ERROR"


# =============================================================================
# Test: 앱별 마이그레이션 테스트
# =============================================================================


class TestAppMigrations:
    """앱별 마이그레이션 테스트"""

    def test_migration_files_exist(self):
        """마이그레이션 파일 존재 확인"""
        migrations_dir = Path(__file__).parent.parent / "migrations"

        # 앱별 디렉토리 존재 확인
        assert (migrations_dir / "users").exists()
        assert (migrations_dir / "products").exists()
        assert (migrations_dir / "orders").exists()
        assert (migrations_dir / "notifications").exists()

        # 마이그레이션 파일 존재 확인
        assert (migrations_dir / "users" / "0001_create_user.py").exists()
        assert (migrations_dir / "products" / "0001_create_product.py").exists()
        assert (migrations_dir / "orders" / "0001_create_order.py").exists()
        assert (migrations_dir / "notifications" / "0001_create_notification.py").exists()

    def test_migration_dependencies(self):
        """마이그레이션 의존성 확인"""
        from examples.demo_app.migrations.orders import migration as orders_migration
        from examples.demo_app.migrations.notifications import migration as notifications_migration

        # orders 마이그레이션은 users, products에 의존
        assert "users:0001_create_user" in orders_migration.dependencies
        assert "products:0001_create_product" in orders_migration.dependencies

        # notifications 마이그레이션은 users에 의존
        assert "users:0001_create_user" in notifications_migration.dependencies

    @pytest.mark.asyncio
    async def test_apply_migrations_in_order(self):
        """마이그레이션 의존성 순서 적용 테스트"""
        from bloom.db.session import SessionFactory
        from bloom.db.backends.sqlite import SQLiteBackend
        from bloom.db.migrations.app import AppMigrationManager

        # 임시 DB로 테스트
        backend = SQLiteBackend(":memory:")
        session_factory = SessionFactory(backend)

        # demo_app 마이그레이션 디렉토리
        migrations_dir = Path(__file__).parent.parent / "migrations"

        manager = AppMigrationManager(
            session_factory=session_factory,
            base_dir=migrations_dir,
        )

        # 마이그레이션 적용
        applied = manager.migrate_all()

        # 의존성 순서 확인: users, products가 orders, notifications보다 먼저
        users_idx = next((i for i, m in enumerate(applied) if "users" in m), -1)
        products_idx = next((i for i, m in enumerate(applied) if "products" in m), -1)
        orders_idx = next((i for i, m in enumerate(applied) if "orders" in m), -1)
        notifications_idx = next((i for i, m in enumerate(applied) if "notifications" in m), -1)

        # users, products가 먼저 적용되어야 함
        if orders_idx >= 0:
            assert users_idx < orders_idx
            assert products_idx < orders_idx

        if notifications_idx >= 0:
            assert users_idx < notifications_idx

        # 테이블 생성 확인
        with session_factory.session() as session:
            tables = session._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {t["name"] for t in tables}

            assert "user" in table_names
            assert "product" in table_names
            assert "orders" in table_names  # 'order'는 SQL 예약어라서 'orders' 사용
            assert "notification" in table_names


# =============================================================================
# Test: Entity __app__ 속성 테스트
# =============================================================================


class TestEntityAppAttribute:
    """엔티티 __app__ 속성 테스트"""

    def test_entity_has_app_attribute(self):
        """엔티티에 __app__ 속성이 있는지 확인"""
        from examples.demo_app.users.entity import User
        from examples.demo_app.products.entity import Product
        from examples.demo_app.orders.entity import Order, OrderItem
        from examples.demo_app.notifications.entity import Notification

        assert getattr(User, "__app__", None) == "users"
        assert getattr(Product, "__app__", None) == "products"
        assert getattr(Order, "__app__", None) == "orders"
        assert getattr(OrderItem, "__app__", None) == "orders"
        assert getattr(Notification, "__app__", None) == "notifications"


# =============================================================================
# Test: HTTP 엔드포인트 테스트 (TestClient 사용)
# =============================================================================


class TestHTTPEndpoints:
    """HTTP 엔드포인트 테스트"""

    @pytest.mark.asyncio
    async def test_health_check(self):
        """헬스체크 API 테스트"""
        from bloom.testing import TestClient
        from examples.demo_app.app import application

        client = TestClient(application.asgi)
        response = await client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "demo-app"


# =============================================================================
# 실행
# =============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
