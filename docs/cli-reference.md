# CLI Reference

Bloom CLI는 애플리케이션 관리를 위한 명령줄 도구입니다.

## 설치 및 실행

```bash
# 패키지 설치 후
bloom --help

# 또는 Python -m으로 실행
python -m bloom --help
```

## 공통 패턴

Bloom CLI는 `application:application` 패턴을 기본값으로 사용합니다:

```python
# application.py (프로젝트 루트)
from bloom import Application

application = Application("myapp")

# application.queue - 태스크 큐
# SessionFactory - DB 세션 팩토리 (DI로 등록)
```

이 파일이 있으면 대부분의 명령어를 옵션 없이 실행할 수 있습니다.

## 명령어 목록

```
Usage: bloom [OPTIONS] COMMAND [ARGS]...

Options:
  --version  Show the version and exit.
  --help     Show this message and exit.

Commands:
  db           Database management commands
  server       Start development server
  startproject Create a new Bloom project
  task         Task management commands
  tests        Run tests with pytest
```

---

## task - 태스크 관리

백그라운드 태스크를 처리하는 워커를 실행합니다.

### 사용법

```bash
bloom task [OPTIONS]
```

### 옵션

| 옵션            | 단축 | 설명             | 기본값                    |
| --------------- | ---- | ---------------- | ------------------------- |
| `--worker`      | `-w` | 워커 시작        | -                         |
| `--application` | `-a` | Application 경로 | `application:application` |
| `--concurrency` | `-c` | 동시 워커 수     | 4                         |

### 예제

```bash
# 기본 실행 (application:application 사용, 자동으로 .queue 접근)
bloom task --worker
bloom task -w

# 동시성 설정
bloom task -w --concurrency 8
bloom task -w -c 8

# 다른 애플리케이션 지정 (Application 또는 QueueApplication 모두 가능)
bloom task -w --application=myapp.main:app
bloom task -w -a myapp.main:app

# 직접 QueueApplication 지정도 가능
bloom task -w -a myapp.main:app.queue
```

### 자동 .queue 탐색

`--application` 옵션에 `Application` 객체를 지정하면 자동으로 `.queue` 속성에 접근합니다:

```bash
# 이 두 명령은 동일합니다
bloom task -w --application=myapp:app
bloom task -w --application=myapp:app.queue
```

### Application 설정

```python
# application.py
from bloom import Application

application = Application("myapp")

# 태스크 정의
@application.queue.task
async def send_email(to: str, subject: str, body: str):
    # 이메일 전송 로직
    pass
```

### 에러 메시지

기본 애플리케이션을 찾을 수 없는 경우:

```
Error: Could not import default application.

Make sure you have 'application.py' with:
  from bloom import Application
  application = Application('myapp')
  # application.queue is your QueueApplication

Or specify explicitly:
  bloom task -w --application=mymodule:app
```

---

## tests - 테스트 실행

pytest를 사용하여 테스트를 실행합니다.

### 사용법

```bash
bloom tests [OPTIONS] [PATHS]...
```

### 옵션

| 옵션          | 단축 | 설명                 | 기본값 |
| ------------- | ---- | -------------------- | ------ |
| `--verbose`   | `-v` | 상세 출력            | -      |
| `--quiet`     | `-q` | 간단한 출력          | -      |
| `--exitfirst` | `-x` | 첫 실패 시 종료      | -      |
| `-k`          |      | 표현식에 맞는 테스트 | -      |
| `--cov`       |      | 커버리지 대상        | -      |

### 예제

```bash
# 기본 실행 (tests/ 디렉토리)
bloom tests

# 특정 파일 실행
bloom tests tests/test_api.py

# 상세 출력과 함께
bloom tests -v

# 첫 실패 시 종료
bloom tests -x

# 조합
bloom tests -v -x

# 표현식으로 필터링
bloom tests -k "test_user"

# 커버리지 측정
bloom tests --cov=src
```

---

## server - 개발 서버

uvicorn을 사용하여 개발 서버를 실행합니다.

### 사용법

```bash
bloom server [OPTIONS]
```

### 옵션

| 옵션            | 단축 | 설명                 | 기본값                    |
| --------------- | ---- | -------------------- | ------------------------- |
| `--application` | `-a` | Application 경로     | `application:application` |
| `--host`        | `-h` | 바인딩 호스트        | `127.0.0.1`               |
| `--port`        | `-p` | 바인딩 포트          | `8000`                    |
| `--reload`      |      | 자동 리로드 활성화   | `True`                    |
| `--no-reload`   |      | 자동 리로드 비활성화 | -                         |

### 예제

```bash
# 기본 실행
bloom server

# 포트 변경
bloom server --port 3000
bloom server -p 3000

# 호스트와 포트 지정
bloom server --host 0.0.0.0 --port 8080

# 자동 리로드 없이
bloom server --no-reload

# 다른 애플리케이션 지정
bloom server --application=backend.application:application
```

---

## startproject - 프로젝트 생성

새 Bloom 프로젝트를 생성합니다.

### 사용법

```bash
bloom startproject [OPTIONS] [PATH]
```

### 옵션

| 옵션     | 단축 | 설명          | 기본값        |
| -------- | ---- | ------------- | ------------- |
| `--name` | `-n` | 프로젝트 이름 | 디렉토리 이름 |

### 예제

```bash
# 새 디렉토리에 프로젝트 생성
bloom startproject myproject

# 현재 디렉토리에 프로젝트 생성
bloom startproject .

# 이름 지정
bloom startproject . --name myapp
```

### 생성되는 구조

```
myproject/
├── application.py
├── settings/
│   ├── __init__.py
│   ├── database.py
│   ├── advice.py
│   └── task.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── test_example.py
├── pyproject.toml
└── README.md
```

---

## db - 데이터베이스 관리

Django 스타일의 마이그레이션 및 DB 관리 도구입니다.

### 사용법

```bash
bloom db [OPTIONS] COMMAND [ARGS]...
```

### 전역 옵션

| 옵션               | 단축 | 설명                  | 기본값                    |
| ------------------ | ---- | --------------------- | ------------------------- |
| `--application`    | `-a` | Application 경로      | `application:application` |
| `--migrations-dir` | `-m` | 마이그레이션 디렉토리 | `migrations`              |
| `--entities`       | `-e` | 엔티티 모듈 (legacy)  | -                         |
| `--database`       | `-d` | DB URL (legacy)       | -                         |

### 하위 명령어

```
Commands:
  init            Initialize database configuration
  makemigrations  Generate new migrations
  migrate         Apply migrations to database
  resetdb         Reset database (drop all tables)
  shell           Open interactive database shell
  showmigrations  Show migration status
  sqlmigrate      Show SQL for a migration
```

---

### db init

`pyproject.toml`에 DB 설정을 초기화합니다.

```bash
bloom db init [OPTIONS]
```

| 옵션      | 설명               |
| --------- | ------------------ |
| `--force` | 기존 설정 덮어쓰기 |

#### 예제

```bash
bloom db init
bloom db init --force
```

#### 생성되는 설정

```toml
# pyproject.toml
[tool.bloom.db]
migrations_dir = "migrations"
entities_module = "app.models"
database_url = "sqlite:///db.sqlite3"
```

---

### db makemigrations

모델 변경사항을 감지하여 마이그레이션을 생성합니다.

```bash
bloom db makemigrations [OPTIONS]
```

| 옵션        | 단축 | 설명                   |
| ----------- | ---- | ---------------------- |
| `--name`    | `-n` | 마이그레이션 이름      |
| `--empty`   |      | 빈 마이그레이션 생성   |
| `--dry-run` |      | 생성될 내용만 미리보기 |

#### 예제

```bash
# 변경 감지하여 자동 생성
bloom db makemigrations

# 이름 지정
bloom db makemigrations --name add_email_field
bloom db makemigrations -n create_posts_table

# 빈 마이그레이션 (수동 작성용)
bloom db makemigrations --empty --name custom_data_migration

# Dry-run (미리보기)
bloom db makemigrations --dry-run
```

#### 출력 예시

```
Checking for model changes...
Initializing application: myapp
Using application: myapp
Database: sqlite://db.sqlite3
Found 3 entities: ['User', 'Post', 'Comment']

Created migration: migrations/0001_create_users.py
  Operations: 3
    - CreateTable(users)
    - CreateTable(posts)
    - CreateTable(comments)
```

---

### db migrate

마이그레이션을 데이터베이스에 적용합니다.

```bash
bloom db migrate [OPTIONS]
```

| 옵션       | 단축 | 설명                       |
| ---------- | ---- | -------------------------- |
| `--target` | `-t` | 특정 마이그레이션까지 적용 |
| `--fake`   |      | 실행 없이 적용 기록만      |

#### 예제

```bash
# 모든 미적용 마이그레이션 적용
bloom db migrate

# 특정 마이그레이션까지 적용
bloom db migrate --target 0002_add_posts
bloom db migrate -t 0002_add_posts

# Fake 적용 (기록만, SQL 실행 안함)
bloom db migrate --fake
```

#### 출력 예시

```
Applying migrations...
Using application: myapp
Database: sqlite://db.sqlite3
Migrations to apply: 2
  - 0001_create_users
  - 0002_add_posts

Applying...
  Applied: 0001_create_users
  Applied: 0002_add_posts

Done.
```

---

### db showmigrations

마이그레이션 상태를 표시합니다.

```bash
bloom db showmigrations
```

#### 출력 예시

```
Using application: myapp
Database: sqlite://db.sqlite3
Migrations:
  [X] 0001_create_users
  [X] 0002_add_posts
  [ ] 0003_add_comments
```

- `[X]` - 적용됨
- `[ ]` - 미적용

---

### db sqlmigrate

마이그레이션의 SQL을 미리 확인합니다.

```bash
bloom db sqlmigrate MIGRATION_NAME
```

#### 예제

```bash
bloom db sqlmigrate 0001_create_users
bloom db sqlmigrate initial  # 부분 매칭 가능
```

#### 출력 예시

```
-- SQL for migration: 0001_create_users
-- ============================================================

-- CreateTable(table_name='users', ...)
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE,
    created_at TIMESTAMP
);

-- CreateTable(table_name='posts', ...)
CREATE TABLE posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(200) NOT NULL,
    user_id INTEGER,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

---

### db resetdb

데이터베이스를 초기 상태로 리셋합니다.

```bash
bloom db resetdb [OPTIONS]
```

| 옵션                | 단축 | 설명                       |
| ------------------- | ---- | -------------------------- |
| `--yes`             | `-y` | 확인 없이 실행             |
| `--keep-migrations` |      | 마이그레이션 히스토리 유지 |

⚠️ **경고**: 이 명령은 모든 데이터를 삭제합니다!

#### 예제

```bash
# 확인 프롬프트와 함께 실행
bloom db resetdb

# 확인 없이 실행
bloom db resetdb --yes
bloom db resetdb -y

# 마이그레이션 히스토리만 유지
bloom db resetdb --keep-migrations
```

#### 출력 예시

```
⚠️  WARNING: This will permanently delete ALL data!

Tables to be dropped:
  - users
  - posts
  - comments
  - bloom_migrations (migration history)

Are you sure you want to continue? [y/N]: y
Resetting database...
  Dropped: comments
  Dropped: posts
  Dropped: users
  Dropped: bloom_migrations

✓ Database reset complete. Dropped 3 tables.

To recreate tables, run:
  bloom db migrate
```

---

### db shell

대화형 데이터베이스 셸을 엽니다.

```bash
bloom db shell
```

#### 사용 가능한 객체

| 객체                | 설명                   |
| ------------------- | ---------------------- |
| `session`           | 활성 데이터베이스 세션 |
| `session_factory`   | 세션 팩토리            |
| `User`, `Post`, ... | 엔티티 클래스들        |

#### 예제 세션

```python
Bloom DB Shell
==============
Database: sqlite://db.sqlite3
Entities: ['User', 'Post', 'Comment']

Available objects:
  session - Active database session
  session_factory - Session factory

Entity classes are available by name.

Example:
  users = session.query(User).all()

>>> users = session.query(User).all()
>>> for user in users:
...     print(user.name)
...
Alice
Bob

>>> new_user = User(name="Charlie", email="charlie@example.com")
>>> session.add(new_user)
>>> session.commit()
```

---

## Application 설정 예제

### 전체 설정

```python
# application.py
from bloom import Application
from bloom.core import Component, Factory
from bloom.db import SessionFactory, Entity, PrimaryKey, Column
from bloom.db.backends import SQLiteBackend
from bloom.task import QueueApplication

# Application 생성
application = Application("myapp")

# 태스크 큐
application.queue = QueueApplication(application)

# Entity 정의
@Entity
class User:
    id: int = PrimaryKey(auto_increment=True)
    name: str = Column(max_length=100)
    email: str = Column(max_length=255, unique=True)

@Entity
class Post:
    id: int = PrimaryKey(auto_increment=True)
    title: str = Column(max_length=200)

# DB 설정
@Component
class DatabaseConfig:
    @Factory
    def session_factory(self) -> SessionFactory:
        backend = SQLiteBackend("db.sqlite3")
        return SessionFactory(backend)

# 태스크 정의
@application.queue.task
async def process_data(data: dict):
    print(f"Processing: {data}")
```

### pyproject.toml 설정

```toml
[tool.bloom.db]
application = "application:application"
migrations_dir = "migrations"
```

이 설정이 있으면 `--application` 옵션 없이도 해당 애플리케이션을 사용합니다.

---

## 에러 메시지

### Application을 찾을 수 없음

```
Error: Could not import default application.

Make sure you have 'application.py' with:

  from bloom import Application
  from bloom.db import SessionFactory
  from bloom.db.backends import SQLiteBackend
  from bloom.core import Component, Factory

  application = Application('myapp')

  @Component
  class DatabaseConfig:
      @Factory
      def session_factory(self) -> SessionFactory:
          backend = SQLiteBackend('db.sqlite3')
          return SessionFactory(backend)

Or specify explicitly:
  bloom db --application=mymodule:app makemigrations

Or use legacy mode:
  bloom db --entities=myapp.models --database=sqlite:///db.sqlite3 makemigrations
```

### SessionFactory를 찾을 수 없음

```
Error: SessionFactory not found in Application DI container.

Please register SessionFactory in your Application:

  @Component
  class DatabaseConfig:
      @Factory
      def session_factory(self) -> SessionFactory:
          backend = SQLiteBackend('db.sqlite3')
          return SessionFactory(backend)
```

---

## Legacy 모드

Application 없이 직접 모듈과 DB URL을 지정할 수 있습니다:

```bash
# --entities와 --database 사용
bloom db --entities=myapp.models --database=sqlite:///db.sqlite3 makemigrations
bloom db --entities=myapp.models --database=sqlite:///db.sqlite3 migrate
```

이 모드는 간단한 사용 사례나 Application 설정 없이 빠르게 테스트할 때 유용합니다.

---

## 참고

- [Database ORM](./database-orm.md) - ORM 사용법
- [Task System](./task-system.md) - 태스크 시스템
- [Dependency Injection](./dependency-injection.md) - DI 설정
