"""ForeignKey 디스크립터 테스트"""

import pytest
from bloom.db import (
    Entity,
    PrimaryKey,
    ForeignKey,
    IntegerColumn,
    StringColumn,
)


# =============================================================================
# ForeignKey db_name 자동 추론 테스트
# =============================================================================


class TestForeignKeyDbNameInference:
    """ForeignKey db_name 자동 추론 테스트"""

    def test_explicit_db_name(self):
        """명시적 db_name 지정"""

        @Entity(table_name="users")
        class User:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=100)

        @Entity(table_name="posts")
        class Post:
            id = PrimaryKey[int](auto_increment=True)
            user_id = ForeignKey[int]("users.id", db_name="custom_user_id")

        fk = Post.__bloom_columns__["user_id"]
        assert fk.db_name == "custom_user_id"

    def test_explicit_name_param(self):
        """명시적 name 파라미터 지정"""

        @Entity(table_name="users")
        class User:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=100)

        @Entity(table_name="posts")
        class Post:
            id = PrimaryKey[int](auto_increment=True)
            user_id = ForeignKey[int]("users.id", name="user_fk")

        fk = Post.__bloom_columns__["user_id"]
        assert fk.db_name == "user_fk"

    def test_infer_from_class_reference(self):
        """클래스 참조로 자동 추론"""

        @Entity(table_name="users")
        class User:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=100)

        @Entity(table_name="posts")
        class Post:
            id = PrimaryKey[int](auto_increment=True)
            title = StringColumn(max_length=200)
            # 자동 추론: User(users 테이블, id PK) → users_id
            user = ForeignKey[int](User)

        fk = Post.__bloom_columns__["user"]
        assert fk.field_name == "user"
        assert fk.db_name == "users_id"

    def test_infer_from_string_reference(self):
        """문자열 참조로 자동 추론"""

        @Entity(table_name="posts")
        class Post:
            id = PrimaryKey[int](auto_increment=True)
            # "users.id" → users_id
            author = ForeignKey[int]("users.id")

        fk = Post.__bloom_columns__["author"]
        assert fk.field_name == "author"
        assert fk.db_name == "users_id"

    def test_infer_with_custom_pk_name(self):
        """PK에 name 지정된 경우 자동 추론"""

        @Entity(table_name="accounts")
        class Account:
            id = PrimaryKey[int](name="account_pk")  # DB 컬럼명: account_pk
            email = StringColumn(max_length=255)

        @Entity(table_name="orders")
        class Order:
            id = PrimaryKey[int](auto_increment=True)
            # 자동 추론: accounts_account_pk
            account = ForeignKey[int](Account)

        fk = Order.__bloom_columns__["account"]
        assert fk.field_name == "account"
        assert fk.db_name == "accounts_account_pk"

    def test_infer_with_custom_pk_db_name(self):
        """PK에 db_name 지정된 경우 자동 추론"""

        @Entity(table_name="companies")
        class Company:
            id = PrimaryKey[int](db_name="company_uuid")
            name = StringColumn(max_length=100)

        @Entity(table_name="employees")
        class Employee:
            id = PrimaryKey[int](auto_increment=True)
            # 자동 추론: companies_company_uuid
            company = ForeignKey[int](Company)

        fk = Employee.__bloom_columns__["company"]
        assert fk.db_name == "companies_company_uuid"

    def test_infer_without_tablename(self):
        """__tablename__ 없으면 클래스명 소문자 사용"""

        @Entity
        class Team:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=100)

        @Entity
        class Player:
            id = PrimaryKey[int](auto_increment=True)
            # 자동 추론: team_id
            team = ForeignKey[int](Team)

        fk = Player.__bloom_columns__["team"]
        assert fk.db_name == "team_id"

    def test_infer_with_custom_pk_field_name(self):
        """PK 필드명이 id가 아닌 경우"""

        @Entity(table_name="departments")
        class Department:
            dept_id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=100)

        @Entity(table_name="staff")
        class Staff:
            id = PrimaryKey[int](auto_increment=True)
            # 자동 추론: departments_dept_id
            department = ForeignKey[int](Department)

        fk = Staff.__bloom_columns__["department"]
        assert fk.db_name == "departments_dept_id"

    def test_infer_complex_case(self):
        """복잡한 케이스: 테이블명 + PK name 조합"""

        @Entity(table_name="user_profiles")
        class UserProfile:
            profile_id = PrimaryKey[int](name="profile_unique_id")
            bio = StringColumn(max_length=500)

        @Entity(table_name="photos")
        class Photo:
            id = PrimaryKey[int](auto_increment=True)
            url = StringColumn(max_length=500)
            # 자동 추론: user_profiles_profile_unique_id
            profile = ForeignKey[int](UserProfile)

        fk = Photo.__bloom_columns__["profile"]
        assert fk.db_name == "user_profiles_profile_unique_id"

    def test_string_reference_table_only(self):
        """문자열 참조: 테이블명만 지정"""

        @Entity(table_name="comments")
        class Comment:
            id = PrimaryKey[int](auto_increment=True)
            # "posts" → posts_id (기본 PK는 id)
            post = ForeignKey[int]("posts")

        fk = Comment.__bloom_columns__["post"]
        assert fk.db_name == "posts_id"


class TestForeignKeyReferencesProperties:
    """ForeignKey references 관련 프로퍼티 테스트"""

    def test_references_table_from_class(self):
        """클래스에서 테이블명 가져오기"""

        @Entity(table_name="categories")
        class Category:
            id = PrimaryKey[int](auto_increment=True)

        @Entity(table_name="products")
        class Product:
            id = PrimaryKey[int](auto_increment=True)
            category = ForeignKey[int](Category)

        fk = Product.__bloom_columns__["category"]
        assert fk.references_table == "categories"

    def test_references_table_from_string(self):
        """문자열에서 테이블명 가져오기"""

        @Entity(table_name="items")
        class Item:
            id = PrimaryKey[int](auto_increment=True)
            category = ForeignKey[int]("categories.id")

        fk = Item.__bloom_columns__["category"]
        assert fk.references_table == "categories"

    def test_references_column_from_class(self):
        """클래스에서 참조 컬럼명 가져오기"""

        @Entity(table_name="users")
        class User:
            user_id = PrimaryKey[int](auto_increment=True)

        @Entity(table_name="posts")
        class Post:
            id = PrimaryKey[int](auto_increment=True)
            author = ForeignKey[int](User)

        fk = Post.__bloom_columns__["author"]
        assert fk.references_column == "user_id"

    def test_references_column_from_string(self):
        """문자열에서 참조 컬럼명 가져오기"""

        @Entity(table_name="posts")
        class Post:
            id = PrimaryKey[int](auto_increment=True)
            author = ForeignKey[int]("users.user_id")

        fk = Post.__bloom_columns__["author"]
        assert fk.references_column == "user_id"


class TestForeignKeyAndOneToManyIntegration:
    """ForeignKey와 OneToMany 통합 테스트"""

    def test_auto_inference_both_sides(self):
        """ForeignKey와 OneToMany 양쪽 자동 추론이 일치하는지 테스트"""
        from bloom.db import OneToMany

        @Entity(table_name="users")
        class User:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=100)
            # OneToMany 자동 추론: users_id
            posts = OneToMany["Post"]("Post")

        @Entity(table_name="posts")
        class Post:
            id = PrimaryKey[int](auto_increment=True)
            title = StringColumn(max_length=200)
            # ForeignKey 자동 추론: users_id
            user = ForeignKey[int](User)

        # 양쪽 db_name이 일치해야 함
        fk = Post.__bloom_columns__["user"]
        otm = User.__bloom_relations__["posts"]

        assert fk.db_name == "users_id"
        assert otm.foreign_key == "users_id"
        assert fk.db_name == otm.foreign_key

    def test_auto_inference_with_custom_pk_name(self):
        """커스텀 PK name으로 양쪽 자동 추론 일치 테스트"""
        from bloom.db import OneToMany

        @Entity(table_name="authors")
        class Author:
            id = PrimaryKey[int](name="author_id")
            name = StringColumn(max_length=100)
            books = OneToMany["Book"]("Book")

        @Entity(table_name="books")
        class Book:
            id = PrimaryKey[int](auto_increment=True)
            title = StringColumn(max_length=200)
            author = ForeignKey[int](Author)

        fk = Book.__bloom_columns__["author"]
        otm = Author.__bloom_relations__["books"]

        # 둘 다 authors_author_id로 추론되어야 함
        assert fk.db_name == "authors_author_id"
        assert otm.foreign_key == "authors_author_id"
        assert fk.db_name == otm.foreign_key

    def test_explicit_both_sides_match(self):
        """양쪽 명시적 지정이 일치하는지 테스트"""
        from bloom.db import OneToMany

        @Entity(table_name="categories")
        class Category:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=100)
            products = OneToMany["Product"]("Product", foreign_key="category_fk")

        @Entity(table_name="products")
        class Product:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=200)
            category = ForeignKey[int](Category, db_name="category_fk")

        fk = Product.__bloom_columns__["category"]
        otm = Category.__bloom_relations__["products"]

        assert fk.db_name == "category_fk"
        assert otm.foreign_key == "category_fk"
        assert fk.db_name == otm.foreign_key

    def test_complex_pk_db_name_both_sides(self):
        """복잡한 PK db_name으로 양쪽 자동 추론"""
        from bloom.db import OneToMany

        @Entity(table_name="departments")
        class Department:
            id = PrimaryKey[int](db_name="dept_uuid")
            name = StringColumn(max_length=100)
            employees = OneToMany["Employee"]("Employee")

        @Entity(table_name="employees")
        class Employee:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=100)
            department = ForeignKey[int](Department)

        fk = Employee.__bloom_columns__["department"]
        otm = Department.__bloom_relations__["employees"]

        # 둘 다 departments_dept_uuid로 추론
        assert fk.db_name == "departments_dept_uuid"
        assert otm.foreign_key == "departments_dept_uuid"
        assert fk.db_name == otm.foreign_key

    def test_onetomany_finds_fk_by_db_name(self):
        """OneToMany가 필드명이 아닌 db_name으로 FK를 찾는지 테스트"""
        from bloom.db import OneToMany
        from unittest.mock import MagicMock

        @Entity(table_name="users")
        class User:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=100)
            posts = OneToMany["Post"]("Post")

        @Entity(table_name="posts")
        class Post:
            id = PrimaryKey[int](auto_increment=True)
            title = StringColumn(max_length=200)
            # 필드명은 "user"이지만 db_name은 "users_id"
            user = ForeignKey[int](User)

        # FK의 필드명과 db_name 확인
        fk = Post.__bloom_columns__["user"]
        assert fk.field_name == "user"
        assert fk.db_name == "users_id"

        # OneToMany foreign_key도 users_id
        otm = User.__bloom_relations__["posts"]
        assert otm.foreign_key == "users_id"

        # Post.__bloom_columns__에서 db_name으로 찾을 수 있는지 확인
        target_columns = Post.__bloom_columns__
        found_col = None
        for col in target_columns.values():
            if hasattr(col, "db_name") and col.db_name == "users_id":
                found_col = col
                break
        assert found_col is not None
        assert found_col.field_name == "user"

    def test_customapp_scenario(self):
        """customapp과 동일한 구조 테스트 - Post에 __tablename__ 없음"""
        from bloom.db import OneToMany

        @Entity(table_name="users")
        class User:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=255, nullable=False)
            email = StringColumn(max_length=255, nullable=False)
            posts = OneToMany["Post"]("Post")

        @Entity  # table_name 없음!
        class Post:
            id = PrimaryKey[int](auto_increment=True)
            title = StringColumn(max_length=255, nullable=False)
            user = ForeignKey[int](User, nullable=False)

        # FK db_name 확인
        fk = Post.__bloom_columns__["user"]
        print(f"FK field_name: {fk.field_name}")
        print(f"FK db_name: {fk.db_name}")

        # OneToMany foreign_key 확인
        otm = User.__bloom_relations__["posts"]
        print(f"OneToMany foreign_key: {otm.foreign_key}")

        assert fk.db_name == "users_id", f"Expected 'users_id', got '{fk.db_name}'"
        assert (
            otm.foreign_key == "users_id"
        ), f"Expected 'users_id', got '{otm.foreign_key}'"

        # db_name으로 컬럼 찾기
        target_columns = Post.__bloom_columns__
        found_col = None
        for col in target_columns.values():
            if hasattr(col, "db_name") and col.db_name == "users_id":
                found_col = col
                break

        assert (
            found_col is not None
        ), f"Could not find column with db_name='users_id' in Post.__bloom_columns__: {list(target_columns.keys())}"
        assert found_col.field_name == "user"


class TestSessionBindingOnAdd:
    """session.add() 시 __bloom_session__ 바인딩 테스트"""

    def test_add_binds_session(self):
        """session.add()가 엔티티에 세션을 바인딩하는지 테스트"""
        from bloom.db import SessionFactory
        from bloom.db.backends import SQLiteBackend

        @Entity(table_name="test_users")
        class TestUser:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=100)

        backend = SQLiteBackend(":memory:")
        factory = SessionFactory(backend)
        factory.create_tables(TestUser)

        with factory.session() as session:
            user = TestUser()
            user.name = "Test"

            # add 전에는 세션 없음
            assert getattr(user, "__bloom_session__", None) is None

            session.add(user)

            # add 후에는 세션 바인딩
            assert getattr(user, "__bloom_session__", None) is session

    def test_new_entity_can_access_onetomany_after_save(self):
        """새로 생성한 엔티티가 save 후 OneToMany에 접근 가능한지 테스트"""
        from bloom.db import SessionFactory, OneToMany, create
        from bloom.db.backends import SQLiteBackend

        # 먼저 Book 정의 (forward reference 대신)
        @Entity(table_name="books3")
        class Book:
            id = PrimaryKey[int](auto_increment=True)
            title = StringColumn(max_length=200)
            author_id = ForeignKey[int]("authors3.id", db_name="author_id")

        @Entity(table_name="authors3")
        class Author:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=100)
            # 클래스 직접 참조
            books = OneToMany[Book](Book, foreign_key="author_id")

        backend = SQLiteBackend(":memory:")
        factory = SessionFactory(backend)
        factory.create_tables(Author, Book)

        with factory.session() as session:
            # 새 엔티티 생성 및 저장
            author = Author()
            author.name = "Test Author"
            session.add(author)
            session.flush()

            # 세션이 바인딩되어 있어야 함
            assert getattr(author, "__bloom_session__", None) is session

            # OneToMany 접근 가능해야 함 (빈 리스트)
            books = author.books
            assert books == []

    def test_customapp_scenario_full(self):
        """customapp과 동일한 시나리오 - 세션 바인딩 테스트"""
        from bloom.db import SessionFactory, OneToMany, create
        from bloom.db.backends import SQLiteBackend

        # 먼저 Post 정의 - 필드명과 db_name을 일치시켜서 복잡성 제거
        @Entity(table_name="posts3")
        class Post:
            id = PrimaryKey[int](auto_increment=True)
            title = StringColumn(max_length=255, nullable=False)
            # 필드명과 db_name을 users3_id로 일치
            users3_id = ForeignKey[int]("users3.id")

        @Entity(table_name="users3")
        class User:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=255, nullable=False)
            email = StringColumn(max_length=255, nullable=False)
            # 클래스 직접 참조, FK는 자동 추론
            posts = OneToMany[Post](Post)

        backend = SQLiteBackend(":memory:")
        factory = SessionFactory(backend)
        factory.create_tables(User, Post)

        # FK db_name 확인
        fk = Post.__bloom_columns__["users3_id"]
        assert fk.db_name == "users3_id"

        # OneToMany foreign_key 확인
        otm = User.__bloom_relations__["posts"]
        assert otm.foreign_key == "users3_id"

        with factory.session() as session:
            # 새 User 생성
            user = User()
            user.name = "Test User"
            user.email = "test@example.com"
            session.add(user)
            session.flush()

            # 세션 바인딩 확인
            assert getattr(user, "__bloom_session__", None) is session

            # OneToMany 접근 (빈 리스트)
            posts = user.posts
            assert posts == []

            # Post 생성 및 연결
            post = Post()
            post.title = "First Post"
            post.users3_id = user.id  # FK 값 설정
            session.add(post)
            session.flush()

            # OneToMany 캐시 클리어 후 다시 조회
            User.__bloom_relations__["posts"].clear_cache(user)
            posts = user.posts
            assert len(posts) == 1
            assert posts[0].title == "First Post"
