"""DB 테스트용 공통 fixture

SQLite 비동기 백엔드 메모리 모드를 사용합니다.
"""

import pytest
from typing import AsyncGenerator

from bloom.db import (
    Entity,
    Column,
    PrimaryKey,
    StringColumn,
    IntegerColumn,
    BooleanColumn,
    ManyToOne,
    OneToMany,
    FetchType,
)
from bloom.db.backends.sqlite import SQLiteBackend
from bloom.db.session import SessionFactory, AsyncSession


# =============================================================================
# Test Entities
# =============================================================================


@Entity
class User:
    """테스트용 User 엔티티"""

    id = PrimaryKey[int](auto_increment=True)
    name = StringColumn(nullable=False)
    email = StringColumn(nullable=False, unique=True)
    age = IntegerColumn(default=0)
    is_active = BooleanColumn(default=True)

    posts = OneToMany["Post"](
        target="Post",
        foreign_key="author_id",
        fetch=FetchType.LAZY,
    )


@Entity
class Post:
    """테스트용 Post 엔티티"""

    id = PrimaryKey[int](auto_increment=True)
    title = StringColumn(nullable=False)
    content = StringColumn(nullable=True)
    view_count = IntegerColumn(default=0)

    author_id = IntegerColumn(nullable=False)
    author = ManyToOne["User"](
        target=User,
        foreign_key="author_id",
        fetch=FetchType.LAZY,
    )


@Entity
class Comment:
    """테스트용 Comment 엔티티"""

    id = PrimaryKey[int](auto_increment=True)
    content = StringColumn(nullable=False)

    post_id = IntegerColumn(nullable=False)
    post = ManyToOne["Post"](
        target=Post,
        foreign_key="post_id",
        fetch=FetchType.LAZY,
    )

    user_id = IntegerColumn(nullable=False)
    user = ManyToOne["User"](
        target=User,
        foreign_key="user_id",
        fetch=FetchType.LAZY,
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sqlite_backend() -> SQLiteBackend:
    """SQLite 메모리 백엔드"""
    return SQLiteBackend(":memory:")


@pytest.fixture
def session_factory(sqlite_backend: SQLiteBackend) -> SessionFactory:
    """세션 팩토리"""
    return SessionFactory(sqlite_backend)


@pytest.fixture
async def async_session(
    session_factory: SessionFactory,
) -> AsyncGenerator[AsyncSession, None]:
    """비동기 세션 (테이블 자동 생성 포함)"""
    session = await session_factory.create_async()
    try:
        # 테이블 생성
        await _create_tables(session)
        yield session
    finally:
        # 명시적으로 연결 닫기
        try:
            await session.rollback()
        except Exception:
            pass
        try:
            await session._connection.close()
        except Exception:
            pass


async def _create_tables(session: AsyncSession) -> None:
    """테스트용 테이블 생성"""
    # User 테이블
    await session._connection.execute(
        """
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            age INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        )
    """
    )

    # Post 테이블
    await session._connection.execute(
        """
        CREATE TABLE IF NOT EXISTS post (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT,
            view_count INTEGER DEFAULT 0,
            author_id INTEGER NOT NULL,
            FOREIGN KEY (author_id) REFERENCES user(id)
        )
    """
    )

    # Comment 테이블
    await session._connection.execute(
        """
        CREATE TABLE IF NOT EXISTS comment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            FOREIGN KEY (post_id) REFERENCES post(id),
            FOREIGN KEY (user_id) REFERENCES user(id)
        )
    """
    )

    await session.commit()
