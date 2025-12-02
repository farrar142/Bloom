"""Column descriptors - Column, PrimaryKey, ForeignKey, and typed columns"""

from __future__ import annotations
from typing import Any, overload, TYPE_CHECKING, Callable, Self, Literal
from weakref import WeakKeyDictionary
from datetime import datetime
from decimal import Decimal
from enum import Enum
import json

from .expressions import FieldExpression


# =============================================================================
# Fetch Type (Lazy/Eager)
# =============================================================================


class FetchType(Enum):
    """관계 로딩 전략

    LAZY: 접근 시점에 쿼리 실행 (기본값)
    EAGER: 부모 엔티티 로드 시 함께 로드
    """

    LAZY = "lazy"
    EAGER = "eager"


if TYPE_CHECKING:
    from .tracker import DirtyTracker
    from .session import Session
    from .query import Query


# =============================================================================
# Base Column Descriptor
# =============================================================================


class Column[T]:
    """컬럼 디스크립터

    인스턴스 레벨: 실제 값 반환/저장 + Dirty Tracking
    클래스 레벨: FieldExpression 반환 (쿼리용)

    Examples:
        class User:
            name = Column[str](nullable=False, max_length=100)
            age = Column[int](default=0)

        # 클래스 레벨 접근 → FieldExpression
        User.name == "alice"  # Condition

        # 인스턴스 레벨 접근 → 실제 값
        user = User()
        user.name = "alice"
        print(user.name)  # "alice"
    """

    # SQL 타입 매핑 (서브클래스에서 오버라이드)
    sql_type: str = "TEXT"

    def __init__(
        self,
        *,
        name: str | None = None,
        db_name: str | None = None,
        nullable: bool = True,
        unique: bool = False,
        default: T | Callable[[], T] | None = None,
        max_length: int | None = None,
        index: bool = False,
        primary_key: bool = False,
    ):
        self.field_name: str = ""  # __set_name__에서 설정
        self._db_name = db_name  # 명시적 DB 컬럼명
        self.nullable = nullable
        self.unique = unique
        self._default = default
        self.max_length = max_length
        self.index = index
        self.primary_key = primary_key

        # 인스턴스별 값 저장 (WeakKeyDictionary로 메모리 누수 방지)
        self._values: WeakKeyDictionary[Any, T] = WeakKeyDictionary()

    @property
    def db_name(self) -> str:
        """DB 컬럼명 (명시적으로 지정하지 않으면 field_name 사용)"""
        return self._db_name or self.field_name

    @property
    def default(self) -> T | None:
        """기본값 (callable이면 호출)"""
        if callable(self._default):
            return self._default()  # type:ignore
        return self._default

    def __set_name__(self, owner: type, name: str) -> None:
        self.field_name = name

        # 엔티티 클래스에 컬럼 메타데이터 등록
        if not hasattr(owner, "__bloom_columns__"):
            owner.__bloom_columns__ = dict[str, Column[Any]]()
        owner.__bloom_columns__[name] = self

        # PrimaryKey 등록
        if self.primary_key:
            owner.__bloom_pk__ = name

    @overload
    def __get__(self, obj: None, objtype: type) -> FieldExpression[T]: ...

    @overload
    def __get__(self, obj: object, objtype: type) -> T: ...

    def __get__(self, obj: object | None, objtype: type) -> FieldExpression[T] | T:
        if obj is None:
            # 클래스 레벨 접근 → FieldExpression 반환 (쿼리용)
            return FieldExpression[T](self.field_name, self)

        # 인스턴스 레벨 접근 → 실제 값 반환
        if obj in self._values:
            return self._values[obj]
        return self.default  # type: ignore

    def __set__(self, obj: object, value: T) -> None:
        old_value = self._values.get(obj)
        self._values[obj] = value

        # Dirty Tracking - 값이 변경되었을 때만
        if old_value != value:
            tracker: DirtyTracker | None = getattr(obj, "__bloom_tracker__", None)
            if tracker is not None:
                tracker.mark_dirty(self.field_name, old_value, value)

    def __delete__(self, obj: object) -> None:
        """값 삭제 (None으로 설정)"""
        if obj in self._values:
            del self._values[obj]

    def get_sql_type(self) -> str:
        """SQL 타입 문자열 반환"""
        sql = self.sql_type
        if self.max_length and "VARCHAR" in sql:
            sql = f"VARCHAR({self.max_length})"
        return sql

    def get_column_definition(self) -> str:
        """DDL용 컬럼 정의 반환 (컬럼 이름 제외)"""
        parts = [self.get_sql_type()]

        if self.primary_key:
            parts.append("PRIMARY KEY")
        if not self.nullable and not self.primary_key:
            parts.append("NOT NULL")
        if self.unique and not self.primary_key:
            parts.append("UNIQUE")
        if self._default is not None and not callable(self._default):
            if isinstance(self._default, str):
                parts.append(f"DEFAULT '{self._default}'")
            elif isinstance(self._default, bool):
                parts.append(f"DEFAULT {1 if self._default else 0}")
            else:
                parts.append(f"DEFAULT {self._default}")

        return " ".join(parts)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}({self.field_name!r}, nullable={self.nullable})"
        )


# =============================================================================
# Primary Key
# =============================================================================


class PrimaryKey[T](Column[T]):
    """프라이머리 키 디스크립터

    Examples:
        class User:
            id = PrimaryKey[int](auto_increment=True)
    """

    sql_type = "INTEGER"

    def __init__(
        self,
        *,
        name: str | None = None,
        db_name: str | None = None,
        auto_increment: bool = True,
    ):
        super().__init__(
            name=name,
            db_name=db_name,
            nullable=False,
            unique=True,
            primary_key=True,
        )
        self.auto_increment = auto_increment

    def get_column_definition(self) -> str:
        """DDL용 컬럼 정의 (AUTO_INCREMENT 포함, 컬럼 이름 제외)"""
        parts = [self.get_sql_type(), "PRIMARY KEY"]
        if self.auto_increment:
            parts.append("AUTOINCREMENT")
        return " ".join(parts)

    def __repr__(self) -> str:
        return f"PrimaryKey({self.field_name!r}, auto_increment={self.auto_increment})"


# =============================================================================
# Foreign Key
# =============================================================================


class ForeignKey[T](Column[T]):
    """외래 키 디스크립터

    Examples:
        class Post:
            user_id = ForeignKey[int](User, on_delete="CASCADE")
    """

    sql_type = "INTEGER"

    def __init__(
        self,
        references: type | str,
        *,
        name: str | None = None,
        db_name: str | None = None,
        nullable: bool = False,
        on_delete: str = "CASCADE",
        on_update: str = "CASCADE",
    ):
        super().__init__(
            name=name,
            db_name=db_name,
            nullable=nullable,
        )
        self._references = references  # 타입 또는 문자열 (forward reference)
        self.on_delete = on_delete
        self.on_update = on_update

    @property
    def references(self) -> type | str:
        return self._references

    @property
    def references_table(self) -> str:
        """참조 테이블명"""
        if isinstance(self._references, str):
            # "table.column" 형식 지원
            if "." in self._references:
                return self._references.split(".")[0]
            return self._references
        return getattr(
            self._references, "__tablename__", self._references.__name__.lower()
        )

    @property
    def references_column(self) -> str:
        """참조 컬럼명 (기본: id)"""
        if isinstance(self._references, str):
            # "table.column" 형식 지원
            if "." in self._references:
                return self._references.split(".")[1]
            return "id"
        if isinstance(self._references, type):
            pk = getattr(self._references, "__bloom_pk__", "id")
            return pk
        return "id"

    def get_constraint_definition(self) -> str:
        """FK 제약조건 DDL"""
        return (
            f"FOREIGN KEY ({self.db_name}) "
            f"REFERENCES {self.references_table}({self.references_column}) "
            f"ON DELETE {self.on_delete} ON UPDATE {self.on_update}"
        )

    def __repr__(self) -> str:
        ref_name = (
            self._references
            if isinstance(self._references, str)
            else self._references.__name__
        )
        return f"ForeignKey({self.field_name!r} -> {ref_name})"


# =============================================================================
# Typed Columns (편의 클래스)
# =============================================================================


class IntegerColumn(Column[int]):
    """정수 컬럼"""

    sql_type = "INTEGER"


class StringColumn(Column[str]):
    """문자열 컬럼 (VARCHAR)"""

    sql_type = "VARCHAR(255)"

    def __init__(self, max_length: int = 255, **kwargs: Any):
        super().__init__(max_length=max_length, **kwargs)

    def get_sql_type(self) -> str:
        return f"VARCHAR({self.max_length or 255})"


class TextColumn(Column[str]):
    """긴 텍스트 컬럼 (TEXT)"""

    sql_type = "TEXT"


class BooleanColumn(Column[bool]):
    """불리언 컬럼"""

    sql_type = "BOOLEAN"


class DateTimeColumn(Column[datetime]):
    """날짜/시간 컬럼"""

    sql_type = "TIMESTAMP"

    def __init__(
        self, auto_now: bool = False, auto_now_add: bool = False, **kwargs: Any
    ):
        if auto_now or auto_now_add:
            kwargs.setdefault("default", datetime.now)
        super().__init__(**kwargs)
        self.auto_now = auto_now
        self.auto_now_add = auto_now_add


class DecimalColumn(Column[Decimal]):
    """십진수 컬럼"""

    sql_type = "DECIMAL"

    def __init__(self, precision: int = 10, scale: int = 2, **kwargs: Any):
        super().__init__(**kwargs)
        self.precision = precision
        self.scale = scale

    def get_sql_type(self) -> str:
        return f"DECIMAL({self.precision}, {self.scale})"


class JSONColumn(Column[dict[str, Any] | list[Any]]):
    """JSON 컬럼"""

    sql_type = "JSON"

    def __get__(self, obj: object | None, objtype: type) -> Any:
        if obj is None:
            return FieldExpression(self.field_name, self)

        value = self._values.get(obj)
        if value is None:
            return self.default

        # 문자열이면 JSON 파싱
        if isinstance(value, str):
            return json.loads(value)
        return value

    def __set__(self, obj: object, value: Any) -> None:
        # dict/list를 저장할 때는 그대로, 문자열은 파싱하여 저장
        if isinstance(value, str):
            value = json.loads(value)
        super().__set__(obj, value)


# =============================================================================
# OneToMany Relationship (역참조)
# =============================================================================


class OneToMany[T]:
    """OneToMany 관계 디스크립터 (역참조)

    ForeignKey의 반대 방향 관계를 정의합니다.
    DB에 컬럼을 생성하지 않고, 관련 엔티티 리스트를 반환합니다.

    순환 임포트를 피하기 위해 문자열로 엔티티를 참조할 수 있습니다:
    - "Post": 같은 모듈 내 클래스
    - "posts.Post": 다른 모듈의 클래스 (app.Entity 형식)

    로딩 전략:
    - LAZY (기본): 접근 시점에 쿼리 실행하여 로드
    - EAGER: 부모 엔티티 로드 시 함께 로드

    Examples:
        @Entity
        class User:
            id = PrimaryKey[int](auto_increment=True)
            posts = OneToMany["Post"](foreign_key="user_id")

        # 접근 시 자동으로 쿼리 실행
        user.posts  # list[Post] 반환
        for post in user.posts:
            print(post.title)

        # 추가 필터링이 필요하면 Query 사용
        Query(Post).filter(Post.user_id == user.id, Post.published == True).all()
    """

    def __init__(
        self,
        target: type[T] | str,
        *,
        foreign_key: str,
        fetch: FetchType = FetchType.LAZY,
    ):
        """
        Args:
            target: 대상 엔티티 클래스 또는 문자열 (순환 임포트 방지)
            foreign_key: 대상 엔티티의 ForeignKey 필드명
            fetch: 로딩 전략 (LAZY 또는 EAGER, 기본값: LAZY)
        """
        self._target = target
        self._foreign_key = foreign_key
        self._fetch = fetch
        self._field_name: str = ""
        self._owner: type | None = None
        self._resolved_target: type[T] | None = None
        # 로딩된 데이터 캐시 (Lazy/Eager 모두 사용)
        self._cache: WeakKeyDictionary[Any, list[T]] = WeakKeyDictionary()

    def __set_name__(self, owner: type, name: str) -> None:
        self._field_name = name
        self._owner = owner

        # OneToMany는 DB 컬럼이 아니므로 __bloom_columns__에 등록하지 않음
        # 대신 __bloom_relations__에 등록
        if not hasattr(owner, "__bloom_relations__"):
            owner.__bloom_relations__ = {}
        owner.__bloom_relations__[name] = self

    def _resolve_target(self) -> type[T]:
        """문자열 타겟을 실제 클래스로 resolve"""
        if self._resolved_target is not None:
            return self._resolved_target

        if isinstance(self._target, type):
            self._resolved_target = self._target
            return self._resolved_target

        # 문자열인 경우 resolve
        target_str = self._target

        # "module.ClassName" 형식
        if "." in target_str:
            module_path, class_name = target_str.rsplit(".", 1)
            import importlib

            module = importlib.import_module(module_path)
            self._resolved_target = getattr(module, class_name)
        else:
            # 같은 모듈 내 클래스 - owner의 모듈에서 찾기
            if self._owner is not None:
                module = __import__(self._owner.__module__, fromlist=[target_str])
                self._resolved_target = getattr(module, target_str)
            else:
                raise ValueError(
                    f"Cannot resolve target '{target_str}' without owner class"
                )

        return self._resolved_target  # type: ignore

    @property
    def fetch(self) -> FetchType:
        """로딩 전략"""
        return self._fetch

    @property
    def is_lazy(self) -> bool:
        """Lazy 로딩 여부"""
        return self._fetch == FetchType.LAZY

    @property
    def is_eager(self) -> bool:
        """Eager 로딩 여부"""
        return self._fetch == FetchType.EAGER

    def __get__(self, obj: object | None, objtype: type) -> "list[T]":
        if obj is None:
            # 클래스 레벨 접근 - 디스크립터 자체 반환
            return self  # type: ignore

        # 캐시에 있으면 반환
        if obj in self._cache:
            return self._cache[obj]

        # 인스턴스 레벨 접근
        target_cls = self._resolve_target()
        owner_pk = getattr(objtype, "__bloom_pk__", "id")
        pk_value = getattr(obj, owner_pk, None)

        if pk_value is None:
            raise ValueError(
                f"Cannot access OneToMany relation: {objtype.__name__}.{owner_pk} is None"
            )

        # Eager 모드: 아직 로드되지 않았으면 빈 리스트 (Session에서 채워짐)
        if self._fetch == FetchType.EAGER:
            return []

        # Lazy 모드: 즉시 쿼리 실행
        from .query import Query

        fk_column = getattr(target_cls, self._foreign_key, None)
        if fk_column is None:
            raise ValueError(
                f"Foreign key '{self._foreign_key}' not found in {target_cls.__name__}"
            )

        # Session 가져오기 (엔티티에 바인딩된 세션)
        session: Session | None = getattr(obj, "__bloom_session__", None)
        if session is None:
            raise ValueError(
                f"Cannot lazy load OneToMany: {objtype.__name__} has no bound session. "
                "Load the entity through a Session first."
            )

        # 쿼리 실행
        query = Query(target_cls).filter(fk_column == pk_value).with_session(session)
        result = query.all()

        # 캐시에 저장
        self._cache[obj] = result
        return result

    def set_loaded_data(self, obj: object, data: list[T]) -> None:
        """로딩된 데이터 설정 (Session에서 호출)"""
        self._cache[obj] = data

    def clear_cache(self, obj: object) -> None:
        """캐시 클리어 (refresh 시)"""
        if obj in self._cache:
            del self._cache[obj]

    def __repr__(self) -> str:
        target_name = (
            self._target if isinstance(self._target, str) else self._target.__name__
        )
        fetch_str = "eager" if self._fetch == FetchType.EAGER else "lazy"
        return f"OneToMany({self._field_name!r} -> {target_name}, fk={self._foreign_key!r}, fetch={fetch_str})"
