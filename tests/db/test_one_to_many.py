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
    author_id = ForeignKey[int]("authors.id")
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
