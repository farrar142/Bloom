"""AsyncSession 테스트"""

import pytest
from bloom.db.session import AsyncSession
from bloom.db.tracker import EntityState

from .conftest import User, Post


class TestAsyncSessionCRUD:
    """AsyncSession CRUD 테스트"""

    @pytest.mark.asyncio
    async def test_add_and_commit(self, async_session: AsyncSession):
        """엔티티 추가 및 커밋"""
        user = User()
        user.name = "alice"
        user.email = "alice@example.com"

        async_session.add(user)
        await async_session.commit()

        # PK가 할당됨
        assert user.id is not None
        assert user.id > 0

    @pytest.mark.asyncio
    async def test_get_by_pk(self, async_session: AsyncSession):
        """PK로 엔티티 조회"""
        # 데이터 삽입
        user = User()
        user.name = "bob"
        user.email = "bob@example.com"
        async_session.add(user)
        await async_session.commit()

        user_id = user.id

        # 조회
        found = await async_session.get(User, user_id)

        assert found is not None
        assert found.name == "bob"
        assert found.email == "bob@example.com"

    @pytest.mark.asyncio
    async def test_get_not_found(self, async_session: AsyncSession):
        """존재하지 않는 엔티티 조회"""
        found = await async_session.get(User, 9999)
        assert found is None

    @pytest.mark.asyncio
    async def test_update(self, async_session: AsyncSession):
        """엔티티 업데이트"""
        # 생성
        user = User()
        user.name = "charlie"
        user.email = "charlie@example.com"
        async_session.add(user)
        await async_session.commit()

        user_id = user.id

        # 수정
        user.name = "charlie_updated"
        await async_session.commit()

        # 다시 조회하여 확인
        found = await async_session.get(User, user_id)
        assert found is not None
        assert found.name == "charlie_updated"

    @pytest.mark.asyncio
    async def test_delete(self, async_session: AsyncSession):
        """엔티티 삭제"""
        # 생성
        user = User()
        user.name = "dave"
        user.email = "dave@example.com"
        async_session.add(user)
        await async_session.commit()

        user_id = user.id

        # 삭제
        async_session.delete(user)
        await async_session.commit()

        # 조회 - 없어야 함
        found = await async_session.get(User, user_id)
        assert found is None


class TestAsyncSessionIdentityMap:
    """Identity Map 테스트"""

    @pytest.mark.asyncio
    async def test_same_pk_returns_same_instance(self, async_session: AsyncSession):
        """같은 PK는 같은 인스턴스 반환"""
        user = User()
        user.name = "eve"
        user.email = "eve@example.com"
        async_session.add(user)
        await async_session.commit()

        user_id = user.id

        # 두 번 조회
        found1 = await async_session.get(User, user_id)
        found2 = await async_session.get(User, user_id)

        # 같은 인스턴스여야 함
        assert found1 is found2


class TestAsyncSessionRelations:
    """관계 테스트"""

    @pytest.mark.asyncio
    async def test_many_to_one(self, async_session: AsyncSession):
        """ManyToOne 관계"""
        # User 생성
        user = User()
        user.name = "frank"
        user.email = "frank@example.com"
        async_session.add(user)
        await async_session.commit()

        # Post 생성
        post = Post()
        post.title = "First Post"
        post.content = "Hello World"
        post.author_id = user.id
        async_session.add(post)
        await async_session.commit()

        # Post 조회 및 관계 확인
        found_post = await async_session.get(Post, post.id)
        assert found_post is not None
        assert found_post.author_id == user.id


class TestAsyncSessionBulkOperations:
    """벌크 작업 테스트"""

    @pytest.mark.asyncio
    async def test_add_all(self, async_session: AsyncSession):
        """여러 엔티티 추가"""
        users = [
            User(),
            User(),
            User(),
        ]
        users[0].name = "user1"
        users[0].email = "user1@example.com"
        users[1].name = "user2"
        users[1].email = "user2@example.com"
        users[2].name = "user3"
        users[2].email = "user3@example.com"

        async_session.add_all(users)
        await async_session.commit()

        # 모든 사용자에 PK 할당됨
        for user in users:
            assert user.id is not None


class TestAsyncSessionRollback:
    """롤백 테스트"""

    @pytest.mark.asyncio
    async def test_rollback_discards_changes(self, async_session: AsyncSession):
        """롤백 시 변경 사항 폐기"""
        user = User()
        user.name = "grace"
        user.email = "grace@example.com"

        async_session.add(user)
        # commit 없이 rollback
        await async_session.rollback()

        # 새 세션에서 조회하면 없어야 함
        # (메모리 DB라 rollback 후 flush 안 된 데이터는 사라짐)
        result = []
        async for row in async_session.execute(
            "SELECT * FROM user WHERE email = :email", {"email": "grace@example.com"}
        ):
            result.append(row)
        assert len(result) == 0
