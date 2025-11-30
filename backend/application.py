"""backend Application

Bloom Framework 기반 애플리케이션입니다.

실행 방법:
    # 개발 서버 (프로젝트 루트에서)
    bloom server --application=backend.application:application

    # 또는 backend 디렉토리에서
    cd backend && bloom server

    # 워커
    bloom worker --application=backend.application:application

    # 마이그레이션
    bloom db makemigrations
    bloom db migrate
"""

from pathlib import Path

from bloom import Application

from backend.settings import configure


# =============================================================================
# Application 인스턴스
# =============================================================================

application = Application("backend")

# 설정 모듈 스캔 + backend 디렉토리만 자동 스캔 + DI 초기화
backend_dir = Path(__file__).parent
application.scan(configure).auto_import(
    base_path=backend_dir, exclude={"application.py", "settings", "tests"}
).ready()
