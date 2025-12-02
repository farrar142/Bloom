# Database ORM

Bloom의 데이터베이스 ORM은 Spring JPA와 Django ORM의 장점을 결합한 Python 네이티브 ORM입니다.

## 핵심 특징

- **Entity 데코레이터**: Spring JPA 스타일의 엔티티 정의
- **QueryDSL 스타일 쿼리**: 타입 안전한 쿼리 빌더
- **Dirty Tracking**: 변경된 필드만 UPDATE
- **Django 스타일 마이그레이션**: 스키마 버전 관리
- **Unit of Work 패턴**: Session을 통한 트랜잭션 관리

## 빠른 시작

### 1. Application 설정

```python
# application.py
from bloom import Application
from bloom.core import Component, Factory
from bloom.db import SessionFactory
from bloom.db.backends import SQLiteBackend

application = Application("myapp")

@Component
class DatabaseConfig:
    @Factory
    def session_factory(self) -> SessionFactory:
        backend = SQLiteBackend("db.sqlite3")
        return SessionFactory(backend)
```

### 2. Entity 정의

```python
# models.py
from bloom.db import Entity, PrimaryKey, Column, ForeignKey, create

@Entity
class User:
    id: int = PrimaryKey(auto_increment=True)
    name: str = Column(max_length=100, nullable=False)
    email: str = Column(max_length=255, unique=True)
    age: int = Column(default=0)
    is_active: bool = Column(default=True)
    created_at: str = Column()

@Entity
class Post:
    id: int = PrimaryKey(auto_increment=True)
    title: str = Column(max_length=200, nullable=False)
    content: str = Column()
    user_id: int = ForeignKey("users.id", on_delete="CASCADE")
    published: bool = Column(default=False)
```

### 3. 마이그레이션 생성 및 적용

```bash
# 마이그레이션 생성
bloom db makemigrations --name create_users

# 마이그레이션 적용
bloom db migrate

# 마이그레이션 상태 확인
bloom db showmigrations
```

### 4. CRUD 작업

```python
from bloom.db import SessionFactory, create

# DI에서 SessionFactory 주입받기
@Component
class UserService:
    def __init__(self, session_factory: SessionFactory):
        self.session_factory = session_factory

    def create_user(self, name: str, email: str) -> User:
        with self.session_factory.session() as session:
            user = create(User, name=name, email=email)
            session.add(user)
            session.commit()
            return user

    def get_user(self, user_id: int) -> User | None:
        with self.session_factory.session() as session:
            return session.query(User).filter(User.id == user_id).first()

    def update_user(self, user_id: int, **kwargs) -> User | None:
        with self.session_factory.session() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if user:
                for key, value in kwargs.items():
                    setattr(user, key, value)
                session.commit()
            return user

    def delete_user(self, user_id: int) -> bool:
        with self.session_factory.session() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if user:
                session.delete(user)
                session.commit()
                return True
            return False
```

## Entity 정의

### Column 타입

```python
from bloom.db import (
    Entity, PrimaryKey, Column, ForeignKey,
    IntegerColumn, StringColumn, BooleanColumn,
    DateTimeColumn, DecimalColumn, TextColumn, JSONColumn
)

@Entity
class Product:
    # 기본키
    id: int = PrimaryKey(auto_increment=True)

    # 문자열 (VARCHAR)
    name: str = Column(max_length=200, nullable=False)
    description: str = TextColumn()  # TEXT 타입

    # 숫자
    price: float = DecimalColumn(precision=10, scale=2)
    stock: int = IntegerColumn(default=0)

    # 불리언
    is_active: bool = BooleanColumn(default=True)

    # 날짜/시간
    created_at: str = DateTimeColumn()

    # JSON
    metadata: dict = JSONColumn()

    # 외래키
    category_id: int = ForeignKey(
        "categories.id",
        on_delete="CASCADE",
        on_update="CASCADE"
    )
```

### Column 옵션

| 옵션             | 설명              | 기본값 |
| ---------------- | ----------------- | ------ |
| `max_length`     | VARCHAR 최대 길이 | 255    |
| `nullable`       | NULL 허용 여부    | True   |
| `unique`         | 유니크 제약조건   | False  |
| `default`        | 기본값            | None   |
| `primary_key`    | 기본키 여부       | False  |
| `auto_increment` | 자동 증가 (PK용)  | False  |

### ForeignKey 옵션

```python
user_id: int = ForeignKey(
    "users.id",           # 참조 테이블.컬럼
    on_delete="CASCADE",  # CASCADE, SET NULL, RESTRICT, NO ACTION
    on_update="CASCADE",  # CASCADE, SET NULL, RESTRICT, NO ACTION
    nullable=True
)
```

### OneToMany 역참조 관계

`OneToMany`는 DB에 컬럼을 생성하지 않고 역참조 관계를 제공합니다. 순환 임포트 방지를 위해 문자열로 타겟 클래스를 지정할 수 있습니다.

```python
from bloom.db import Entity, PrimaryKey, ForeignKey, StringColumn, OneToMany, FetchType

@Entity(table_name="users")
class User:
    id = PrimaryKey[int](auto_increment=True)
    name = StringColumn(max_length=100)

    # 역참조 관계 - DB 컬럼 없음 (기본 LAZY)
    posts: "OneToMany[Post]" = OneToMany("Post", foreign_key="user_id")

@Entity(table_name="posts")
class Post:
    id = PrimaryKey[int](auto_increment=True)
    title = StringColumn(max_length=200)
    user_id = ForeignKey[int]("users.id")  # 실제 FK 컬럼
```

#### FetchType (Lazy vs Eager)

`OneToMany`는 `FetchType.LAZY`(기본값)와 `FetchType.EAGER`를 지원합니다:

```python
from bloom.db import OneToMany, FetchType

@Entity(table_name="users")
class User:
    id = PrimaryKey[int](auto_increment=True)
    name = StringColumn(max_length=100)

    # LAZY (기본값): 접근 시 쿼리 실행
    posts: "OneToMany[Post]" = OneToMany("Post", foreign_key="user_id")

    # EAGER: 부모 로드 시 함께 로드
    comments: "OneToMany[Comment]" = OneToMany(
        "Comment", 
        foreign_key="user_id", 
        fetch=FetchType.EAGER
    )
```

#### 사용 예시

`OneToMany` 접근 시 `list[T]`가 바로 반환됩니다. Session에서 엔티티를 조회하면 자동으로 Session이 바인딩됩니다:

```python
with session_factory.session() as session:
    # Session에서 조회한 엔티티는 Session이 자동 바인딩됨
    user = session.query(User).filter(User.id == 1).first()
    
    # posts 접근 시 자동으로 쿼리 실행 (LAZY)
    posts = user.posts  # list[Post] 반환
    
    for post in posts:
        print(post.title)
    
    # 두 번째 접근 시 캐시된 결과 반환 (추가 쿼리 없음)
    same_posts = user.posts
```

#### 문자열 타겟

순환 임포트를 방지하기 위해 문자열로 타겟을 지정할 수 있습니다:

```python
# 같은 모듈 내 클래스
posts: "OneToMany[Post]" = OneToMany("Post", foreign_key="user_id")

# 다른 모듈의 클래스
posts: "OneToMany[Post]" = OneToMany("myapp.models.Post", foreign_key="user_id")
```

## 쿼리 빌더 (QueryDSL 스타일)

### 기본 조회

```python
with session_factory.session() as session:
    # 전체 조회
    users = session.query(User).all()

    # 단일 조회
    user = session.query(User).filter(User.id == 1).first()

    # 조건 조회
    active_users = session.query(User).filter(
        User.is_active == True,
        User.age >= 18
    ).all()
````

### 비교 연산자

```python
# 동등 비교
User.name == "alice"
User.age != 30

# 크기 비교
User.age > 18
User.age >= 18
User.age < 65
User.age <= 65

# NULL 체크
User.email.is_null()
User.email.is_not_null()

# LIKE
User.name.like("%alice%")
User.name.startswith("al")
User.name.endswith("ice")
User.name.contains("lic")

# IN
User.id.in_([1, 2, 3])
User.status.not_in(["banned", "deleted"])

# BETWEEN
User.age.between(18, 65)
```

### 논리 연산자

```python
from bloom.db import and_, or_, not_

# AND (기본)
session.query(User).filter(
    User.is_active == True,
    User.age >= 18
)

# OR
session.query(User).filter(
    or_(
        User.name == "alice",
        User.name == "bob"
    )
)

# NOT
session.query(User).filter(
    not_(User.is_active == True)
)

# 복합 조건
session.query(User).filter(
    and_(
        User.is_active == True,
        or_(
            User.age >= 18,
            User.role == "admin"
        )
    )
)
```

### 정렬

```python
# 오름차순
session.query(User).order_by(User.name.asc()).all()

# 내림차순
session.query(User).order_by(User.created_at.desc()).all()

# 다중 정렬
session.query(User).order_by(
    User.is_active.desc(),
    User.name.asc()
).all()
```

### 페이지네이션

```python
# LIMIT / OFFSET
users = session.query(User)\
    .order_by(User.id)\
    .limit(10)\
    .offset(20)\
    .all()

# 개수
count = session.query(User).filter(User.is_active == True).count()
```

### 특정 컬럼만 조회

```python
# 특정 컬럼
names = session.query(User).select(User.name, User.email).all()

# 결과: [{"name": "alice", "email": "alice@example.com"}, ...]
```

## Session (Unit of Work)

### 기본 사용법

```python
with session_factory.session() as session:
    # 엔티티 추가
    user = create(User, name="alice", email="alice@example.com")
    session.add(user)

    # 변경 (자동 추적)
    user.name = "Alice"

    # 삭제
    session.delete(user)

    # 커밋 (with 블록 끝에서 자동 커밋)
    session.commit()  # 명시적 커밋도 가능
```

### Dirty Tracking

```python
with session_factory.session() as session:
    user = session.query(User).filter(User.id == 1).first()

    # 변경 추적
    user.name = "New Name"
    user.age = 30

    # commit 시 변경된 필드만 UPDATE
    # UPDATE users SET name = 'New Name', age = 30 WHERE id = 1
    session.commit()
```

### 트랜잭션

```python
try:
    with session_factory.session() as session:
        user1 = create(User, name="user1")
        session.add(user1)

        user2 = create(User, name="user2")
        session.add(user2)

        # 에러 발생 시 자동 롤백
        raise Exception("Something went wrong")
except Exception:
    # 롤백됨 - user1, user2 모두 저장되지 않음
    pass
```

## SessionFactory 설정

### SQLite

```python
from bloom.db import SessionFactory
from bloom.db.backends import SQLiteBackend

# 파일 기반
backend = SQLiteBackend("db.sqlite3")
session_factory = SessionFactory(backend)

# 메모리 DB
backend = SQLiteBackend(":memory:")
session_factory = SessionFactory(backend)
```

### PostgreSQL

```python
from bloom.db import SessionFactory
from bloom.db.backends import PostgreSQLBackend

backend = PostgreSQLBackend(
    host="localhost",
    port=5432,
    database="mydb",
    user="user",
    password="pass",
)
session_factory = SessionFactory(backend)

# 또는 URL 형식
backend = PostgreSQLBackend("postgresql://user:pass@localhost:5432/mydb")
session_factory = SessionFactory(backend)
```

### MySQL

```python
from bloom.db import SessionFactory
from bloom.db.backends import MySQLBackend

backend = MySQLBackend(
    host="localhost",
    port=3306,
    database="mydb",
    user="user",
    password="pass",
)
session_factory = SessionFactory(backend)
```

### DI 통합

```python
from bloom import Application
from bloom.core import Component, Factory
from bloom.db import SessionFactory
from bloom.db.backends import SQLiteBackend

application = Application("myapp")

@Component
class DatabaseConfig:
    @Factory
    def session_factory(self) -> SessionFactory:
        backend = SQLiteBackend("db.sqlite3")
        return SessionFactory(backend)

# 다른 컴포넌트에서 주입받기
@Component
class UserRepository:
    def __init__(self, session_factory: SessionFactory):
        self.session_factory = session_factory
```

## Repository 패턴

### CrudRepository

Repository는 동기와 비동기 메서드를 모두 지원합니다.

```python
from bloom.db import CrudRepository, Entity, PrimaryKey, Column

@Entity
class User:
    id: int = PrimaryKey(auto_increment=True)
    name: str = Column(max_length=100)

class UserRepository(CrudRepository[User, int]):
    pass
```

#### Session 설정

Repository는 `session`과 `async_session` 필드를 @Factory로 주입받아야 합니다:

```python
from bloom import Component
from bloom.core import Factory, Scope
from bloom.core.protocols import PrototypeMode
from bloom.db import Session, AsyncSession, SessionFactory

@Component
class DatabaseConfig:
    session_factory: SessionFactory

    @Factory
    @Scope(Scope.CALL, PrototypeMode.CALL_SCOPED)
    def session(self) -> Session:
        """동기 Session - 같은 요청 내 공유, 요청 끝나면 자동 close"""
        return self.session_factory.create()

    @Factory
    @Scope(Scope.CALL, PrototypeMode.CALL_SCOPED)
    async def async_session(self) -> AsyncSession:
        """비동기 AsyncSession - 같은 요청 내 공유, 요청 끝나면 자동 close"""
        return await self.session_factory.create_async()
```

#### 동기 메서드

```python
repo = UserRepository()

# Create
user = repo.save(create(User, name="alice"))

# Read
user = repo.find_by_id(1)
users = repo.find_all()
user = repo.find_one_by(name="alice")
users = repo.find_by(status="active")

# Update
user.name = "bob"
repo.save(user)

# Delete
repo.delete(user)
repo.delete_by_id(1)

# Utility
count = repo.count()
exists = repo.exists_by_id(1)
```

#### 비동기 메서드

```python
repo = UserRepository()

# Create
user = await repo.save_async(create(User, name="alice"))

# Read
user = await repo.find_by_id_async(1)
users = await repo.find_all_async()
user = await repo.find_one_by_async(name="alice")
users = await repo.find_by_async(status="active")

# Update
user.name = "bob"
await repo.save_async(user)

# Delete
await repo.delete_async(user)
await repo.delete_by_id_async(1)

# Utility
count = await repo.count_async()
exists = await repo.exists_by_id_async(1)
```

#### 전체 메서드 목록

| 동기 메서드              | 비동기 메서드                  | 설명                 |
| ------------------------ | ------------------------------ | -------------------- |
| `find_by_id(id)`         | `find_by_id_async(id)`         | ID로 조회            |
| `find_all()`             | `find_all_async()`             | 전체 조회            |
| `find_all_by_id(ids)`    | `find_all_by_id_async(ids)`    | 여러 ID로 조회       |
| `find_by(**kwargs)`      | `find_by_async(**kwargs)`      | 조건으로 조회        |
| `find_one_by(**kwargs)`  | `find_one_by_async(**kwargs)`  | 조건으로 단일 조회   |
| `find_page(page, size)`  | `find_page_async(page, size)`  | 페이지네이션         |
| `find_slice(off, limit)` | `find_slice_async(off, limit)` | 슬라이스 조회        |
| `save(entity)`           | `save_async(entity)`           | 저장 (INSERT/UPDATE) |
| `save_all(entities)`     | `save_all_async(entities)`     | 여러 엔티티 저장     |
| `delete(entity)`         | `delete_async(entity)`         | 삭제                 |
| `delete_by_id(id)`       | `delete_by_id_async(id)`       | ID로 삭제            |
| `delete_all(entities)`   | `delete_all_async(entities)`   | 여러 엔티티 삭제     |
| `delete_all_by_id(ids)`  | `delete_all_by_id_async(ids)`  | 여러 ID로 삭제       |
| `exists_by_id(id)`       | `exists_by_id_async(id)`       | 존재 여부            |
| `count()`                | `count_async()`                | 전체 개수            |

### 커스텀 Repository

```python
class UserRepository(CrudRepository[User, int]):
    # 동기 메서드
    def find_by_email(self, email: str) -> User | None:
        return self.find_one_by(email=email)

    def find_active_users(self) -> list[User]:
        return self.find_by(is_active=True)

    def find_by_age_range(self, min_age: int, max_age: int) -> list[User]:
        with self.session as session:
            return session.query(User).filter(
                User.age.between(min_age, max_age)
            ).all()

    # 비동기 메서드
    async def find_by_email_async(self, email: str) -> User | None:
        return await self.find_one_by_async(email=email)

    async def find_active_users_async(self) -> list[User]:
        return await self.find_by_async(is_active=True)
```

## 마이그레이션

### 마이그레이션 생성

```bash
# 변경 사항 감지하여 자동 생성
bloom db makemigrations

# 이름 지정
bloom db makemigrations --name add_email_to_users

# 빈 마이그레이션 생성
bloom db makemigrations --empty --name custom_migration
```

### 마이그레이션 적용

```bash
# 모든 마이그레이션 적용
bloom db migrate

# 특정 마이그레이션까지 적용
bloom db migrate --target 0003_add_email

# Fake 적용 (기록만)
bloom db migrate --fake
```

### 마이그레이션 상태 확인

```bash
bloom db showmigrations

# 출력:
# Migrations:
#   [X] 0001_initial
#   [X] 0002_add_posts
#   [ ] 0003_add_comments
```

### SQL 미리보기

```bash
bloom db sqlmigrate 0001_initial

# 출력:
# -- SQL for migration: 0001_initial
# CREATE TABLE users (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     name VARCHAR(100) NOT NULL,
#     email VARCHAR(255) UNIQUE,
#     ...
# );
```

### 마이그레이션 파일 구조

```python
# migrations/0001_initial.py
from bloom.db.migrations import (
    Migration,
    CreateTable,
    AddColumn,
    CreateIndex,
)

migration = Migration(
    name="0001_initial",
    dependencies=[],
    operations=[
        CreateTable(
            "users",
            columns=[
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("name", "VARCHAR(100) NOT NULL"),
                ("email", "VARCHAR(255) UNIQUE"),
            ],
        ),
        CreateIndex("users", "idx_users_email", ["email"], unique=True),
    ],
)
```

## Dialect (SQL 방언)

### 지원 Dialect

| Dialect             | 상태    | 설명           |
| ------------------- | ------- | -------------- |
| `SQLiteDialect`     | ✅ 완료 | SQLite 3       |
| `PostgreSQLDialect` | 🚧 예정 | PostgreSQL 12+ |
| `MySQLDialect`      | 🚧 예정 | MySQL 8+       |

### 커스텀 Dialect

```python
from bloom.db.dialect import Dialect

class CustomDialect(Dialect):
    name = "custom"

    def get_type_mapping(self) -> dict[str, str]:
        return {
            "int": "INTEGER",
            "str": "VARCHAR",
            "bool": "BOOLEAN",
            "float": "DECIMAL",
        }

    def get_placeholder(self) -> str:
        return "%s"  # 또는 "?" 또는 ":name"
```

## 전체 예제

```python
# application.py
from bloom import Application
from bloom.core import Component, Factory
from bloom.db import (
    Entity, PrimaryKey, Column, ForeignKey,
    SessionFactory, CrudRepository, create
)
from bloom.db.backends import SQLiteBackend

application = Application("blog")

# Entity 정의
@Entity
class User:
    id: int = PrimaryKey(auto_increment=True)
    name: str = Column(max_length=100, nullable=False)
    email: str = Column(max_length=255, unique=True)

@Entity
class Post:
    id: int = PrimaryKey(auto_increment=True)
    title: str = Column(max_length=200, nullable=False)
    content: str = Column()
    user_id: int = ForeignKey("users.id", on_delete="CASCADE")

# Repository
class UserRepository(CrudRepository[User, int]):
    def find_by_email(self, email: str) -> User | None:
        with self.session_factory.session() as session:
            return session.query(User).filter(User.email == email).first()

class PostRepository(CrudRepository[Post, int]):
    def find_by_user(self, user_id: int) -> list[Post]:
        with self.session_factory.session() as session:
            return session.query(Post).filter(Post.user_id == user_id).all()

# DI 설정
@Component
class DatabaseConfig:
    @Factory
    def session_factory(self) -> SessionFactory:
        backend = SQLiteBackend("blog.sqlite3")
        return SessionFactory(backend)

@Component
class BlogService:
    def __init__(
        self,
        user_repo: UserRepository,
        post_repo: PostRepository
    ):
        self.user_repo = user_repo
        self.post_repo = post_repo

    def create_post(self, user_email: str, title: str, content: str) -> Post:
        user = self.user_repo.find_by_email(user_email)
        if not user:
            raise ValueError(f"User not found: {user_email}")

        post = create(Post, title=title, content=content, user_id=user.id)
        return self.post_repo.save(post)

# 실행
if __name__ == "__main__":
    application.ready()

    blog_service = application.get(BlogService)
    post = blog_service.create_post(
        "alice@example.com",
        "Hello World",
        "My first post!"
    )
    print(f"Created post: {post.title}")
```

## 참고

- [CLI Reference](./cli-reference.md) - 명령줄 인터페이스
- [Dependency Injection](./dependency-injection.md) - DI 통합
- [Testing](./testing-testcase.md) - 테스트 가이드
