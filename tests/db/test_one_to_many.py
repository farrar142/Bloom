"""OneToMany 관계 디스크립터 테스트"""

import pytest
from bloom.db import (
    Entity,
    PrimaryKey,
    ForeignKey,
    IntegerColumn,
    StringColumn,
    BooleanColumn,
    OneToMany,
    FetchType,
    Query,
    create,
)


# =============================================================================
# 테스트용 엔티티
# =============================================================================


@Entity(table_name="authors")
class Author:
    id = PrimaryKey[int](auto_increment=True)
    name = StringColumn(max_length=100)

    # 역참조 관계 (기본 LAZY)
    books: "OneToMany[Book]" = OneToMany("Book", foreign_key="author_id")


@Entity(table_name="eager_authors")
class EagerAuthor:
    id = PrimaryKey[int](auto_increment=True)
    name = StringColumn(max_length=100)

    # Eager 로딩
    books: "OneToMany[Book]" = OneToMany(
        "Book", foreign_key="author_id", fetch=FetchType.EAGER
    )


@Entity(table_name="books")
class Book:
    id = PrimaryKey[int](auto_increment=True)
    title = StringColumn(max_length=200)
    # db_name="author_id" 명시적 지정 (OneToMany foreign_key와 일치)
    author_id = ForeignKey[int]("authors.id", db_name="author_id")
    published = BooleanColumn(default=False)
    year = IntegerColumn(default=2024)


# =============================================================================
# 테스트
# =============================================================================


class TestOneToManyDescriptor:
    """OneToMany 디스크립터 테스트"""

    def test_class_level_access_returns_descriptor(self):
        """클래스 레벨 접근 시 디스크립터 반환"""
        # OneToMany 인스턴스 자체가 반환됨
        assert isinstance(Author.books, OneToMany)

    def test_instance_without_pk_raises_error(self):
        """PK 없이 접근하면 에러"""
        author = create(Author, name="Test Author")
        # id=None 상태

        with pytest.raises(ValueError, match="Cannot access OneToMany relation"):
            _ = author.books

    def test_instance_without_session_raises_error(self):
        """Session 없이 lazy 접근하면 에러"""
        author = create(Author, id=1, name="Test Author")
        author.__bloom_tracker__.mark_persisted()

        with pytest.raises(ValueError, match="has no bound session"):
            _ = author.books

    def test_relations_registered(self):
        """__bloom_relations__에 등록됨"""
        assert hasattr(Author, "__bloom_relations__")
        assert "books" in Author.__bloom_relations__
        assert Author.__bloom_relations__["books"] is Author.__dict__["books"]


class TestFetchType:
    """FetchType (Lazy/Eager) 테스트"""

    def test_default_is_lazy(self):
        """기본값은 LAZY"""
        descriptor = Author.__dict__["books"]
        assert descriptor.fetch == FetchType.LAZY
        assert descriptor.is_lazy is True
        assert descriptor.is_eager is False

    def test_eager_fetch_type(self):
        """EAGER 설정"""
        descriptor = EagerAuthor.__dict__["books"]
        assert descriptor.fetch == FetchType.EAGER
        assert descriptor.is_lazy is False
        assert descriptor.is_eager is True

    def test_eager_returns_empty_list_without_loaded_data(self):
        """EAGER 모드는 로드되지 않은 경우 빈 list 반환"""
        author = create(EagerAuthor, id=1, name="Test")
        author.__bloom_tracker__.mark_persisted()

        result = author.books
        assert isinstance(result, list)
        assert result == []

    def test_set_loaded_data(self):
        """로딩된 데이터 설정"""
        author = create(EagerAuthor, id=1, name="Test")
        author.__bloom_tracker__.mark_persisted()

        # Session에서 데이터 설정
        descriptor = EagerAuthor.__dict__["books"]
        book1 = create(Book, id=1, title="Book 1", author_id=1)
        book2 = create(Book, id=2, title="Book 2", author_id=1)
        descriptor.set_loaded_data(author, [book1, book2])

        # 이제 리스트가 반환됨
        result = author.books
        assert len(result) == 2
        assert result[0].title == "Book 1"
        assert result[1].title == "Book 2"

    def test_clear_cache(self):
        """캐시 클리어"""
        author = create(EagerAuthor, id=1, name="Test")
        author.__bloom_tracker__.mark_persisted()

        descriptor = EagerAuthor.__dict__["books"]
        book = create(Book, id=1, title="Book 1", author_id=1)
        descriptor.set_loaded_data(author, [book])

        assert len(author.books) == 1

        # 캐시 클리어
        descriptor.clear_cache(author)

        # 다시 빈 리스트 (eager 모드)
        assert author.books == []

    def test_repr_includes_fetch_type(self):
        """repr에 fetch 타입 포함"""
        lazy_repr = repr(Author.__dict__["books"])
        assert "lazy" in lazy_repr

        eager_repr = repr(EagerAuthor.__dict__["books"])
        assert "eager" in eager_repr


class TestOneToManyStringTarget:
    """문자열 타겟 resolve 테스트"""

    def test_string_target_same_module(self):
        """같은 모듈의 문자열 타겟 resolve"""
        descriptor = Author.__dict__["books"]
        resolved = descriptor._resolve_target()
        assert resolved is Book

    def test_dotted_string_target(self):
        """모듈.클래스 형식의 문자열 타겟"""

        @Entity(table_name="publishers")
        class Publisher:
            id = PrimaryKey[int](auto_increment=True)
            # 전체 경로로 지정
            authors: "OneToMany[Author]" = OneToMany(
                "tests.db.test_one_to_many.Author", foreign_key="publisher_id"
            )

        descriptor = Publisher.__dict__["authors"]
        resolved = descriptor._resolve_target()
        assert resolved is Author


class TestForeignKeyInference:
    """foreign_key 자동 추론 테스트"""

    def test_explicit_foreign_key(self):
        """명시적 foreign_key 지정"""
        descriptor = Author.__dict__["books"]
        assert descriptor.foreign_key == "author_id"

    def test_infer_from_table_and_pk(self):
        """테이블명_pk필드명 형태로 자동 추론"""

        @Entity(table_name="users")
        class User:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=100)
            # foreign_key 생략 - users_id로 자동 추론
            posts: "OneToMany[Post]" = OneToMany("Post")

        @Entity(table_name="posts")
        class Post:
            id = PrimaryKey[int](auto_increment=True)
            title = StringColumn(max_length=200)
            users_id = ForeignKey[int]("users.id")

        descriptor = User.__dict__["posts"]
        assert descriptor.foreign_key == "users_id"

    def test_infer_with_custom_pk_db_name(self):
        """PK에 name 지정된 경우 해당 db_name으로 추론"""

        @Entity(table_name="categories")
        class Category:
            id = PrimaryKey[int](name="category_pk")  # DB 컬럼명: category_pk
            name = StringColumn(max_length=100)
            # foreign_key 생략 - categories_category_pk로 자동 추론
            items: "OneToMany[Item]" = OneToMany("Item")

        @Entity(table_name="items")
        class Item:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=200)
            categories_category_pk = ForeignKey[int]("categories.id")

        descriptor = Category.__dict__["items"]
        assert descriptor.foreign_key == "categories_category_pk"

    def test_infer_with_custom_pk_field_name(self):
        """PK 필드명이 id가 아닌 경우"""

        @Entity(table_name="departments")
        class Department:
            dept_id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=100)
            # foreign_key 생략 - departments_dept_id로 자동 추론
            employees: "OneToMany[Employee]" = OneToMany("Employee")

        @Entity(table_name="employees")
        class Employee:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=100)
            departments_dept_id = ForeignKey[int]("departments.dept_id")

        descriptor = Department.__dict__["employees"]
        assert descriptor.foreign_key == "departments_dept_id"

    def test_infer_without_tablename(self):
        """__tablename__ 없으면 클래스명 소문자 사용"""

        @Entity
        class Team:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=100)
            members: "OneToMany[Member]" = OneToMany("Member")

        @Entity
        class Member:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=100)
            team_id = ForeignKey[int]("team.id")

        descriptor = Team.__dict__["members"]
        # Team -> team (소문자) + id
        assert descriptor.foreign_key == "team_id"

    def test_infer_with_weird_pk_db_name(self):
        """PK의 db_name이 완전히 다른 이름인 경우"""

        @Entity(table_name="accounts")
        class Account:
            id = PrimaryKey[int](
                name="something_weird_pk"
            )  # DB 컬럼명: something_weird_pk
            email = StringColumn(max_length=200)
            # foreign_key 생략 - accounts_something_weird_pk로 자동 추론
            orders: "OneToMany[Order]" = OneToMany("Order")

        @Entity(table_name="orders")
        class Order:
            id = PrimaryKey[int](auto_increment=True)
            amount = IntegerColumn(default=0)
            accounts_something_weird_pk = ForeignKey[int]("accounts.id")

        descriptor = Account.__dict__["orders"]
        assert descriptor.foreign_key == "accounts_something_weird_pk"

    def test_infer_with_db_name_param(self):
        """PK에 db_name 파라미터 사용 시"""

        @Entity(table_name="companies")
        class Company:
            id = PrimaryKey[int](db_name="company_uuid")  # db_name 직접 사용
            name = StringColumn(max_length=100)
            branches: "OneToMany[Branch]" = OneToMany("Branch")

        @Entity(table_name="branches")
        class Branch:
            id = PrimaryKey[int](auto_increment=True)
            location = StringColumn(max_length=200)
            companies_company_uuid = ForeignKey[int]("companies.id")

        descriptor = Company.__dict__["branches"]
        assert descriptor.foreign_key == "companies_company_uuid"

    def test_infer_with_both_name_and_db_name(self):
        """name과 db_name 둘 다 지정된 경우 db_name 우선"""

        @Entity(table_name="projects")
        class Project:
            # db_name이 우선됨
            id = PrimaryKey[int](name="proj_id", db_name="project_identifier")
            title = StringColumn(max_length=100)
            tasks: "OneToMany[Task]" = OneToMany("Task")

        @Entity(table_name="tasks")
        class Task:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=100)
            projects_project_identifier = ForeignKey[int]("projects.id")

        descriptor = Project.__dict__["tasks"]
        assert descriptor.foreign_key == "projects_project_identifier"

    def test_infer_complex_table_name_and_pk(self):
        """복잡한 테이블명과 PK 조합"""

        @Entity(table_name="user_profiles")
        class UserProfile:
            profile_uuid = PrimaryKey[int](name="profile_unique_id")
            bio = StringColumn(max_length=500)
            photos: "OneToMany[Photo]" = OneToMany("Photo")

        @Entity(table_name="photos")
        class Photo:
            id = PrimaryKey[int](auto_increment=True)
            url = StringColumn(max_length=500)
            user_profiles_profile_unique_id = ForeignKey[int](
                "user_profiles.profile_uuid"
            )

        descriptor = UserProfile.__dict__["photos"]
        # user_profiles (테이블명) + profile_unique_id (PK의 db_name)
        assert descriptor.foreign_key == "user_profiles_profile_unique_id"


# =============================================================================
# Session 통합 테스트
# =============================================================================


class TestOneToManyWithSession:
    """실제 Session과 함께 OneToMany 테스트"""

    @pytest.fixture
    def session(self):
        """인메모리 SQLite 세션"""
        from bloom.db import SessionFactory
        from bloom.db.backends import SQLiteBackend

        backend = SQLiteBackend(":memory:")
        factory = SessionFactory(backend)

        with factory.session() as session:
            # 테이블 생성
            session._connection.execute(
                """
                CREATE TABLE authors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(100)
                )
            """
            )
            session._connection.execute(
                """
                CREATE TABLE eager_authors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(100)
                )
            """
            )
            session._connection.execute(
                """
                CREATE TABLE books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title VARCHAR(200),
                    author_id INTEGER,
                    published BOOLEAN DEFAULT 0,
                    year INTEGER DEFAULT 2024
                )
            """
            )
            yield session

    def test_lazy_loading_with_session(self, session):
        """LAZY 모드 - Session으로 조회 후 관계 접근"""
        # 데이터 추가
        session._connection.execute(
            "INSERT INTO authors (name) VALUES (:name)", {"name": "Jane Doe"}
        )
        session._connection.execute(
            "INSERT INTO books (title, author_id) VALUES (:title, :author_id)",
            {"title": "Book 1", "author_id": 1},
        )
        session._connection.execute(
            "INSERT INTO books (title, author_id) VALUES (:title, :author_id)",
            {"title": "Book 2", "author_id": 1},
        )
        session.commit()

        # Session으로 조회
        author = session.query(Author).filter(Author.id == 1).first()
        assert author is not None
        assert author.name == "Jane Doe"

        # Session이 바인딩되어 있어야 함
        assert hasattr(author, "__bloom_session__")
        assert author.__bloom_session__ is session

        # Lazy 로딩 - 접근 시 쿼리 실행
        books = author.books
        assert isinstance(books, list)
        assert len(books) == 2
        assert books[0].title in ["Book 1", "Book 2"]

    def test_eager_loading_with_session(self, session):
        """EAGER 모드 - 부모 조회 시 자식도 함께 로드"""
        # 데이터 추가
        session._connection.execute(
            "INSERT INTO eager_authors (name) VALUES (:name)", {"name": "John Smith"}
        )
        session._connection.execute(
            "INSERT INTO books (title, author_id) VALUES (:title, :author_id)",
            {"title": "Eager Book 1", "author_id": 1},
        )
        session._connection.execute(
            "INSERT INTO books (title, author_id) VALUES (:title, :author_id)",
            {"title": "Eager Book 2", "author_id": 1},
        )
        session.commit()

        # Session으로 조회 - Eager 로딩으로 자식도 함께 로드됨
        author = session.query(EagerAuthor).filter(EagerAuthor.id == 1).first()
        assert author is not None

        # 이미 로드되어 있어야 함 (추가 쿼리 없이)
        books = author.books
        assert isinstance(books, list)
        assert len(books) == 2

    def test_lazy_caching(self, session):
        """LAZY 모드 - 캐싱 동작 확인"""
        session._connection.execute(
            "INSERT INTO authors (name) VALUES (:name)", {"name": "Cache Test"}
        )
        session._connection.execute(
            "INSERT INTO books (title, author_id) VALUES (:title, :author_id)",
            {"title": "Cached Book", "author_id": 1},
        )
        session.commit()

        author = session.query(Author).filter(Author.id == 1).first()

        # 첫 접근 - 쿼리 실행
        books1 = author.books
        # 두 번째 접근 - 캐시 반환
        books2 = author.books

        # 같은 리스트 객체여야 함
        assert books1 is books2
