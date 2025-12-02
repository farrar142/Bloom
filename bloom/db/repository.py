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
from .session import Session, AsyncSession, SessionFactory
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

    Session은 @Factory + @Scope(CALL, CALL_SCOPED)로 주입받아야 합니다.
    이렇게 하면 같은 요청 내에서는 같은 Session을 공유하고,
    요청이 끝나면 자동으로 close됩니다.

    동기/비동기 메서드 모두 지원합니다:
    - 동기: session 필드 사용, find_by_id(), save() 등
    - 비동기: async_session 필드 사용, find_by_id_async(), save_async() 등

    사용법:
        # 1. Session Factory 정의 (settings/database.py 등)
        @Component
        class DatabaseConfig:
            session_factory: SessionFactory
            
            @Factory
            @Scope(Scope.CALL, PrototypeMode.CALL_SCOPED)
            def session(self) -> Session:
                return self.session_factory.create()
            
            @Factory
            @Scope(Scope.CALL, PrototypeMode.CALL_SCOPED)
            async def async_session(self) -> AsyncSession:
                return await self.session_factory.create_async()

        # 2. Repository 정의
        class UserRepository(CrudRepository[User, int]):
            # session, async_session은 자동 주입됨
            
            def find_by_email(self, email: str) -> User | None:
                return self.find_one_by(email=email)
            
            async def find_by_email_async(self, email: str) -> User | None:
                return await self.find_one_by_async(email=email)
    """

    # 필드 주입용 - Session/AsyncSession은 Factory로 주입됨
    session: "Session"
    async_session: "AsyncSession"

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

    def _get_async_session(self) -> AsyncSession:
        """AsyncSession 반환 (DI로 주입됨)"""
        return self.async_session

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

    # =========================================================================
    # Async CRUD Operations
    # =========================================================================

    async def find_by_id_async(self, id: ID) -> T | None:
        """ID로 엔티티 조회 (비동기)"""
        return await self._get_async_session().get(self._get_entity_class(), id)

    async def find_all_async(self) -> list[T]:
        """모든 엔티티 조회 (비동기)"""
        entity_cls = self._get_entity_class()
        meta = self._get_meta()
        session = self._get_async_session()

        sql = session.dialect.select_sql(meta)
        rows = [row async for row in session.execute(sql)]

        from .entity import dict_to_entity

        return [dict_to_entity(entity_cls, dict(row)) for row in rows]

    async def find_all_by_id_async(self, ids: list[ID]) -> list[T]:
        """여러 ID로 엔티티 조회 (비동기)"""
        if not ids:
            return []

        entity_cls = self._get_entity_class()
        pk_name = get_entity_pk(entity_cls)
        if pk_name is None:
            raise ValueError(f"{entity_cls.__name__} has no primary key")

        meta = self._get_meta()
        session = self._get_async_session()

        # IN 조건 생성
        placeholders = ", ".join(f":id{i}" for i in range(len(ids)))
        where = f'"{pk_name}" IN ({placeholders})'
        params = {f"id{i}": id_val for i, id_val in enumerate(ids)}

        sql = session.dialect.select_sql(meta, where=where)
        rows = [row async for row in session.execute(sql, params)]

        from .entity import dict_to_entity

        return [dict_to_entity(entity_cls, dict(row)) for row in rows]

    async def save_async(self, entity: T) -> T:
        """엔티티 저장 (비동기)

        새 엔티티면 INSERT, 기존이면 UPDATE
        """
        pk = get_pk_value(entity)
        session = self._get_async_session()

        if pk is None:
            session.add(entity)
        else:
            entity = await session.merge(entity)

        await session.flush()
        return entity

    async def save_all_async(self, entities: list[T]) -> list[T]:
        """여러 엔티티 저장 (비동기)"""
        return [await self.save_async(e) for e in entities]

    async def delete_async(self, entity: T) -> None:
        """엔티티 삭제 (비동기)"""
        session = self._get_async_session()
        session.delete(entity)
        await session.flush()

    async def delete_by_id_async(self, id: ID) -> bool:
        """ID로 삭제 (비동기)"""
        entity = await self.find_by_id_async(id)
        if entity is None:
            return False
        await self.delete_async(entity)
        return True

    async def delete_all_async(self, entities: list[T] | None = None) -> None:
        """여러 엔티티 삭제 (비동기)"""
        if entities is None:
            # 전체 삭제
            meta = self._get_meta()
            session = self._get_async_session()
            sql = f'DELETE FROM "{meta.table_name}"'
            await session.execute_update(sql)
        else:
            for entity in entities:
                await self.delete_async(entity)

    async def delete_all_by_id_async(self, ids: list[ID]) -> None:
        """여러 ID로 삭제 (비동기)"""
        if not ids:
            return

        entity_cls = self._get_entity_class()
        pk_name = get_entity_pk(entity_cls)
        if pk_name is None:
            raise ValueError(f"{entity_cls.__name__} has no primary key")

        meta = self._get_meta()
        session = self._get_async_session()

        placeholders = ", ".join(f":id{i}" for i in range(len(ids)))
        sql = f'DELETE FROM "{meta.table_name}" WHERE "{pk_name}" IN ({placeholders})'
        params = {f"id{i}": id_val for i, id_val in enumerate(ids)}

        await session.execute_update(sql, params)

    async def exists_by_id_async(self, id: ID) -> bool:
        """ID 존재 여부 (비동기)"""
        entity_cls = self._get_entity_class()
        pk_name = get_entity_pk(entity_cls)
        if pk_name is None:
            raise ValueError(f"{entity_cls.__name__} has no primary key")

        meta = self._get_meta()
        session = self._get_async_session()

        sql = f'SELECT 1 FROM "{meta.table_name}" WHERE "{pk_name}" = :pk LIMIT 1'
        rows = [row async for row in session.execute(sql, {"pk": id})]
        return len(rows) > 0

    async def count_async(self) -> int:
        """전체 개수 (비동기)"""
        meta = self._get_meta()
        session = self._get_async_session()

        sql = f'SELECT COUNT(*) as cnt FROM "{meta.table_name}"'
        rows = [row async for row in session.execute(sql)]
        if rows:
            return rows[0].get("cnt", 0)
        return 0

    # -------------------------------------------------------------------------
    # Async Extended Query Methods
    # -------------------------------------------------------------------------

    async def find_by_async(self, **kwargs: Any) -> list[T]:
        """필드 조건으로 조회 (비동기)

        Examples:
            await repo.find_by_async(name="alice", status="active")
        """
        if not kwargs:
            return await self.find_all_async()

        entity_cls = self._get_entity_class()
        meta = self._get_meta()
        session = self._get_async_session()

        # WHERE 조건 생성
        conditions = [f'"{k}" = :{k}' for k in kwargs.keys()]
        where = " AND ".join(conditions)

        sql = session.dialect.select_sql(meta, where=where)
        rows = [row async for row in session.execute(sql, kwargs)]

        from .entity import dict_to_entity

        return [dict_to_entity(entity_cls, dict(row)) for row in rows]

    async def find_one_by_async(self, **kwargs: Any) -> T | None:
        """필드 조건으로 단일 조회 (비동기)"""
        results = await self.find_by_async(**kwargs)
        return results[0] if results else None

    async def find_all_ordered_async(self, *orders: OrderBy) -> list[T]:
        """정렬하여 전체 조회 (비동기)"""
        entity_cls = self._get_entity_class()
        meta = self._get_meta()
        session = self._get_async_session()

        # ORDER BY 생성
        order_clauses = []
        for order in orders:
            direction = "DESC" if order.desc else "ASC"
            order_clauses.append(f'"{order.field}" {direction}')

        order_by = ", ".join(order_clauses) if order_clauses else None
        sql = session.dialect.select_sql(meta, order_by=order_by)
        rows = [row async for row in session.execute(sql)]

        from .entity import dict_to_entity

        return [dict_to_entity(entity_cls, dict(row)) for row in rows]

    async def find_page_async(self, page: int, size: int) -> list[T]:
        """페이지네이션 조회 (비동기)

        Args:
            page: 페이지 번호 (0부터 시작)
            size: 페이지 크기
        """
        return await self.find_slice_async(page * size, size)

    async def find_slice_async(self, offset: int, limit: int) -> list[T]:
        """슬라이스 조회 (비동기)"""
        entity_cls = self._get_entity_class()
        meta = self._get_meta()
        session = self._get_async_session()

        sql = session.dialect.select_sql(meta, limit=limit, offset=offset)
        rows = [row async for row in session.execute(sql)]

        from .entity import dict_to_entity

        return [dict_to_entity(entity_cls, dict(row)) for row in rows]


# Alias for backward compatibility
CrudRepository = Repository
