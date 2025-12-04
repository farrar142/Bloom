"""Demo Application - Bloom 프레임워크 종합 예제

실제 애플리케이션처럼 도메인별로 분리된 구조입니다.

Structure:
    demo_app/
    ├── app.py              # Application 인스턴스
    ├── settings/           # 설정 (@Configuration, @Factory)
    ├── users/              # 사용자 도메인 (Entity, Repository, Service, Controller)
    ├── products/           # 상품 도메인
    ├── orders/             # 주문 도메인
    └── notifications/      # 알림 도메인 (@EventListener, @Task)

Features:
    - @Entity로 ORM 엔티티 정의
    - @Component, @Service, @Repository, @Configuration
    - @Factory를 통한 DI (TaskBroker, TaskBackend, EventBus)
    - @PostConstruct, @PreDestroy 라이프사이클
    - @Task 데코레이터로 비동기 태스크 (워커에서 실행)
    - @EventListener로 이벤트 기반 아키텍처
    - @Controller, @GetMapping, @PostMapping으로 REST API

Usage:
    # 워커 시작 (태스크 처리)
    REDIS_HOST=192.168.0.17 bloom queue -A examples.demo_app:application.queue worker -c 2 -Q default,notifications,emails

    # 웹 서버 시작 (API)
    REDIS_HOST=192.168.0.17 uvicorn examples.demo_app:application.asgi --reload --port 8000

    # API 테스트
    curl http://localhost:8000/health
    curl -X POST http://localhost:8000/api/users -H "Content-Type: application/json" -d '{"name": "홍길동", "email": "hong@example.com"}'
    curl http://localhost:8000/api/users
    curl http://localhost:8000/api/products
    curl -X POST http://localhost:8000/api/orders -H "Content-Type: application/json" -d '{"user_id": 1, "items": [{"product_id": 1, "quantity": 1}]}'
"""

from .app import application, asgi_app

__all__ = ["application", "asgi_app"]
