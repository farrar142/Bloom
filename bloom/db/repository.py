"""Repository pattern - Spring Data JPA style"""

from __future__ import annotations
from abc import ABC
from typing import (
    Any,
    Generic,
    TypeVar,
    Iterator,
    TYPE_CHECKING,
    get_origin,
    get_args,
    Self,
)

from .entity import get_entity_meta, get_entity_pk, get_pk_value, EntityMeta
from .query import Query
from .session import Session, SessionFactory
from .expressions import Condition, ConditionGroup, OrderBy

if TYPE_CHECKING:
    pass

T = TypeVar("T")
ID = TypeVar("ID")


# =============================================================================
# Helper Functions
# =============================================================================


def _get_entity_class_from_generic(cls: type) -> type | None:
    """Generic 타입에서 Entity 클래스 추출

    Repository[User, int]에서 User를 추출합니다.
    """
    for base in getattr(cls, "__orig_bases__", []):
        origin = get_origin(base)
        if origin is not None:
            args = get_args(base)
            if args:
                entity_cls = args[0]
                if isinstance(entity_cls, type):
                    return entity_cls
    return None


# =============================================================================
# Repository
# =============================================================================


class Repository(ABC, Generic[T, ID]):
    """리포지토리 베이스 클래스

    Spring Data JPA의 CrudRepository와 유사합니다.
    Repository를 상속하면 자동으로 @Component로 등록됩니다.

    Session은 @Factory + @Scope(PROTOTYPE, CALL_SCOPED)로 주입받아야 합니다.
    이렇게 하면 같은 요청 내에서는 같은 Session을 공유하고,
    요청이 끝나면 자동으로 close됩니다.

    사용법:
        # 1. Session Factory 정의 (settings/database.py 등)
        @Component
        class DatabaseConfig:
            session_factory: SessionFactory
            
            @Factory
            @Scope(Scope.PROTOTYPE, PrototypeMode.CALL_SCOPED)
            def session(self) -> Session:
                return self.session_factory.create()

        # 2. Repository 정의
        class UserRepository(CrudRepository[User, int]):
            # session은 자동 주입됨
            
            def find_by_email(self, email: str) -> User | None:
                return self.find_one_by(email=email)
    """

    # 필드 주입용 - Session은 Factory로 주입됨
    session: "Session"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Repository를 상속하면 자동으로 @Component로 등록"""
        super().__init_subclass__(**kwargs)
        
        # ABC를 직접 상속한 경우 (Repository 자체)는 스킵
        if cls.__name__ == "Repository":
            return
            
        # @Component 데코레이터 적용
        from bloom.core.decorators import Component
        Component(cls)

    # 지연 초기화 캐시
    _entity_cls: "type[T] | None" = None
    _meta: "EntityMeta | None" = None

    @classmethod
    def for_entity(cls, entity_cls: type[T], session: "Session") -> Self:
        """Entity와 Session으로 Repository 생성 (팩토리 메서드)

        Args:
            entity_cls: Entity 클래스
            session: Session 인스턴스

        Returns:
            Repository 인스턴스

        Examples:
            with session_factory.session() as session:
                repo = Repository.for_entity(User, session)
                user = repo.find_by_id(1)
        """
        repo = cls()
        repo._entity_cls = entity_cls  # type: ignore
        repo.session = session
        return repo

    def _get_session(self) -> Session:
        """Session 반환 (DI로 주입됨)"""
        return self.session

    def _get_entity_class(self) -> type[T]:
        """Entity 클래스 반환 (지연 초기화)"""
        if self._entity_cls is None:
            inferred = _get_entity_class_from_generic(type(self))
            if inferred is None:
                raise ValueError(
                    f"{type(self).__name__}: Entity class not specified. "
                    "Use Generic (e.g., class UserRepo(Repository[User, int]))"
                )
            self._entity_cls = inferred  # type: ignore
        return self._entity_cls  # type: ignore

    def _get_meta(self) -> EntityMeta:
        """Entity 메타데이터 반환 (지연 초기화)"""
        if self._meta is None:
            entity_cls = self._get_entity_class()
            meta = get_entity_meta(entity_cls)
            if meta is None:
                raise ValueError(f"{entity_cls.__name__} is not an Entity")
            self._meta = meta
        return self._meta

    @property
    def entity_class(self) -> type[T]:
        return self._get_entity_class()

    # -------------------------------------------------------------------------
    # Query DSL
    # -------------------------------------------------------------------------

    def query(self) -> Query[T]:
        """쿼리 빌더 반환"""
        return Query(self._get_entity_class()).with_session(self._get_session())

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------

    def find_by_id(self, id: ID) -> T | None:
        """ID로 엔티티 조회"""
        return self._get_session().get(self._get_entity_class(), id)

    def find_all(self) -> list[T]:
        """모든 엔티티 조회"""
        return self.query().all()

    def find_all_by_id(self, ids: list[ID]) -> list[T]:
        """여러 ID로 엔티티 조회"""
        if not ids:
            return []

        entity_cls = self._get_entity_class()
        pk_name = get_entity_pk(entity_cls)
        if pk_name is None:
            raise ValueError(f"{entity_cls.__name__} has no primary key")

        return self.query().filter(Condition(pk_name, "IN", ids)).all()

    def save(self, entity: T) -> T:
        """엔티티 저장

        새 엔티티면 INSERT, 기존이면 UPDATE
        """
        pk = get_pk_value(entity)
        session = self._get_session()

        if pk is None:
            session.add(entity)
        else:
            entity = session.merge(entity)

        session.flush()
        return entity

    def save_all(self, entities: list[T]) -> list[T]:
        """여러 엔티티 저장"""
        return [self.save(e) for e in entities]

    def delete(self, entity: T) -> None:
        """엔티티 삭제"""
        session = self._get_session()
        session.delete(entity)
        session.flush()

    def delete_by_id(self, id: ID) -> bool:
        """ID로 삭제"""
        entity = self.find_by_id(id)
        if entity is None:
            return False
        self.delete(entity)
        return True

    def delete_all(self, entities: list[T] | None = None) -> None:
        """여러 엔티티 삭제"""
        if entities is None:
            self.query().delete()
        else:
            for entity in entities:
                self.delete(entity)

    def delete_all_by_id(self, ids: list[ID]) -> None:
        """여러 ID로 삭제"""
        if not ids:
            return

        entity_cls = self._get_entity_class()
        pk_name = get_entity_pk(entity_cls)
        if pk_name is None:
            raise ValueError(f"{entity_cls.__name__} has no primary key")

        self.query().filter(Condition(pk_name, "IN", ids)).delete()

    def exists_by_id(self, id: ID) -> bool:
        """ID 존재 여부"""
        entity_cls = self._get_entity_class()
        pk_name = get_entity_pk(entity_cls)
        if pk_name is None:
            raise ValueError(f"{entity_cls.__name__} has no primary key")

        return self.query().filter(Condition(pk_name, "=", id)).exists()

    def count(self) -> int:
        """전체 개수"""
        return self.query().count()

    # -------------------------------------------------------------------------
    # Extended Query Methods
    # -------------------------------------------------------------------------

    def find_by(self, **kwargs: Any) -> list[T]:
        """필드 조건으로 조회

        Examples:
            repo.find_by(name="alice", status="active")
        """
        return self.query().filter_by(**kwargs).all()

    def find_one_by(self, **kwargs: Any) -> T | None:
        """필드 조건으로 단일 조회"""
        return self.query().filter_by(**kwargs).first()

    def find_all_ordered(self, *orders: OrderBy) -> list[T]:
        """정렬하여 전체 조회"""
        return self.query().order_by(*orders).all()

    def find_page(self, page: int, size: int) -> list[T]:
        """페이지네이션 조회

        Args:
            page: 페이지 번호 (0부터 시작)
            size: 페이지 크기
        """
        return self.query().offset(page * size).limit(size).all()

    def find_slice(self, offset: int, limit: int) -> list[T]:
        """슬라이스 조회"""
        return self.query().offset(offset).limit(limit).all()

    # -------------------------------------------------------------------------
    # Iteration
    # -------------------------------------------------------------------------

    def __iter__(self) -> Iterator[T]:
        return iter(self.find_all())

    def __len__(self) -> int:
        return self.count()


# Alias for backward compatibility
CrudRepository = Repository
