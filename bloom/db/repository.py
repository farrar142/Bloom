"""Repository pattern - Spring Data JPA style"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar, Iterator, TYPE_CHECKING

from .entity import get_entity_meta, get_entity_pk, get_pk_value
from .query import Query
from .session import Session, SessionFactory
from .expressions import Condition, ConditionGroup, OrderBy

if TYPE_CHECKING:
    pass

T = TypeVar("T")
ID = TypeVar("ID")


# =============================================================================
# Repository Interface
# =============================================================================


class Repository(ABC, Generic[T, ID]):
    """리포지토리 추상 인터페이스

    Spring Data JPA의 Repository 인터페이스와 유사합니다.
    """

    @abstractmethod
    def find_by_id(self, id: ID) -> T | None:
        """ID로 엔티티 조회"""
        ...

    @abstractmethod
    def find_all(self) -> list[T]:
        """모든 엔티티 조회"""
        ...

    @abstractmethod
    def save(self, entity: T) -> T:
        """엔티티 저장 (INSERT or UPDATE)"""
        ...

    @abstractmethod
    def delete(self, entity: T) -> None:
        """엔티티 삭제"""
        ...

    @abstractmethod
    def delete_by_id(self, id: ID) -> bool:
        """ID로 삭제"""
        ...

    @abstractmethod
    def exists_by_id(self, id: ID) -> bool:
        """ID 존재 여부"""
        ...

    @abstractmethod
    def count(self) -> int:
        """전체 개수"""
        ...


# =============================================================================
# CRUD Repository Implementation
# =============================================================================


class CrudRepository(Repository[T, ID]):
    """CRUD 리포지토리 구현

    Spring Data JPA의 CrudRepository와 유사합니다.

    Examples:
        @Entity
        class User:
            id = PrimaryKey[int](auto_increment=True)
            name = Column[str](nullable=False)

        class UserRepository(CrudRepository[User, int]):
            pass

        # 사용
        repo = UserRepository(User, session)
        user = User(name="alice")
        repo.save(user)

        found = repo.find_by_id(1)
        all_users = repo.find_all()
    """

    def __init__(self, entity_cls: type[T], session: Session):
        self._entity_cls = entity_cls
        self._session = session
        self._meta = get_entity_meta(entity_cls)

        if self._meta is None:
            raise ValueError(f"{entity_cls.__name__} is not an Entity")

    @property
    def entity_class(self) -> type[T]:
        return self._entity_cls

    @property
    def session(self) -> Session:
        return self._session

    # -------------------------------------------------------------------------
    # Query DSL
    # -------------------------------------------------------------------------

    def query(self) -> Query[T]:
        """쿼리 빌더 반환"""
        return Query(self._entity_cls).with_session(self._session)

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------

    def find_by_id(self, id: ID) -> T | None:
        """ID로 엔티티 조회"""
        return self._session.get(self._entity_cls, id)

    def find_all(self) -> list[T]:
        """모든 엔티티 조회"""
        return self.query().all()

    def find_all_by_id(self, ids: list[ID]) -> list[T]:
        """여러 ID로 엔티티 조회"""
        if not ids:
            return []

        pk_name = get_entity_pk(self._entity_cls)
        if pk_name is None:
            raise ValueError(f"{self._entity_cls.__name__} has no primary key")

        return self.query().filter(Condition(pk_name, "IN", ids)).all()

    def save(self, entity: T) -> T:
        """엔티티 저장

        새 엔티티면 INSERT, 기존이면 UPDATE
        """
        pk = get_pk_value(entity)

        if pk is None:
            # 새 엔티티 → INSERT
            self._session.add(entity)
        else:
            # 기존 엔티티 → merge (dirty tracking으로 자동 UPDATE)
            entity = self._session.merge(entity)

        self._session.flush()
        return entity

    def save_all(self, entities: list[T]) -> list[T]:
        """여러 엔티티 저장"""
        return [self.save(e) for e in entities]

    def delete(self, entity: T) -> None:
        """엔티티 삭제"""
        self._session.delete(entity)
        self._session.flush()

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
            # 전체 삭제
            self.query().delete()
        else:
            for entity in entities:
                self.delete(entity)

    def delete_all_by_id(self, ids: list[ID]) -> None:
        """여러 ID로 삭제"""
        if not ids:
            return

        pk_name = get_entity_pk(self._entity_cls)
        if pk_name is None:
            raise ValueError(f"{self._entity_cls.__name__} has no primary key")

        self.query().filter(Condition(pk_name, "IN", ids)).delete()

    def exists_by_id(self, id: ID) -> bool:
        """ID 존재 여부"""
        pk_name = get_entity_pk(self._entity_cls)
        if pk_name is None:
            raise ValueError(f"{self._entity_cls.__name__} has no primary key")

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


# =============================================================================
# Repository Factory
# =============================================================================


class RepositoryFactory:
    """리포지토리 팩토리

    Examples:
        factory = RepositoryFactory(session_factory)

        with factory.session() as repos:
            user_repo = repos.get(User)
            user_repo.save(User(name="alice"))
    """

    def __init__(self, session_factory: SessionFactory):
        self._session_factory = session_factory

    def create(self, entity_cls: type[T], session: Session) -> CrudRepository[T, Any]:
        """리포지토리 생성"""
        return CrudRepository(entity_cls, session)

    def for_session(self, session: Session) -> RepositoryProvider:
        """세션에 바인딩된 프로바이더 반환"""
        return RepositoryProvider(self, session)


class RepositoryProvider:
    """세션에 바인딩된 리포지토리 프로바이더"""

    def __init__(self, factory: RepositoryFactory, session: Session):
        self._factory = factory
        self._session = session
        self._cache: dict[type, CrudRepository[Any, Any]] = {}

    def get(self, entity_cls: type[T]) -> CrudRepository[T, Any]:
        """리포지토리 반환 (캐싱)"""
        if entity_cls not in self._cache:
            self._cache[entity_cls] = self._factory.create(entity_cls, self._session)
        return self._cache[entity_cls]

    def __getitem__(self, entity_cls: type[T]) -> CrudRepository[T, Any]:
        return self.get(entity_cls)
