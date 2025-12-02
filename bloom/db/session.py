"""Session - Unit of Work pattern implementation"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, TypeVar, Generic, Iterator, AsyncIterator, TYPE_CHECKING
from contextlib import contextmanager, asynccontextmanager
from weakref import WeakValueDictionary

from .entity import (
    EntityMeta,
    get_entity_meta,
    get_entity_pk,
    get_pk_value,
    set_pk_value,
    entity_to_dict,
    dict_to_entity,
)
from .tracker import DirtyTracker, EntityState
from .dialect import Dialect
from .query import Query, QueryBuilder
from .backends.base import DatabaseBackend, Connection, AsyncConnection, ConnectionPool

if TYPE_CHECKING:
    from .columns import Column
    from bloom.core.protocols import AutoCloseable

T = TypeVar("T")


# =============================================================================
# Session (Unit of Work)
# =============================================================================


class Session:
    """세션 - Unit of Work 패턴 구현

    AutoCloseable 프로토콜을 구현하여 DI 컨테이너에서 자동으로 정리됩니다.
    CALL 스코프로 사용 시 메서드 종료 시 자동으로 close()가 호출됩니다.

    엔티티의 생명주기를 관리하고, 변경 사항을 추적하여
    flush 시점에 DB에 반영합니다.

    Examples:
        # Context Manager 사용 (권장)
        with session_factory.create() as session:
            user = User(name="alice")
            session.add(user)
            session.commit()

        # DI로 주입받아 사용 (CALL + CALL_SCOPED 권장)
        @Component
        class UserService:
            session: Session  # 자동으로 정리됨

            def create_user(self, name: str) -> User:
                user = User(name=name)
                self.session.add(user)
                self.session.commit()
                return user
    """

    def __init__(self, connection: Connection, autoflush: bool = True):
        self._connection = connection
        self._dialect = connection.dialect
        self._autoflush = autoflush

        # Identity Map - 같은 PK를 가진 엔티티는 동일 인스턴스
        self._identity_map: dict[tuple[type, Any], Any] = {}

        # 변경 추적
        self._new: set[Any] = set()  # 새로 추가된 엔티티
        self._dirty: set[Any] = set()  # 변경된 엔티티
        self._deleted: set[Any] = set()  # 삭제 예정 엔티티

        self._closed = False

    @property
    def dialect(self) -> Dialect:
        return self._dialect

    def query(self, entity_cls: type[T]) -> Query[T]:
        """쿼리 빌더 생성"""
        return Query(entity_cls).with_session(self)

    def query_builder(self) -> QueryBuilder:
        """쿼리 빌더 팩토리 반환"""
        return QueryBuilder(self)

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------

    def add(self, entity: T) -> T:
        """엔티티 추가 (INSERT 예약)"""
        self._check_closed()

        tracker: DirtyTracker | None = getattr(entity, "__bloom_tracker__", None)
        if tracker is None:
            tracker = DirtyTracker()
            object.__setattr__(entity, "__bloom_tracker__", tracker)

        tracker.state = EntityState.MANAGED
        self._new.add(entity)
        return entity

    def add_all(self, entities: list[T]) -> list[T]:
        """여러 엔티티 추가"""
        for entity in entities:
            self.add(entity)
        return entities

    def delete(self, entity: Any) -> None:
        """엔티티 삭제 (DELETE 예약)"""
        self._check_closed()

        tracker: DirtyTracker | None = getattr(entity, "__bloom_tracker__", None)
        if tracker:
            tracker.mark_deleted()

        # 새로 추가된 엔티티면 new에서 제거만
        if entity in self._new:
            self._new.discard(entity)
        else:
            self._deleted.add(entity)
            self._dirty.discard(entity)

    def get(self, entity_cls: type[T], pk: Any) -> T | None:
        """PK로 엔티티 조회"""
        self._check_closed()

        # Identity Map 확인
        key = (entity_cls, pk)
        if key in self._identity_map:
            return self._identity_map[key]

        # DB에서 조회
        meta = get_entity_meta(entity_cls)
        if meta is None or meta.primary_key is None:
            raise ValueError(f"{entity_cls.__name__} has no primary key")

        pk_col = meta.primary_key
        sql = self._dialect.select_sql(
            meta,
            where=f'"{pk_col}" = :pk',
        )

        rows = list(self.execute(sql, {"pk": pk}))
        if not rows:
            return None

        entity = dict_to_entity(entity_cls, dict(rows[0]))
        self._identity_map[key] = entity
        return entity

    def refresh(self, entity: Any) -> None:
        """엔티티 리프레시 (DB에서 다시 로드)"""
        self._check_closed()

        entity_cls = type(entity)
        pk = get_pk_value(entity)
        if pk is None:
            raise ValueError("Cannot refresh entity without PK")

        meta = get_entity_meta(entity_cls)
        if meta is None or meta.primary_key is None:
            raise ValueError(f"{entity_cls.__name__} has no primary key")

        pk_col = meta.primary_key
        sql = self._dialect.select_sql(meta, where=f'"{pk_col}" = :pk')

        rows = list(self.execute(sql, {"pk": pk}))
        if not rows:
            raise ValueError(f"Entity not found: {entity_cls.__name__}#{pk}")

        data = dict(rows[0])
        for name, value in data.items():
            setattr(entity, name, value)

        tracker: DirtyTracker | None = getattr(entity, "__bloom_tracker__", None)
        if tracker:
            tracker.mark_loaded(data)

    def merge(self, entity: T) -> T:
        """엔티티 병합 (detached → managed)"""
        self._check_closed()

        entity_cls = type(entity)
        pk = get_pk_value(entity)

        if pk is not None:
            # 기존 엔티티 찾기
            existing = self.get(entity_cls, pk)
            if existing is not None:
                # 값 복사
                meta = get_entity_meta(entity_cls)
                if meta:
                    for name in meta.columns:
                        setattr(existing, name, getattr(entity, name, None))

                # dirty tracking: 값이 변경되었으면 _dirty에 추가
                tracker: DirtyTracker | None = getattr(
                    existing, "__bloom_tracker__", None
                )
                if tracker and tracker.is_dirty:
                    self._dirty.add(existing)

                return existing  # type: ignore

        # 새 엔티티로 추가
        return self.add(entity)

    # -------------------------------------------------------------------------
    # Query Execution
    # -------------------------------------------------------------------------

    def execute(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> Iterator[dict[str, Any]]:
        """SQL 실행 (SELECT용)"""
        self._check_closed()

        if self._autoflush:
            self.flush()

        result = self._connection.execute(sql, params or {})
        return iter(result.fetchall())

    def execute_update(self, sql: str, params: dict[str, Any] | None = None) -> int:
        """SQL 실행 (UPDATE/DELETE용) - 영향받은 행 수 반환"""
        self._check_closed()

        if self._autoflush:
            self.flush()

        result = self._connection.execute(sql, params or {})
        return result.rowcount

    # -------------------------------------------------------------------------
    # Flush & Commit
    # -------------------------------------------------------------------------

    def flush(self) -> None:
        """변경 사항을 DB에 반영 (커밋 없이)"""
        self._check_closed()

        # INSERT
        for entity in list(self._new):
            self._do_insert(entity)
        self._new.clear()

        # UPDATE (dirty tracking)
        for entity in list(self._dirty):
            self._do_update(entity)
        self._dirty.clear()

        # DELETE
        for entity in list(self._deleted):
            self._do_delete(entity)
        self._deleted.clear()

    def commit(self) -> None:
        """변경 사항 커밋"""
        self._check_closed()
        self.flush()
        self._connection.commit()

    def rollback(self) -> None:
        """변경 사항 롤백"""
        self._check_closed()
        self._connection.rollback()

        # 상태 초기화
        self._new.clear()
        self._dirty.clear()
        self._deleted.clear()
        self._identity_map.clear()

    def close(self) -> None:
        """세션 닫기"""
        if not self._closed:
            self._new.clear()
            self._dirty.clear()
            self._deleted.clear()
            self._identity_map.clear()
            self._closed = True

    def _check_closed(self) -> None:
        if self._closed:
            raise RuntimeError("Session is closed")

    # -------------------------------------------------------------------------
    # Internal Operations
    # -------------------------------------------------------------------------

    def _do_insert(self, entity: Any) -> None:
        """INSERT 실행"""
        entity_cls = type(entity)
        meta = get_entity_meta(entity_cls)
        if meta is None:
            raise ValueError(f"{entity_cls.__name__} is not an Entity")

        # 값 수집 (auto_increment PK 제외)
        data = entity_to_dict(entity, include_none=False)
        pk_col = meta.primary_key

        # auto_increment PK는 제외
        if pk_col and pk_col in data:
            pk_column = meta.columns.get(pk_col)
            if pk_column and getattr(pk_column, "auto_increment", False):
                if data.get(pk_col) is None:
                    del data[pk_col]

        columns = list(data.keys())
        sql = self._dialect.insert_returning_sql(meta, columns)

        result = self._connection.execute(sql, data)

        # auto_increment PK 값 설정
        if pk_col and pk_col not in data:
            pk_value = result.lastrowid
            set_pk_value(entity, pk_value)

        # Identity Map에 등록
        pk = get_pk_value(entity)
        if pk is not None:
            self._identity_map[(entity_cls, pk)] = entity

        # Tracker 업데이트
        tracker: DirtyTracker | None = getattr(entity, "__bloom_tracker__", None)
        if tracker:
            tracker.mark_persisted()

    def _do_update(self, entity: Any) -> None:
        """UPDATE 실행"""
        entity_cls = type(entity)
        meta = get_entity_meta(entity_cls)
        if meta is None:
            raise ValueError(f"{entity_cls.__name__} is not an Entity")

        pk_col = meta.primary_key
        if pk_col is None:
            raise ValueError(f"{entity_cls.__name__} has no primary key")

        pk = get_pk_value(entity)
        if pk is None:
            raise ValueError("Cannot update entity without PK")

        # Dirty 필드만 업데이트
        tracker: DirtyTracker | None = getattr(entity, "__bloom_tracker__", None)
        if tracker is None or not tracker.is_dirty:
            return

        dirty_fields = tracker.get_dirty_fields()
        data = {f: getattr(entity, f) for f in dirty_fields}
        data[pk_col] = pk

        sql = self._dialect.update_sql(meta, dirty_fields, pk_col)
        self._connection.execute(sql, data)

        tracker.clear()

    def _do_delete(self, entity: Any) -> None:
        """DELETE 실행"""
        entity_cls = type(entity)
        meta = get_entity_meta(entity_cls)
        if meta is None:
            raise ValueError(f"{entity_cls.__name__} is not an Entity")

        pk_col = meta.primary_key
        if pk_col is None:
            raise ValueError(f"{entity_cls.__name__} has no primary key")

        pk = get_pk_value(entity)
        if pk is None:
            raise ValueError("Cannot delete entity without PK")

        sql = self._dialect.delete_sql(meta, pk_col)
        self._connection.execute(sql, {pk_col: pk})

        # Identity Map에서 제거
        key = (entity_cls, pk)
        self._identity_map.pop(key, None)

    def __enter__(self) -> Session:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            self.rollback()
        self.close()


# =============================================================================
# Async Session (Unit of Work)
# =============================================================================


class AsyncSession:
    """비동기 세션 - Unit of Work 패턴 구현 (Async)

    AsyncConnection을 사용하여 비동기 DB 작업을 지원합니다.

    Examples:
        # Async Context Manager 사용 (권장)
        async with session_factory.create_async() as session:
            user = User(name="alice")
            session.add(user)
            await session.commit()

        # Async 세션 직접 생성
        session = await session_factory.create_async()
        try:
            user = User(name="alice")
            session.add(user)
            await session.commit()
        finally:
            await session.close()
    """

    def __init__(
        self,
        connection: AsyncConnection,
        pool: ConnectionPool,
        autoflush: bool = True,
    ):
        self._connection = connection
        self._pool = pool
        self._dialect = pool.config  # Will get dialect from somewhere else
        self._autoflush = autoflush

        # Identity Map - 같은 PK를 가진 엔티티는 동일 인스턴스
        self._identity_map: dict[tuple[type, Any], Any] = {}

        # 변경 추적
        self._new: set[Any] = set()  # 새로 추가된 엔티티
        self._dirty: set[Any] = set()  # 변경된 엔티티
        self._deleted: set[Any] = set()  # 삭제 예정 엔티티

        self._closed = False

    @property
    def dialect(self) -> Any:
        return getattr(self._connection, "dialect", None)

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------

    def add(self, entity: T) -> T:
        """엔티티 추가 (INSERT 예약)"""
        self._check_closed()

        tracker: DirtyTracker | None = getattr(entity, "__bloom_tracker__", None)
        if tracker is None:
            tracker = DirtyTracker()
            object.__setattr__(entity, "__bloom_tracker__", tracker)

        tracker.state = EntityState.MANAGED
        self._new.add(entity)
        return entity

    def add_all(self, entities: list[T]) -> list[T]:
        """여러 엔티티 추가"""
        for entity in entities:
            self.add(entity)
        return entities

    def delete(self, entity: Any) -> None:
        """엔티티 삭제 (DELETE 예약)"""
        self._check_closed()

        tracker: DirtyTracker | None = getattr(entity, "__bloom_tracker__", None)
        if tracker:
            tracker.mark_deleted()

        if entity in self._new:
            self._new.discard(entity)
        else:
            self._deleted.add(entity)
            self._dirty.discard(entity)

    async def get(self, entity_cls: type[T], pk: Any) -> T | None:
        """PK로 엔티티 조회"""
        self._check_closed()

        # Identity Map 확인
        key = (entity_cls, pk)
        if key in self._identity_map:
            return self._identity_map[key]

        # DB에서 조회
        meta = get_entity_meta(entity_cls)
        if meta is None or meta.primary_key is None:
            raise ValueError(f"{entity_cls.__name__} has no primary key")

        pk_col = meta.primary_key
        dialect = self.dialect
        if dialect is None:
            raise ValueError("Dialect not available")

        sql = dialect.select_sql(
            meta,
            where=f'"{pk_col}" = :pk',
        )

        rows = [row async for row in self.execute(sql, {"pk": pk})]
        if not rows:
            return None

        entity = dict_to_entity(entity_cls, dict(rows[0]))
        self._identity_map[key] = entity
        return entity

    async def refresh(self, entity: Any) -> None:
        """엔티티 리프레시 (DB에서 다시 로드)"""
        self._check_closed()

        entity_cls = type(entity)
        pk = get_pk_value(entity)
        if pk is None:
            raise ValueError("Cannot refresh entity without PK")

        meta = get_entity_meta(entity_cls)
        if meta is None or meta.primary_key is None:
            raise ValueError(f"{entity_cls.__name__} has no primary key")

        dialect = self.dialect
        if dialect is None:
            raise ValueError("Dialect not available")

        pk_col = meta.primary_key
        sql = dialect.select_sql(meta, where=f'"{pk_col}" = :pk')

        rows = [row async for row in self.execute(sql, {"pk": pk})]
        if not rows:
            raise ValueError(f"Entity not found: {entity_cls.__name__}#{pk}")

        data = dict(rows[0])
        for name, value in data.items():
            setattr(entity, name, value)

        tracker: DirtyTracker | None = getattr(entity, "__bloom_tracker__", None)
        if tracker:
            tracker.mark_loaded(data)

    async def merge(self, entity: T) -> T:
        """엔티티 병합 (detached → managed)"""
        self._check_closed()

        entity_cls = type(entity)
        pk = get_pk_value(entity)

        if pk is not None:
            existing = await self.get(entity_cls, pk)
            if existing is not None:
                meta = get_entity_meta(entity_cls)
                if meta:
                    for name in meta.columns:
                        setattr(existing, name, getattr(entity, name, None))

                    tracker: DirtyTracker | None = getattr(
                        existing, "__bloom_tracker__", None
                    )
                    if tracker and tracker.is_dirty:
                        self._dirty.add(existing)

                return existing  # type: ignore

        return self.add(entity)

    # -------------------------------------------------------------------------
    # Query Execution
    # -------------------------------------------------------------------------

    async def execute(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """SQL 실행 (SELECT용)"""
        self._check_closed()

        if self._autoflush:
            await self.flush()

        await self._connection.execute(sql, params or {})
        rows = await self._connection.fetchall()
        for row in rows:
            yield row

    async def execute_update(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> int:
        """SQL 실행 (UPDATE/DELETE용) - 영향받은 행 수 반환"""
        self._check_closed()

        if self._autoflush:
            await self.flush()

        await self._connection.execute(sql, params or {})
        return self._connection.rowcount

    # -------------------------------------------------------------------------
    # Flush & Commit
    # -------------------------------------------------------------------------

    async def flush(self) -> None:
        """변경 사항을 DB에 반영 (커밋 없이)"""
        self._check_closed()

        # INSERT
        for entity in list(self._new):
            await self._do_insert(entity)
        self._new.clear()

        # UPDATE
        for entity in list(self._dirty):
            await self._do_update(entity)
        self._dirty.clear()

        # DELETE
        for entity in list(self._deleted):
            await self._do_delete(entity)
        self._deleted.clear()

    async def commit(self) -> None:
        """변경 사항 커밋"""
        self._check_closed()
        await self.flush()
        await self._connection.commit()

    async def rollback(self) -> None:
        """변경 사항 롤백"""
        self._check_closed()
        await self._connection.rollback()

        self._new.clear()
        self._dirty.clear()
        self._deleted.clear()
        self._identity_map.clear()

    async def close(self) -> None:
        """세션 닫기 및 연결 반환"""
        if not self._closed:
            self._new.clear()
            self._dirty.clear()
            self._deleted.clear()
            self._identity_map.clear()
            # 연결을 풀에 반환
            await self._pool.release_async(self._connection)
            self._closed = True

    def _check_closed(self) -> None:
        if self._closed:
            raise RuntimeError("Session is closed")

    # -------------------------------------------------------------------------
    # Internal Operations
    # -------------------------------------------------------------------------

    async def _do_insert(self, entity: Any) -> None:
        """INSERT 실행"""
        entity_cls = type(entity)
        meta = get_entity_meta(entity_cls)
        if meta is None:
            raise ValueError(f"{entity_cls.__name__} is not an Entity")

        dialect = self.dialect
        if dialect is None:
            raise ValueError("Dialect not available")

        data = entity_to_dict(entity, include_none=False)
        pk_col = meta.primary_key

        if pk_col and pk_col in data:
            pk_column = meta.columns.get(pk_col)
            if pk_column and getattr(pk_column, "auto_increment", False):
                if data.get(pk_col) is None:
                    del data[pk_col]

        columns = list(data.keys())
        sql = dialect.insert_returning_sql(meta, columns)

        await self._connection.execute(sql, data)

        if pk_col and pk_col not in data:
            pk_value = self._connection.lastrowid
            set_pk_value(entity, pk_value)

        pk = get_pk_value(entity)
        if pk is not None:
            self._identity_map[(entity_cls, pk)] = entity

        tracker: DirtyTracker | None = getattr(entity, "__bloom_tracker__", None)
        if tracker:
            tracker.mark_persisted()

    async def _do_update(self, entity: Any) -> None:
        """UPDATE 실행"""
        entity_cls = type(entity)
        meta = get_entity_meta(entity_cls)
        if meta is None:
            raise ValueError(f"{entity_cls.__name__} is not an Entity")

        dialect = self.dialect
        if dialect is None:
            raise ValueError("Dialect not available")

        pk_col = meta.primary_key
        if pk_col is None:
            raise ValueError(f"{entity_cls.__name__} has no primary key")

        pk = get_pk_value(entity)
        if pk is None:
            raise ValueError("Cannot update entity without PK")

        tracker: DirtyTracker | None = getattr(entity, "__bloom_tracker__", None)
        if tracker is None or not tracker.is_dirty:
            return

        dirty_fields = tracker.get_dirty_fields()
        data = {f: getattr(entity, f) for f in dirty_fields}
        data[pk_col] = pk

        sql = dialect.update_sql(meta, dirty_fields, pk_col)
        await self._connection.execute(sql, data)

        tracker.clear()

    async def _do_delete(self, entity: Any) -> None:
        """DELETE 실행"""
        entity_cls = type(entity)
        meta = get_entity_meta(entity_cls)
        if meta is None:
            raise ValueError(f"{entity_cls.__name__} is not an Entity")

        dialect = self.dialect
        if dialect is None:
            raise ValueError("Dialect not available")

        pk_col = meta.primary_key
        if pk_col is None:
            raise ValueError(f"{entity_cls.__name__} has no primary key")

        pk = get_pk_value(entity)
        if pk is None:
            raise ValueError("Cannot delete entity without PK")

        sql = dialect.delete_sql(meta, pk_col)
        await self._connection.execute(sql, {pk_col: pk})

        key = (entity_cls, pk)
        self._identity_map.pop(key, None)

    async def __aenter__(self) -> "AsyncSession":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            await self.rollback()
        await self.close()


# =============================================================================
# Session Factory
# =============================================================================


class SessionFactory:
    """세션 팩토리

    DatabaseBackend를 통해 다양한 데이터베이스를 지원합니다.

    Examples:
        from bloom.db.backends import SQLiteBackend, PostgreSQLBackend

        # SQLite
        backend = SQLiteBackend(":memory:")
        factory = SessionFactory(backend)

        # PostgreSQL
        backend = PostgreSQLBackend("postgresql://user:pass@localhost/mydb")
        factory = SessionFactory(backend)

        with factory.create() as session:
            user = User(name="alice")
            session.add(user)
            session.commit()
    """

    def __init__(
        self,
        backend: DatabaseBackend,
        *,
        autoflush: bool = True,
    ):
        self._autoflush = autoflush
        self._backend = backend

        # Dialect는 백엔드에서 가져옴
        self._dialect = self._backend.dialect

    @property
    def dialect(self) -> Dialect:
        """현재 Dialect 반환"""
        return self._dialect

    @property
    def backend(self) -> DatabaseBackend:
        """현재 Backend 반환"""
        return self._backend

    def _create_connection(self) -> Connection:
        """연결 생성 - 백엔드에서 커넥션을 가져옴"""
        return self._backend.connect()

    def create(self) -> Session:
        """새 세션 생성"""
        connection = self._create_connection()
        return Session(connection, autoflush=self._autoflush)

    async def create_async(self) -> AsyncSession:
        """새 비동기 세션 생성"""
        connection = await self._backend.pool.acquire_async()
        return AsyncSession(
            connection, self._backend.pool, autoflush=self._autoflush
        )

    @contextmanager
    def session(self) -> Iterator[Session]:
        """컨텍스트 매니저로 세션 생성"""
        session = self.create()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @asynccontextmanager
    async def session_async(self) -> AsyncIterator[AsyncSession]:
        """비동기 컨텍스트 매니저로 세션 생성"""
        session = await self.create_async()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    def create_tables(self, *entity_classes: type) -> None:
        """테이블 생성"""
        with self.session() as session:
            for entity_cls in entity_classes:
                meta = get_entity_meta(entity_cls)
                if meta:
                    sql = self._dialect.create_table_sql(meta)
                    session._connection.execute(sql)

    def drop_tables(self, *entity_classes: type) -> None:
        """테이블 삭제"""
        with self.session() as session:
            for entity_cls in entity_classes:
                meta = get_entity_meta(entity_cls)
                if meta:
                    sql = self._dialect.drop_table_sql(meta.table_name)
                    session._connection.execute(sql)
