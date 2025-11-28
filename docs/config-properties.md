# Configuration Properties 사용 가이드

Bloom의 설정 관리 시스템은 Spring Boot의 `@ConfigurationProperties`와 유사하게 타입 안전한 설정 바인딩을 제공합니다.

## 기본 사용법

### 1. dataclass 사용

```python
from dataclasses import dataclass
from bloom import Application, Component
from bloom.config import ConfigurationProperties

# 설정 클래스 정의
@ConfigurationProperties("app.database")
@dataclass
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5432
    username: str = ""
    password: str = ""

# Component에서 주입
@Component
class DatabaseService:
    config: DatabaseConfig  # 자동으로 app.database.* 설정 바인딩
    
    def connect(self):
        print(f"Connecting to {self.config.host}:{self.config.port}")

# 애플리케이션 설정
app = Application("myapp")
app.load_config("config/application.yaml")  # YAML 파일에서 로드
app.scan(__name__).ready()
```

**config/application.yaml:**
```yaml
app:
  database:
    host: db.example.com
    port: 3306
    username: admin
    password: secret
```

### 2. Pydantic 사용 (검증 포함)

```python
from pydantic import BaseModel, Field
from bloom.config import ConfigurationProperties

@ConfigurationProperties("app.database")
class DatabaseConfig(BaseModel):
    host: str
    port: int = Field(ge=1, le=65535, default=5432)
    username: str
    password: str
    pool_size: int = Field(ge=1, le=100, default=10)
```

## 설정 로드 방법

### 1. YAML 파일
```python
app.load_config("config/application.yaml")
```

### 2. JSON 파일
```python
app.load_config("config/application.json")
```

### 3. 딕셔너리
```python
app.load_config({
    "app": {
        "database": {
            "host": "localhost",
            "port": 5432
        }
    }
}, source_type="dict")
```

### 4. 환경 변수
```python
# 환경 변수만 로드
app.load_config(source_type="env")

# 환경 변수 형식: PREFIX_KEY_SUBKEY=value
# 예: APP_DATABASE_HOST=localhost
```

### 5. 여러 소스 병합
```python
app.load_config("config/application.yaml")  # 기본 설정
app.load_config(source_type="env")          # 환경 변수로 오버라이드
```

## 중첩된 설정

```python
@ConfigurationProperties("app.database")
@dataclass
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5432
    
    @dataclass
    class Pool:
        min_size: int = 5
        max_size: int = 20
    
    pool: Pool = field(default_factory=Pool)

# config.yaml
app:
  database:
    host: localhost
    port: 5432
    pool:
      min_size: 10
      max_size: 50
```

## 독립적인 설정 클래스 (권장 패턴)

```python
# 각 설정을 독립적으로 정의
@ConfigurationProperties("database")
@dataclass
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5432

@ConfigurationProperties("redis")
@dataclass
class RedisConfig:
    host: str = "localhost"
    port: int = 6379

# 필요한 설정만 주입
@Component
class DatabaseService:
    config: DatabaseConfig  # database.* 설정만 주입

@Component
class CacheService:
    config: RedisConfig  # redis.* 설정만 주입
```

## 장점

- ✅ **타입 안전성**: IDE 자동완성, 타입 체크 지원
- ✅ **검증**: Pydantic으로 설정 검증
- ✅ **중앙화**: 모든 설정을 한 곳에서 관리
- ✅ **유연성**: 여러 소스에서 로드 및 오버라이드
- ✅ **선택적 주입**: 필요한 설정만 주입 가능
