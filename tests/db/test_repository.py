"""Repository 테스트"""

import pytest
from typing import Generic, TypeVar
from bloom.db import Repository
from bloom.db.session import AsyncSession

from .conftest import User, Post


# =============================================================================
# Test Repository 정의
# =============================================================================


class UserRepository(Repository[User, int]):
    """User Repository"""

    async def find_by_email_async(self, email: str) -> User | None:
        """이메일로 사용자 조회"""
        session = self._get_async_session()
        async for row in session.execute(
            "SELECT * FROM user WHERE email = :email", {"email": email}
        ):
            from bloom.db.entity import dict_to_entity

            return dict_to_entity(User, dict(row))
        return None

    async def find_active_users_async(self) -> list[User]:
        """활성 사용자 조회"""
        session = self._get_async_session()
        rows = []
        async for row in session.execute("SELECT * FROM user WHERE is_active = 1", {}):
            rows.append(row)

        from bloom.db.entity import dict_to_entity

        return [dict_to_entity(User, dict(row)) for row in rows]


class PostRepository(Repository[Post, int]):
    """Post Repository"""

    async def find_by_author_async(self, author_id: int) -> list[Post]:
        """작성자로 게시글 조회"""
        session = self._get_async_session()
        rows = []
        async for row in session.execute(
            "SELECT * FROM post WHERE author_id = :author_id",
            {"author_id": author_id},
        ):
            rows.append(row)

        from bloom.db.entity import dict_to_entity

        return [dict_to_entity(Post, dict(row)) for row in rows]


# =============================================================================
# Tests
# =============================================================================


class TestRepositoryCRUD:
    """Repository CRUD 테스트"""

    @pytest.mark.asyncio
    async def test_save_async(self, async_session: AsyncSession):
        """저장 테스트"""
        repo = UserRepository()
        repo.async_session = async_session

        user = User()
        user.name = "alice"
        user.email = "alice@example.com"

        saved = await repo.save_async(user)
        await async_session.commit()

        assert saved.id is not None
        assert saved.id > 0

    @pytest.mark.asyncio
    async def test_find_by_id_async(self, async_session: AsyncSession):
        """ID로 조회 테스트"""
        repo = UserRepository()
        repo.async_session = async_session

        # 저장
        user = User()
        user.name = "bob"
        user.email = "bob@example.com"
        await repo.save_async(user)
        await async_session.commit()

        user_id = user.id

        # 조회
        found = await repo.find_by_id_async(user_id)

        assert found is not None
        assert found.name == "bob"

    @pytest.mark.asyncio
    async def test_find_all_async(self, async_session: AsyncSession):
        """전체 조회 테스트"""
        repo = UserRepository()
        repo.async_session = async_session

        # 여러 사용자 저장
        for i in range(3):
            user = User()
            user.name = f"user{i}"
            user.email = f"user{i}@example.com"
            await repo.save_async(user)

        await async_session.commit()

        # 전체 조회
        users = await repo.find_all_async()

        assert len(users) >= 3

    @pytest.mark.asyncio
    async def test_delete_async(self, async_session: AsyncSession):
        """삭제 테스트"""
        repo = UserRepository()
        repo.async_session = async_session

        # 저장
        user = User()
        user.name = "charlie"
        user.email = "charlie@example.com"
        await repo.save_async(user)
        await async_session.commit()

        user_id = user.id

        # 삭제
        await repo.delete_async(user)
        await async_session.commit()

        # 조회 - 없어야 함
        found = await repo.find_by_id_async(user_id)
        assert found is None

    @pytest.mark.asyncio
    async def test_delete_by_id_async(self, async_session: AsyncSession):
        """ID로 삭제 테스트"""
        repo = UserRepository()
        repo.async_session = async_session

        # 저장
        user = User()
        user.name = "dave"
        user.email = "dave@example.com"
        await repo.save_async(user)
        await async_session.commit()

        user_id = user.id

        # ID로 삭제
        deleted = await repo.delete_by_id_async(user_id)
        await async_session.commit()

        assert deleted is True

        # 조회 - 없어야 함
        found = await repo.find_by_id_async(user_id)
        assert found is None


class TestRepositoryCustomMethods:
    """커스텀 Repository 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_find_by_email(self, async_session: AsyncSession):
        """이메일로 조회"""
        repo = UserRepository()
        repo.async_session = async_session

        # 저장
        user = User()
        user.name = "eve"
        user.email = "eve@example.com"
        await repo.save_async(user)
        await async_session.commit()

        # 커스텀 메서드로 조회
        found = await repo.find_by_email_async("eve@example.com")

        assert found is not None
        assert found.name == "eve"

    @pytest.mark.asyncio
    async def test_find_active_users(self, async_session: AsyncSession):
        """활성 사용자 조회"""
        repo = UserRepository()
        repo.async_session = async_session

        # 활성/비활성 사용자 저장
        active_user = User()
        active_user.name = "active"
        active_user.email = "active@example.com"
        active_user.is_active = True
        await repo.save_async(active_user)

        inactive_user = User()
        inactive_user.name = "inactive"
        inactive_user.email = "inactive@example.com"
        inactive_user.is_active = False
        await repo.save_async(inactive_user)

        await async_session.commit()

        # 활성 사용자만 조회
        active_users = await repo.find_active_users_async()

        # active만 포함, inactive 제외
        names = [u.name for u in active_users]
        assert "active" in names
        assert "inactive" not in names


class TestPostRepository:
    """Post Repository 테스트"""

    @pytest.mark.asyncio
    async def test_find_by_author(self, async_session: AsyncSession):
        """작성자로 게시글 조회"""
        user_repo = UserRepository()
        user_repo.async_session = async_session
        post_repo = PostRepository()
        post_repo.async_session = async_session

        # 사용자 생성
        user = User()
        user.name = "author"
        user.email = "author@example.com"
        await user_repo.save_async(user)
        await async_session.commit()

        # 게시글 생성
        for i in range(3):
            post = Post()
            post.title = f"Post {i}"
            post.content = f"Content {i}"
            post.author_id = user.id
            await post_repo.save_async(post)

        await async_session.commit()

        # 작성자로 조회
        posts = await post_repo.find_by_author_async(user.id)

        assert len(posts) == 3
        for post in posts:
            assert post.author_id == user.id
