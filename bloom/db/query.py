"""Query Builder - QueryDSL-style type-safe query builder"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar, Self, TYPE_CHECKING, Callable, Iterator
from copy import copy

from .expressions import Condition, ConditionGroup, OrderBy, FieldExpression
from .entity import EntityMeta, get_entity_meta, dict_to_entity

if TYPE_CHECKING:
    from .session import Session, AsyncSession
    from .columns import Column

T = TypeVar("T")


# =============================================================================
# Query Result
# =============================================================================


@dataclass
class QueryResult(Generic[T]):
    """쿼리 결과 래퍼

    지연 로딩과 다양한 결과 접근 방식을 제공합니다.
    """

    _session: Session
    _entity_cls: type[T]
    _sql: str
    _params: dict[str, Any]
    _results: list[T] | None = None
    _executed: bool = False

    def _execute(self) -> list[T]:
        """쿼리 실행 (lazy)"""
        if not self._executed:
            rows = self._session.execute(self._sql, self._params)
            self._results = [
                self._bind_session(dict_to_entity(self._entity_cls, dict(row)))
                for row in rows
            ]
            # Eager 로딩 처리
            self._load_eager_relations()
            self._executed = True
        return self._results or []

    def _bind_session(self, entity: T) -> T:
        """엔티티에 Session 바인딩"""
        object.__setattr__(entity, "__bloom_session__", self._session)
        return entity

    def _load_eager_relations(self) -> None:
        """Eager 관계 로딩"""
        if not self._results:
            return

        from .columns import OneToMany, FetchType

        # __bloom_relations__ 확인
        relations = getattr(self._entity_cls, "__bloom_relations__", {})
        for rel_name, descriptor in relations.items():
            if isinstance(descriptor, OneToMany) and descriptor.is_eager:
                self._load_one_to_many_eager(descriptor, rel_name)

    def _load_one_to_many_eager(self, descriptor: Any, rel_name: str) -> None:
        """OneToMany Eager 로딩

        N+1 문제를 방지하기 위해 IN 쿼리로 한 번에 로딩
        """
        if not self._results:
            return

        from .columns import OneToMany

        # 부모 PK 수집
        pk_name = getattr(self._entity_cls, "__bloom_pk__", "id")
        pk_values = [
            getattr(entity, pk_name)
            for entity in self._results
            if getattr(entity, pk_name, None) is not None
        ]

        if not pk_values:
            return

        # 타겟 클래스 resolve
        target_cls = descriptor._resolve_target()
        fk_name = descriptor.foreign_key
        fk_column = getattr(target_cls, fk_name, None)
        if fk_column is None:
            return

        # IN 쿼리로 모든 자식 한 번에 조회
        children = (
            Query(target_cls)
            .filter(fk_column.in_(pk_values))
            .with_session(self._session)
            .all()
        )

        # 부모별로 그룹핑
        children_by_parent: dict[Any, list[Any]] = {pk: [] for pk in pk_values}
        for child in children:
            parent_pk = getattr(child, fk_name, None)
            if parent_pk in children_by_parent:
                children_by_parent[parent_pk].append(child)

        # 각 부모에 자식 데이터 설정
        for entity in self._results:
            pk = getattr(entity, pk_name, None)
            if pk is not None:
                descriptor.set_loaded_data(entity, children_by_parent.get(pk, []))

    def all(self) -> list[T]:
        """모든 결과 반환"""
        return self._execute()

    def first(self) -> T | None:
        """첫 번째 결과 또는 None"""
        results = self._execute()
        return results[0] if results else None

    def one(self) -> T:
        """정확히 하나의 결과 (없거나 여러 개면 예외)"""
        results = self._execute()
        if len(results) == 0:
            raise ValueError("No result found")
        if len(results) > 1:
            raise ValueError(f"Expected 1 result, got {len(results)}")
        return results[0]

    def one_or_none(self) -> T | None:
        """하나의 결과 또는 None (여러 개면 예외)"""
        results = self._execute()
        if len(results) > 1:
            raise ValueError(f"Expected 0 or 1 result, got {len(results)}")
        return results[0] if results else None

    def count(self) -> int:
        """결과 수"""
        return len(self._execute())

    def exists(self) -> bool:
        """결과 존재 여부"""
        return len(self._execute()) > 0

    def __iter__(self) -> Iterator[T]:
        return iter(self._execute())

    def __len__(self) -> int:
        return len(self._execute())

    def __bool__(self) -> bool:
        return self.exists()


# =============================================================================
# Query Builder
# =============================================================================


@dataclass
class Query(Generic[T]):
    """QueryDSL 스타일 쿼리 빌더

    타입 안전한 쿼리 작성을 지원합니다.

    Examples:
        # 기본 조회
        query = Query(User).filter(User.name == "alice").first()

        # 복합 조건
        query = (
            Query(User)
            .filter(User.age > 18)
            .filter((User.status == "active") | (User.role == "admin"))
            .order_by(User.name.asc())
            .limit(10)
        )

        # 실행
        users = query.with_session(session).all()
    """

    entity_cls: type[T]
    _conditions: list[Condition | ConditionGroup] = field(default_factory=list)
    _order_by: list[OrderBy] = field(default_factory=list)
    _limit: int | None = None
    _offset: int | None = None
    _select_columns: list[str] | None = None
    _session: Session | None = None
    _async_session: AsyncSession | None = None

    def __post_init__(self) -> None:
        self._meta = get_entity_meta(self.entity_cls)
        if self._meta is None:
            raise ValueError(f"{self.entity_cls.__name__} is not an Entity")

    def with_session(self, session: Session | AsyncSession) -> Self:
        """세션 설정 (동기/비동기 모두 지원)"""
        from .session import AsyncSession as AsyncSessionClass

        new_query = copy(self)
        if isinstance(session, AsyncSessionClass):
            new_query._async_session = session
            new_query._session = None
        else:
            new_query._session = session
            new_query._async_session = None
        return new_query

    def filter(self, *conditions: Condition | ConditionGroup) -> Self:
        """WHERE 조건 추가 (AND)

        Examples:
            query.filter(User.name == "alice")
            query.filter(User.age > 18, User.status == "active")
        """
        new_query = copy(self)
        new_query._conditions = [*self._conditions, *conditions]
        return new_query

    def filter_by(self, **kwargs: Any) -> Self:
        """키워드 인자로 WHERE 조건 추가

        Examples:
            query.filter_by(name="alice", age=25)
        """
        conditions = [Condition(k, "=", v) for k, v in kwargs.items()]
        return self.filter(*conditions)

    def order_by(self, *orders: OrderBy | FieldExpression[Any]) -> Self:
        """ORDER BY 추가

        Examples:
            query.order_by(User.name.asc(), User.age.desc())
            query.order_by(User.created_at)  # 기본 ASC
        """
        new_query = copy(self)
        order_list: list[OrderBy] = []
        for o in orders:
            if isinstance(o, OrderBy):
                order_list.append(o)
            elif isinstance(o, FieldExpression):
                order_list.append(o.asc())
        new_query._order_by = [*self._order_by, *order_list]
        return new_query

    def limit(self, n: int) -> Self:
        """LIMIT 설정"""
        new_query = copy(self)
        new_query._limit = n
        return new_query

    def offset(self, n: int) -> Self:
        """OFFSET 설정"""
        new_query = copy(self)
        new_query._offset = n
        return new_query

    def select(self, *columns: str | FieldExpression[Any]) -> Self:
        """SELECT 컬럼 지정

        Examples:
            query.select("id", "name")
            query.select(User.id, User.name)
        """
        new_query = copy(self)
        col_names: list[str] = []
        for c in columns:
            if isinstance(c, str):
                col_names.append(c)
            elif isinstance(c, FieldExpression):
                col_names.append(c.name)
        new_query._select_columns = col_names
        return new_query

    def _build_where(self) -> tuple[str | None, dict[str, Any]]:
        """WHERE 절 생성"""
        if not self._conditions:
            return None, {}

        if len(self._conditions) == 1:
            cond = self._conditions[0]
            return cond.to_sql("w")

        # 여러 조건은 AND로 결합
        group = ConditionGroup("AND", list(self._conditions))
        return group.to_sql("w")

    def _build_order_by(self) -> list[str]:
        """ORDER BY 절 생성"""
        return [o.to_sql() for o in self._order_by]

    def build(self) -> tuple[str, dict[str, Any]]:
        """SQL 쿼리 생성

        Returns:
            (sql, params)
        """
        if self._meta is None:
            raise ValueError("Entity meta not found")

        where_sql, params = self._build_where()
        order_by = self._build_order_by()

        columns = self._select_columns or self._meta.column_names
        cols_str = ", ".join(f'"{c}"' for c in columns)

        sql = f'SELECT {cols_str} FROM "{self._meta.table_name}"'

        if where_sql:
            sql += f" WHERE {where_sql}"
        if order_by:
            sql += f" ORDER BY {', '.join(order_by)}"
        if self._limit is not None:
            sql += f" LIMIT {self._limit}"
        if self._offset is not None:
            sql += f" OFFSET {self._offset}"

        return sql, params

    def _ensure_session(self) -> Session:
        """동기 세션 확인"""
        if self._session is None:
            raise ValueError("No session. Call with_session() first.")
        return self._session

    def _ensure_async_session(self) -> AsyncSession:
        """비동기 세션 확인"""
        if self._async_session is None:
            raise ValueError(
                "No async session. Call with_session(async_session) first."
            )
        return self._async_session

    # -------------------------------------------------------------------------
    # 동기 실행 메서드
    # -------------------------------------------------------------------------

    def all(self) -> list[T]:
        """모든 결과 반환"""
        session = self._ensure_session()
        sql, params = self.build()
        rows = session.execute(sql, params)
        results = [
            self._bind_session(dict_to_entity(self.entity_cls, dict(row)), session)
            for row in rows
        ]
        # Eager 로딩 처리
        self._load_eager_relations(results, session)
        return results

    def _bind_session(self, entity: T, session: Session) -> T:
        """엔티티에 Session 바인딩"""
        object.__setattr__(entity, "__bloom_session__", session)
        return entity

    def _load_eager_relations(self, results: list[T], session: Session) -> None:
        """Eager 관계 로딩"""
        if not results:
            return

        from .columns import OneToMany

        # __bloom_relations__ 확인
        relations = getattr(self.entity_cls, "__bloom_relations__", {})
        for rel_name, descriptor in relations.items():
            if isinstance(descriptor, OneToMany) and descriptor.is_eager:
                self._load_one_to_many_eager(descriptor, results, session)

    def _load_one_to_many_eager(
        self, descriptor: Any, results: list[T], session: Session
    ) -> None:
        """OneToMany Eager 로딩 (N+1 방지를 위해 IN 쿼리 사용)"""
        if not results:
            return

        # 부모 PK 수집
        pk_name = getattr(self.entity_cls, "__bloom_pk__", "id")
        pk_values = [
            getattr(entity, pk_name)
            for entity in results
            if getattr(entity, pk_name, None) is not None
        ]

        if not pk_values:
            return

        # 타겟 클래스 resolve
        target_cls = descriptor._resolve_target()
        fk_name = descriptor.foreign_key
        fk_column = getattr(target_cls, fk_name, None)
        if fk_column is None:
            return

        # IN 쿼리로 모든 자식 한 번에 조회
        children = (
            Query(target_cls)
            .filter(fk_column.in_(pk_values))
            .with_session(session)
            .all()
        )

        # 부모별로 그룹핑
        children_by_parent: dict[Any, list[Any]] = {pk: [] for pk in pk_values}
        for child in children:
            parent_pk = getattr(child, fk_name, None)
            if parent_pk in children_by_parent:
                children_by_parent[parent_pk].append(child)

        # 각 부모에 자식 데이터 설정
        for entity in results:
            pk = getattr(entity, pk_name, None)
            if pk is not None:
                descriptor.set_loaded_data(entity, children_by_parent.get(pk, []))

    def first(self) -> T | None:
        """첫 번째 결과"""
        return self.limit(1).all()[0] if self.limit(1).all() else None

    def one(self) -> T:
        """정확히 하나"""
        results = self.all()
        if len(results) == 0:
            raise ValueError("No result found")
        if len(results) > 1:
            raise ValueError(f"Expected 1 result, got {len(results)}")
        return results[0]

    def one_or_none(self) -> T | None:
        """하나 또는 None"""
        results = self.limit(2).all()
        if len(results) > 1:
            raise ValueError(f"Expected 0 or 1 result, got {len(results)}")
        return results[0] if results else None

    def count(self) -> int:
        """결과 수"""
        session = self._ensure_session()
        if self._meta is None:
            raise ValueError("Entity meta not found")

        where_sql, params = self._build_where()
        sql = f'SELECT COUNT(*) as cnt FROM "{self._meta.table_name}"'
        if where_sql:
            sql += f" WHERE {where_sql}"

        rows = session.execute(sql, params)
        row = next(iter(rows), None)
        return row["cnt"] if row else 0

    def exists(self) -> bool:
        """존재 여부"""
        return self.limit(1).count() > 0

    def delete(self) -> int:
        """조건에 맞는 레코드 삭제

        Returns:
            삭제된 행 수
        """
        session = self._ensure_session()
        if self._meta is None:
            raise ValueError("Entity meta not found")

        where_sql, params = self._build_where()
        sql = f'DELETE FROM "{self._meta.table_name}"'
        if where_sql:
            sql += f" WHERE {where_sql}"

        return session.execute_update(sql, params)

    def update(self, **values: Any) -> int:
        """조건에 맞는 레코드 업데이트

        Returns:
            업데이트된 행 수
        """
        session = self._ensure_session()
        if self._meta is None:
            raise ValueError("Entity meta not found")

        where_sql, params = self._build_where()

        set_parts: list[str] = []
        for i, (k, v) in enumerate(values.items()):
            param_name = f"set_{i}"
            set_parts.append(f'"{k}" = :{param_name}')
            params[param_name] = v

        sql = f'UPDATE "{self._meta.table_name}" SET {", ".join(set_parts)}'
        if where_sql:
            sql += f" WHERE {where_sql}"

        return session.execute_update(sql, params)

    def __iter__(self) -> Iterator[T]:
        return iter(self.all())

    def __repr__(self) -> str:
        sql, params = self.build()
        return f"Query({sql!r}, params={params})"

    # -------------------------------------------------------------------------
    # 비동기 실행 메서드
    # -------------------------------------------------------------------------

    async def async_all(self) -> list[T]:
        """[Async] 모든 결과 반환"""
        session = self._ensure_async_session()
        sql, params = self.build()
        rows = [row async for row in session.execute(sql, params)]
        results = [
            self._bind_async_session(
                dict_to_entity(self.entity_cls, dict(row)), session
            )
            for row in rows
        ]
        # Eager 로딩 처리
        await self._async_load_eager_relations(results, session)
        return results

    def _bind_async_session(self, entity: T, session: AsyncSession) -> T:
        """엔티티에 AsyncSession 바인딩"""
        object.__setattr__(entity, "__bloom_session__", session)
        return entity

    async def _async_load_eager_relations(
        self, results: list[T], session: AsyncSession
    ) -> None:
        """[Async] Eager 관계 로딩"""
        if not results:
            return

        from .columns import OneToMany

        relations = getattr(self.entity_cls, "__bloom_relations__", {})
        for rel_name, descriptor in relations.items():
            if isinstance(descriptor, OneToMany) and descriptor.is_eager:
                await self._async_load_one_to_many_eager(descriptor, results, session)

    async def _async_load_one_to_many_eager(
        self, descriptor: Any, results: list[T], session: AsyncSession
    ) -> None:
        """[Async] OneToMany Eager 로딩 (N+1 방지를 위해 IN 쿼리 사용)"""
        if not results:
            return

        pk_name = getattr(self.entity_cls, "__bloom_pk__", "id")
        pk_values = [
            getattr(entity, pk_name)
            for entity in results
            if getattr(entity, pk_name, None) is not None
        ]

        if not pk_values:
            return

        target_cls = descriptor._resolve_target()
        fk_name = descriptor.foreign_key
        fk_column = getattr(target_cls, fk_name, None)
        if fk_column is None:
            return

        # IN 쿼리로 모든 자식 한 번에 조회
        children = await (
            Query(target_cls)
            .filter(fk_column.in_(pk_values))
            .with_session(session)
            .async_all()
        )

        # 부모별로 그룹핑
        children_by_parent: dict[Any, list[Any]] = {pk: [] for pk in pk_values}
        for child in children:
            parent_pk = getattr(child, fk_name, None)
            if parent_pk in children_by_parent:
                children_by_parent[parent_pk].append(child)

        # 각 부모에 자식 데이터 설정
        for entity in results:
            pk = getattr(entity, pk_name, None)
            if pk is not None:
                descriptor.set_loaded_data(entity, children_by_parent.get(pk, []))

    async def async_first(self) -> T | None:
        """[Async] 첫 번째 결과"""
        results = await self.limit(1).async_all()
        return results[0] if results else None

    async def async_one(self) -> T:
        """[Async] 정확히 하나"""
        results = await self.async_all()
        if len(results) == 0:
            raise ValueError("No result found")
        if len(results) > 1:
            raise ValueError(f"Expected 1 result, got {len(results)}")
        return results[0]

    async def async_one_or_none(self) -> T | None:
        """[Async] 하나 또는 None"""
        results = await self.limit(2).async_all()
        if len(results) > 1:
            raise ValueError(f"Expected 0 or 1 result, got {len(results)}")
        return results[0] if results else None

    async def async_count(self) -> int:
        """[Async] 결과 수"""
        session = self._ensure_async_session()
        if self._meta is None:
            raise ValueError("Entity meta not found")

        where_sql, params = self._build_where()
        sql = f'SELECT COUNT(*) as cnt FROM "{self._meta.table_name}"'
        if where_sql:
            sql += f" WHERE {where_sql}"

        rows = [row async for row in session.execute(sql, params)]
        return rows[0]["cnt"] if rows else 0

    async def async_exists(self) -> bool:
        """[Async] 존재 여부"""
        return await self.limit(1).async_count() > 0

    async def async_delete(self) -> int:
        """[Async] 조건에 맞는 레코드 삭제"""
        session = self._ensure_async_session()
        if self._meta is None:
            raise ValueError("Entity meta not found")

        where_sql, params = self._build_where()
        sql = f'DELETE FROM "{self._meta.table_name}"'
        if where_sql:
            sql += f" WHERE {where_sql}"

        return await session.execute_update(sql, params)

    async def async_update(self, **values: Any) -> int:
        """[Async] 조건에 맞는 레코드 업데이트"""
        session = self._ensure_async_session()
        if self._meta is None:
            raise ValueError("Entity meta not found")

        where_sql, params = self._build_where()

        set_parts: list[str] = []
        for i, (k, v) in enumerate(values.items()):
            param_name = f"set_{i}"
            set_parts.append(f'"{k}" = :{param_name}')
            params[param_name] = v

        sql = f'UPDATE "{self._meta.table_name}" SET {", ".join(set_parts)}'
        if where_sql:
            sql += f" WHERE {where_sql}"

        return await session.execute_update(sql, params)


# =============================================================================
# QueryBuilder Factory
# =============================================================================


class QueryBuilder:
    """쿼리 빌더 팩토리

    Examples:
        qb = QueryBuilder(session)
        users = qb.select(User).filter(User.age > 18).all()
    """

    def __init__(self, session: Session):
        self._session = session

    def select(self, entity_cls: type[T]) -> Query[T]:
        """SELECT 쿼리 시작"""
        return Query(entity_cls).with_session(self._session)

    def from_(self, entity_cls: type[T]) -> Query[T]:
        """FROM 쿼리 시작 (select의 별칭)"""
        return self.select(entity_cls)

    def query(self, entity_cls: type[T]) -> Query[T]:
        """쿼리 시작"""
        return self.select(entity_cls)
