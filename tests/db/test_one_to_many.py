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
    Query,
    create,
)
from bloom.db.columns import OneToManyQuery


# =============================================================================
# 테스트용 엔티티
# =============================================================================


@Entity(table_name="authors")
class Author:
    id = PrimaryKey[int](auto_increment=True)
    name = StringColumn(max_length=100)

    # 역참조 관계
    books: "OneToMany[Book]" = OneToMany("Book", foreign_key="author_id")


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

    def test_instance_level_access_returns_query(self):
        """인스턴스 레벨 접근 시 OneToManyQuery 반환"""
        author = create(Author, id=1, name="Test Author")
        author.__bloom_tracker__.mark_persisted()

        # 인스턴스 접근 시 OneToManyQuery
        query = author.books
        assert isinstance(query, OneToManyQuery)

    def test_instance_without_pk_raises_error(self):
        """PK 없이 접근하면 에러"""
        author = create(Author, name="Test Author")
        # id=None 상태

        with pytest.raises(ValueError, match="Cannot access OneToMany relation"):
            _ = author.books

    def test_relations_registered(self):
        """__bloom_relations__에 등록됨"""
        assert hasattr(Author, "__bloom_relations__")
        assert "books" in Author.__bloom_relations__
        assert Author.__bloom_relations__["books"] is Author.__dict__["books"]


class TestOneToManyQuery:
    """OneToManyQuery 테스트"""

    @pytest.fixture
    def author_with_id(self):
        """ID가 있는 Author 인스턴스"""
        author = create(Author, id=42, name="Jane Doe")
        author.__bloom_tracker__.mark_persisted()
        return author

    def test_query_repr(self, author_with_id):
        """쿼리 repr"""
        query = author_with_id.books
        assert "OneToManyQuery" in repr(query)
        assert "Book" in repr(query)
        assert "author_id=42" in repr(query)

    def test_filter_chainable(self, author_with_id):
        """filter 체이닝"""
        query = author_with_id.books.filter(Book.published == True)  # type: ignore
        assert isinstance(query, OneToManyQuery)

    def test_order_by_chainable(self, author_with_id):
        """order_by 체이닝"""
        query = author_with_id.books.order_by(Book.year.desc())  # type: ignore
        assert isinstance(query, OneToManyQuery)

    def test_limit_chainable(self, author_with_id):
        """limit 체이닝"""
        query = author_with_id.books.limit(10)
        assert isinstance(query, OneToManyQuery)

    def test_offset_chainable(self, author_with_id):
        """offset 체이닝"""
        query = author_with_id.books.offset(5)
        assert isinstance(query, OneToManyQuery)

    def test_chaining_immutable(self, author_with_id):
        """체이닝이 불변성 유지 (새 객체 반환)"""
        query1 = author_with_id.books
        query2 = query1.filter(Book.published == True)  # type: ignore
        query3 = query2.limit(10)

        # 모두 다른 객체
        assert query1 is not query2
        assert query2 is not query3

    def test_build_query_generates_correct_sql(self, author_with_id):
        """내부 Query 빌드 시 올바른 SQL 생성"""
        query = (
            author_with_id.books.filter(Book.published == True)  # type: ignore
            .order_by(Book.year.desc())  # type: ignore
            .limit(5)
        )

        internal_query = query._build_query()
        sql, params = internal_query.build()

        # FK 조건 포함
        assert "author_id" in sql
        assert params.get("w_0_0_author_id") == 42

        # 추가 필터 포함
        assert "published" in sql
        assert params.get("w_0_1_published") == True

        # ORDER BY 포함
        assert "ORDER BY" in sql
        assert "year" in sql

        # LIMIT 포함
        assert "LIMIT 5" in sql


class TestOneToManyStringTarget:
    """문자열 타겟 resolve 테스트"""

    def test_string_target_same_module(self):
        """같은 모듈의 문자열 타겟 resolve"""
        author = create(Author, id=1, name="Test")
        author.__bloom_tracker__.mark_persisted()

        # "Book" 문자열이 실제 Book 클래스로 resolve됨
        query = author.books
        assert query._target_cls is Book

    def test_dotted_string_target(self):
        """모듈.클래스 형식의 문자열 타겟"""

        @Entity(table_name="publishers")
        class Publisher:
            id = PrimaryKey[int](auto_increment=True)
            # 전체 경로로 지정
            authors: "OneToMany[Author]" = OneToMany(
                "tests.db.test_one_to_many.Author", foreign_key="publisher_id"
            )

        publisher = create(Publisher, id=1)
        publisher.__bloom_tracker__.mark_persisted()

        # resolve 시도
        query = publisher.authors
        assert query._target_cls is Author
