"""Demo App Migrations - 앱별 마이그레이션

앱별 마이그레이션 디렉토리 구조:
migrations/
├── users/           # users 앱 마이그레이션
├── products/        # products 앱 마이그레이션
├── orders/          # orders 앱 마이그레이션 (users, products 의존)
└── notifications/   # notifications 앱 마이그레이션 (users 의존)
"""
