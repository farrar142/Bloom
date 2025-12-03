"""Entity decorator and metaclass"""

from __future__ import annotations
from typing import Any, Callable, TypeVar, overload, TYPE_CHECKING, Self
from dataclasses import dataclass, field

from .columns import Column, PrimaryKey, ManyToOne
from .tracker import DirtyTracker, EntityState

if TYPE_CHECKING:
    pass

T = TypeVar("T")


# =============================================================================
# Entity Metadata
# =============================================================================


@dataclass
class EntityMeta:
    """엔티티 메타데이터

    엔티티 클래스의 테이블 정보, 컬럼 정보 등을 저장합니다.
    """

    table_name: str
    columns: dict[str, Column[Any]] = field(default_factory=dict)
    primary_key: str | None = None
    indexes: list[str] = field(default_factory=list)
    unique_constraints: list[tuple[str, ...]] = field(default_factory=list)

    @property
    def column_names(self) -> list[str]:
        """모든 컬럼의 DB 컬럼명 반환

        ManyToOne의 경우 db_name (예: user_id)을 반환합니다.
        """
        result = []
        for name, column in self.columns.items():
            if isinstance(column, ManyToOne):
                result.append(column.db_name)
            elif hasattr(column, "db_name"):
                result.append(column.db_name)
            else:
                result.append(name)
        return result

    @property
    def pk_column(self) -> Column[Any] | None:
        """PK 컬럼 반환"""
        if self.primary_key:
            return self.columns.get(self.primary_key)
        return None

    def get_column(self, name: str) -> Column[Any] | None:
        """컬럼 반환"""
        return self.columns.get(name)


# =============================================================================
# Entity Decorator
# =============================================================================


@overload
def Entity(cls: type[T]) -> type[T]: ...


@overload
def Entity(
    *,
    table_name: str | None = None,
    indexes: list[str] | None = None,
) -> Callable[[type[T]], type[T]]: ...


def Entity(
    cls: type[T] | None = None,
    *,
    table_name: str | None = None,
    indexes: list[str] | None = None,
) -> type[T] | Callable[[type[T]], type[T]]:
    """엔티티 데코레이터

    클래스를 DB 엔티티로 등록합니다.
    Spring의 @Entity와 유사합니다.

    Examples:
        @Entity
        class User:
            id = PrimaryKey[int](auto_increment=True)
            name = Column[str](nullable=False)
            email = Column[str](nullable=False, unique=True)

        @Entity(table_name="users", indexes=["name"])
        class User:
            id = PrimaryKey[int]()
            name = Column[str]()
    """

    def decorator(cls: type[T]) -> type[T]:
        # 테이블명 결정 (명시적 > 클래스명 소문자)
        tbl_name = (
            table_name or getattr(cls, "__tablename__", None) or cls.__name__.lower()
        )

        # 컬럼 수집
        columns: dict[str, Column[Any]] = {}
        pk_name: str | None = None

        # 상속 계층에서 컬럼 수집
        for base in reversed(cls.__mro__):
            if hasattr(base, "__bloom_columns__"):
                columns.update(base.__bloom_columns__)

        # 현재 클래스의 컬럼 수집
        for name, attr in cls.__dict__.items():
            if isinstance(attr, Column):
                columns[name] = attr
                if attr.primary_key:
                    pk_name = name

        # PK 찾기 (명시적 PrimaryKey 또는 __bloom_pk__)
        if pk_name is None:
            pk_name = getattr(cls, "__bloom_pk__", None)

        # 메타데이터 생성
        meta = EntityMeta(
            table_name=tbl_name,
            columns=columns,
            primary_key=pk_name,
            indexes=indexes or [],
        )

        # 클래스에 메타데이터 저장
        cls.__bloom_meta__ = meta  # type: ignore
        cls.__tablename__ = tbl_name  # type: ignore
        cls.__bloom_columns__ = columns  # type: ignore

        # __init__ 래핑하여 DirtyTracker 자동 주입 (필드 주입 방식)
        original_init = cls.__init__ if hasattr(cls, "__init__") else None

        def new_init(self: Any) -> None:
            # DirtyTracker 주입
            object.__setattr__(self, "__bloom_tracker__", DirtyTracker())

            # 원본 __init__ 호출 (인자 없이)
            if original_init and original_init is not object.__init__:
                try:
                    original_init(self)
                except TypeError:
                    pass  # 원본 __init__이 인자를 받는 경우 무시

        cls.__init__ = new_init  # type: ignore

        # __repr__ 추가 (없으면)
        if "__repr__" not in cls.__dict__:

            def entity_repr(self: Any) -> str:
                pk_val = getattr(self, pk_name, None) if pk_name else None
                return f"{cls.__name__}(id={pk_val})"

            cls.__repr__ = entity_repr  # type: ignore

        return cls

    if cls is not None:
        return decorator(cls)
    return decorator


# =============================================================================
# Entity Helper Functions
# =============================================================================


def get_entity_meta(entity_cls: type) -> EntityMeta | None:
    """엔티티 클래스의 메타데이터 반환"""
    return getattr(entity_cls, "__bloom_meta__", None)


def get_entity_columns(entity_cls: type) -> dict[str, Column[Any]]:
    """엔티티 클래스의 컬럼들 반환"""
    return getattr(entity_cls, "__bloom_columns__", {})


def get_entity_pk(entity_cls: type) -> str | None:
    """엔티티 클래스의 PK 필드명 반환"""
    meta = get_entity_meta(entity_cls)
    return meta.primary_key if meta else None


def get_pk_value(entity: Any) -> Any:
    """엔티티 인스턴스의 PK 값 반환"""
    pk_name = get_entity_pk(type(entity))
    if pk_name:
        return getattr(entity, pk_name, None)
    return None


def set_pk_value(entity: Any, value: Any) -> None:
    """엔티티 인스턴스의 PK 값 설정"""
    pk_name = get_entity_pk(type(entity))
    if pk_name:
        setattr(entity, pk_name, value)


def entity_to_dict(entity: Any, include_none: bool = False) -> dict[str, Any]:
    """엔티티를 딕셔너리로 변환

    ManyToOne 필드의 경우 FK 값을 가져옵니다.
    """
    columns = get_entity_columns(type(entity))
    result = {}
    for name, column in columns.items():
        # ManyToOne의 경우 FK 값 가져오기
        if isinstance(column, ManyToOne):
            value = column.get_fk_value(entity)
            db_name = column.db_name
            if include_none or value is not None:
                result[db_name] = value
        else:
            value = getattr(entity, name, None)
            if include_none or value is not None:
                result[name] = value
    return result


def dict_to_entity(entity_cls: type[T], data: dict[str, Any]) -> T:
    """딕셔너리를 엔티티로 변환

    ManyToOne 필드의 경우 FK 값을 db_name으로 찾아서 설정합니다.
    FK 컬럼이 별도로 정의된 경우에도 값을 설정합니다.
    """
    entity = entity_cls()
    columns = get_entity_columns(entity_cls)

    # db_name -> (field_name, column) 매핑 생성
    # FK 필드는 ManyToOne과 일반 컬럼 모두에 값을 설정해야 함
    db_name_to_field: dict[str, list[tuple[str, Any]]] = {}
    for name, column in columns.items():
        if isinstance(column, ManyToOne):
            db_name = column.db_name
            if db_name not in db_name_to_field:
                db_name_to_field[db_name] = []
            db_name_to_field[db_name].append((name, column))
        elif hasattr(column, "db_name"):
            db_name = column.db_name
            if db_name not in db_name_to_field:
                db_name_to_field[db_name] = []
            db_name_to_field[db_name].append((name, column))

        # 필드 이름으로도 매핑
        if name not in db_name_to_field:
            db_name_to_field[name] = []
        # 중복 방지
        if (name, column) not in db_name_to_field[name]:
            db_name_to_field[name].append((name, column))

    for data_key, value in data.items():
        if data_key in db_name_to_field:
            for field_name, column in db_name_to_field[data_key]:
                if isinstance(column, ManyToOne):
                    # ManyToOne: FK 값 직접 설정
                    column.set_fk_value(entity, value)
                else:
                    setattr(entity, field_name, value)
        elif data_key in columns:
            setattr(entity, data_key, value)

    # 로드됨 마킹
    tracker: DirtyTracker | None = getattr(entity, "__bloom_tracker__", None)
    if tracker:
        tracker.mark_loaded(data)

    return entity


def create(entity_cls: type[T], **kwargs: Any) -> T:
    """엔티티 생성 헬퍼 함수

    필드 주입 방식으로 엔티티를 생성합니다.

    Examples:
        user = create(User, name="Alice", email="alice@example.com", age=25)
    """
    entity = entity_cls()
    columns = get_entity_columns(entity_cls)

    for name, value in kwargs.items():
        if name in columns:
            setattr(entity, name, value)

    return entity
