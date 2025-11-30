"""
Bloom DB ORM 예제
- Spring 스타일 Entity
- CRUD Repository
- QueryDSL 스타일 쿼리
- 더티 체킹
- Django 스타일 마이그레이션
"""

from bloom.db import (
    Entity,
    Column,
    PrimaryKey,
    ForeignKey,
    IntegerColumn,
    StringColumn,
    BooleanColumn,
    DateTimeColumn,
    CrudRepository,
    Query,
    create,
)
from bloom.db.dialect import SQLiteDialect
from bloom.db.session import SessionFactory
from bloom.application import Application
from bloom.core.decorators import Component, Factory
from datetime import datetime


# =============================================================================
# Application 설정
# =============================================================================


@Component
class DatabaseConfig:
    """데이터베이스 설정"""

    @Factory
    def session_factory(self) -> SessionFactory:
        """SessionFactory DI 등록"""
        dialect = SQLiteDialect()
        return SessionFactory("db.sqlite3", dialect)


# Application 인스턴스
app = Application("orm_example")
app.scan(DatabaseConfig)


# =============================================================================
# 1. Entity 정의 (Spring 스타일 + Field Injection)
# =============================================================================


@Entity(table_name="users")
class User:
    """사용자 엔티티"""

    id = PrimaryKey[int](auto_increment=True)
    name = StringColumn(max_length=100, nullable=False)
    email = StringColumn(max_length=255, unique=True)
    age = IntegerColumn(default=0)
    is_active = BooleanColumn(default=True)
    created_at = DateTimeColumn(default=datetime.now)


@Entity(table_name="posts")
class Post:
    """게시글 엔티티"""

    id = PrimaryKey[int](auto_increment=True)
    title = StringColumn(max_length=200, nullable=False)
    content = StringColumn(nullable=True)
    user_id = ForeignKey[int]("users.id", on_delete="CASCADE")
    published = BooleanColumn(default=False)
    created_at = DateTimeColumn(default=datetime.now)


@Entity(table_name="comments")
class Comment:
    """댓글 엔티티"""

    id = PrimaryKey[int](auto_increment=True)
    content = StringColumn(max_length=1000, nullable=False)
    post_id = ForeignKey[int]("posts.id", on_delete="CASCADE")
    user_id = ForeignKey[int]("users.id", on_delete="SET NULL")
    created_at = DateTimeColumn(default=datetime.now)


# =============================================================================
# 2. Repository 정의 (Spring Data JPA 스타일)
# =============================================================================


class UserRepository(CrudRepository[User, int]):
    """사용자 리포지토리"""

    def find_by_email(self, email: str) -> User | None:
        """이메일로 사용자 찾기"""
        return self.find_one(User.email == email)  # type: ignore

    def find_active_users(self) -> list[User]:
        """활성 사용자 목록"""
        return self.find_all(User.is_active == True)  # type: ignore

    def find_by_age_range(self, min_age: int, max_age: int) -> list[User]:
        """나이 범위로 사용자 찾기"""
        return self.find_all(
            (User.age >= min_age) & (User.age <= max_age)  # type: ignore
        )


class PostRepository(CrudRepository[Post, int]):
    """게시글 리포지토리"""

    def find_by_user(self, user_id: int) -> list[Post]:
        """사용자별 게시글 찾기"""
        return self.find_all(Post.user_id == user_id)  # type: ignore

    def find_published(self) -> list[Post]:
        """발행된 게시글 목록"""
        return self.find_all(Post.published == True)  # type: ignore


# =============================================================================
# 3. QueryDSL 스타일 쿼리 빌더 예제
# =============================================================================


def query_builder_examples():
    """Query 사용 예제"""
    print("\n=== QueryDSL 스타일 쿼리 빌더 ===")

    # 기본 SELECT
    query1 = (
        Query(User)
        .filter(User.is_active == True)  # type: ignore
        .order_by(User.name)  # type: ignore
        .limit(10)
    )
    sql1, params1 = query1.build()
    print(f"\n기본 조회:\n{sql1}")
    print(f"파라미터: {params1}")

    # 복합 조건
    query2 = (
        Query(User)
        .select(User.id, User.name, User.email)  # type: ignore
        .filter(
            (User.age >= 20)  # type: ignore
            & (User.age <= 30)  # type: ignore
            & (User.is_active == True)  # type: ignore
        )
        .order_by(User.age.desc())  # type: ignore
    )
    sql2, params2 = query2.build()
    print(f"\n복합 조건 조회:\n{sql2}")
    print(f"파라미터: {params2}")

    # OR 조건
    query3 = Query(User).filter(
        (User.name == "Alice")  # type: ignore
        | (User.name == "Bob")  # type: ignore
    )
    sql3, params3 = query3.build()
    print(f"\nOR 조건 조회:\n{sql3}")
    print(f"파라미터: {params3}")

    # NOT 조건
    query4 = Query(User).filter(~(User.is_active == True))  # type: ignore
    sql4, params4 = query4.build()
    print(f"\nNOT 조건 조회:\n{sql4}")
    print(f"파라미터: {params4}")

    # filter_by 사용 (키워드 인자)
    query5 = Query(User).filter_by(name="Alice", age=25)
    sql5, params5 = query5.build()
    print(f"\nfilter_by 조회:\n{sql5}")
    print(f"파라미터: {params5}")


# =============================================================================
# 4. 더티 체킹 예제
# =============================================================================


def dirty_checking_examples():
    """더티 체킹 예제"""
    print("\n=== 더티 체킹 ===")

    # create() 헬퍼 함수 사용
    user = create(User, name="Alice", email="alice@example.com", age=25)

    tracker = user.__bloom_tracker__  # type: ignore

    print(f"\n생성 직후:")
    print(f"  user.name = {user.name}")
    print(f"  더티 필드: {tracker.get_dirty_fields()}")
    print(f"  상태: {tracker.state}")

    # 원래 값 저장 (세션에서 로드된 것처럼 시뮬레이션)
    tracker.mark_persisted()

    print(f"\n클린 마킹 후:")
    print(f"  더티 필드: {tracker.get_dirty_fields()}")
    print(f"  상태: {tracker.state}")

    # 필드 변경
    user.name = "Alice Smith"
    user.age = 26

    print(f"\n변경 후:")
    print(f"  user.name = {user.name}")
    print(f"  user.age = {user.age}")
    print(f"  더티 필드: {tracker.get_dirty_fields()}")
    print(f"  상태: {tracker.state}")
    print(f"  is_dirty: {tracker.is_dirty}")

    # 변경 정보 확인
    print(f"\n변경 정보:")
    for change in tracker.get_changes():
        print(f"  {change.field_name}: {change.old_value} -> {change.new_value}")

    # 필드 주입 방식으로 생성
    print("\n\n--- 필드 주입 방식 ---")
    user2 = User()
    user2.name = "Bob"
    user2.email = "bob@example.com"
    user2.age = 30

    print(f"user2.name = {user2.name}")
    print(f"user2.email = {user2.email}")
    print(f"user2.age = {user2.age}")


# =============================================================================
# 5. 마이그레이션 예제
# =============================================================================


def migration_examples():
    """마이그레이션 시스템 예제"""
    print("\n=== Django 스타일 마이그레이션 ===")

    from bloom.db.entity import get_entity_meta

    # 엔티티 메타데이터에서 테이블 생성 SQL 생성
    print("\n--- 테이블 생성 SQL 생성 ---")

    dialect = SQLiteDialect()

    # User 테이블
    user_meta = get_entity_meta(User)
    if user_meta:
        user_sql = dialect.create_table_sql(user_meta)
        print(f"\nUser 테이블:\n{user_sql}")

    # Post 테이블
    post_meta = get_entity_meta(Post)
    if post_meta:
        post_sql = dialect.create_table_sql(post_meta)
        print(f"\nPost 테이블:\n{post_sql}")


# =============================================================================
# 6. Session 예제
# =============================================================================


def session_examples():
    """Session 패턴 예제 (개념 설명)"""
    print("\n=== Session (Unit of Work) 패턴 ===")

    print(
        """
Session은 Unit of Work 패턴을 구현합니다:

1. 엔티티 추가 (INSERT 예약)
   session.add(user)

2. 변경 추적 (Dirty Checking)
   user.name = "new name"  # 자동으로 dirty로 마킹

3. flush - 변경사항 DB 반영
   session.flush()

4. commit - 트랜잭션 커밋
   session.commit()

5. 쿼리
   users = session.query(User).filter(User.age > 18).all()
"""
    )

    # 개념 데모 - create 함수 사용
    user = create(User, name="Alice", email="alice@example.com", age=25)
    print(f"생성된 엔티티: {user}")
    print(f"  name: {user.name}")
    print(f"  email: {user.email}")


# =============================================================================
# 7. Repository 예제
# =============================================================================


def repository_examples():
    """Repository 패턴 예제 (쿼리 생성 데모)"""
    print("\n=== CRUD Repository 패턴 ===")

    print(
        """
Repository는 데이터 접근을 추상화합니다:

1. 기본 CRUD 메서드
   - save(entity) - INSERT/UPDATE
   - find_by_id(id) - PK로 조회
   - find_all() - 전체 조회
   - delete(entity) - 삭제

2. 커스텀 쿼리 메서드
   - find_by_email(email)
   - find_active_users()
   - find_by_age_range(min, max)
"""
    )

    # 쿼리 빌더로 생성되는 SQL 데모
    print("--- 쿼리 빌더로 생성되는 SQL ---")

    # find_by_email
    query1 = Query(User).filter(User.email == "alice@example.com").limit(1)  # type: ignore
    sql1, params1 = query1.build()
    print(f"\nfind_by_email SQL:\n  {sql1}")
    print(f"  params: {params1}")

    # find_active_users
    query2 = Query(User).filter(User.is_active == True)  # type: ignore
    sql2, params2 = query2.build()
    print(f"\nfind_active_users SQL:\n  {sql2}")
    print(f"  params: {params2}")

    # find_by_age_range
    query3 = Query(User).filter((User.age >= 20) & (User.age <= 30))  # type: ignore
    sql3, params3 = query3.build()
    print(f"\nfind_by_age_range SQL:\n  {sql3}")
    print(f"  params: {params3}")


# =============================================================================
# 메인 실행
# =============================================================================

if __name__ == "__main__":
    from bloom.db.entity import get_entity_meta

    print("=" * 60)
    print("Bloom DB ORM 예제")
    print("=" * 60)

    # 엔티티 메타데이터 확인
    print("\n=== 엔티티 메타데이터 ===")

    user_meta = get_entity_meta(User)
    if user_meta:
        print(f"\nUser:")
        print(f"  테이블: {user_meta.table_name}")
        print(f"  컬럼: {user_meta.column_names}")
        print(f"  PK: {user_meta.primary_key}")

    post_meta = get_entity_meta(Post)
    if post_meta:
        print(f"\nPost:")
        print(f"  테이블: {post_meta.table_name}")
        print(f"  컬럼: {post_meta.column_names}")
        print(f"  PK: {post_meta.primary_key}")

    # 각 예제 실행
    query_builder_examples()
    dirty_checking_examples()
    migration_examples()
    session_examples()
    repository_examples()

    print("\n" + "=" * 60)
    print("예제 완료!")
    print("=" * 60)
