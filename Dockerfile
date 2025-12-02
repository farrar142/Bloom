# Bloom Framework Development Environment
FROM python:3.13-slim

# 환경 변수 설정
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 시스템 패키지 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    vim \
    && rm -rf /var/lib/apt/lists/*

# uv 설치 (빠른 Python 패키지 매니저)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# 작업 디렉토리 설정
WORKDIR /workspace

# 의존성 파일 복사 및 설치
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# 소스 코드 복사
COPY . .

# 개발 모드로 패키지 설치
RUN uv pip install -e .

# 기본 포트 노출 (웹 서버용)
EXPOSE 8000

# 기본 명령어
CMD ["bash"]
