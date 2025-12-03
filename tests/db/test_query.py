"""Query 테스트"""

import pytest
from bloom.db import Query, Condition, ConditionGroup, OrderBy
from bloom.db.session import AsyncSession

from .conftest import User, Post


class TestQueryBuilder:
    """Query 빌더 테스트"""

    @pytest.mark.asyncio
    async def test_select_all(self, async_session: AsyncSession):
        """전체 조회"""
        # 데이터 생성
        for i in range(3):
            user = User()
            user.name = f"user{i}"
            user.email = f"user{i}@example.com"
            async_session.add(user)
        await async_session.commit()

        # Query로 조회
        query = Query(User).with_session(async_session)
        users = await query.async_all()

        assert len(users) >= 3

    @pytest.mark.asyncio
    async def test_filter_eq(self, async_session: AsyncSession):
        """동등 조건 필터"""
        # 데이터 생성
        user = User()
        user.name = "alice"
        user.email = "alice@example.com"
        async_session.add(user)
        await async_session.commit()

        # 필터 조회
        query = Query(User).with_session(async_session)
        result = await query.filter(Condition("name", "=", "alice")).async_all()

        assert len(result) == 1
        assert result[0].name == "alice"

    @pytest.mark.asyncio
    async def test_filter_like(self, async_session: AsyncSession):
        """LIKE 조건 필터"""
        # 데이터 생성
        for name in ["alice", "bob", "alicia"]:
            user = User()
            user.name = name
            user.email = f"{name}@example.com"
            async_session.add(user)
        await async_session.commit()

        # LIKE 필터
        query = Query(User).with_session(async_session)
        result = await query.filter(Condition("name", "LIKE", "ali%")).async_all()

        assert len(result) == 2
        names = [u.name for u in result]
        assert "alice" in names
        assert "alicia" in names

    @pytest.mark.asyncio
    async def test_filter_gt_lt(self, async_session: AsyncSession):
        """비교 연산 필터"""
        # 데이터 생성
        for i, age in enumerate([20, 25, 30, 35]):
            user = User()
            user.name = f"user{i}"
            user.email = f"user{i}@example.com"
            user.age = age
            async_session.add(user)
        await async_session.commit()

        # 25 초과 필터
        query = Query(User).with_session(async_session)
        result = await query.filter(Condition("age", ">", 25)).async_all()

        assert len(result) == 2
        for user in result:
            assert user.age > 25


class TestQueryConditionGroup:
    """조건 그룹 테스트"""

    @pytest.mark.asyncio
    async def test_and_conditions(self, async_session: AsyncSession):
        """AND 조건"""
        # 데이터 생성
        user1 = User()
        user1.name = "alice"
        user1.email = "alice@example.com"
        user1.age = 25
        user1.is_active = True
        async_session.add(user1)

        user2 = User()
        user2.name = "bob"
        user2.email = "bob@example.com"
        user2.age = 25
        user2.is_active = False
        async_session.add(user2)

        await async_session.commit()

        # AND 조건: age=25 AND is_active=True
        query = Query(User).with_session(async_session)
        result = await query.filter(
            Condition("age", "=", 25), Condition("is_active", "=", 1)
        ).async_all()

        assert len(result) == 1
        assert result[0].name == "alice"

    @pytest.mark.asyncio
    async def test_or_conditions(self, async_session: AsyncSession):
        """OR 조건"""
        # 데이터 생성
        for name in ["alice", "bob", "charlie"]:
            user = User()
            user.name = name
            user.email = f"{name}@example.com"
            async_session.add(user)
        await async_session.commit()

        # OR 조건: name="alice" OR name="bob"
        query = Query(User).with_session(async_session)
        or_cond = ConditionGroup(
            "OR",
            [Condition("name", "=", "alice"), Condition("name", "=", "bob")],
        )
        result = await query.filter(or_cond).async_all()

        assert len(result) == 2
        names = [u.name for u in result]
        assert "alice" in names
        assert "bob" in names
        assert "charlie" not in names


class TestQueryOrdering:
    """정렬 테스트"""

    @pytest.mark.asyncio
    async def test_order_by_asc(self, async_session: AsyncSession):
        """오름차순 정렬"""
        # 데이터 생성 (역순으로)
        for name in ["charlie", "alice", "bob"]:
            user = User()
            user.name = name
            user.email = f"{name}@example.com"
            async_session.add(user)
        await async_session.commit()

        # 이름으로 오름차순 정렬
        query = Query(User).with_session(async_session)
        result = await query.order_by(OrderBy("name", "ASC")).async_all()

        names = [u.name for u in result]
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_order_by_desc(self, async_session: AsyncSession):
        """내림차순 정렬"""
        # 데이터 생성
        for age in [20, 30, 25]:
            user = User()
            user.name = f"user{age}"
            user.email = f"user{age}@example.com"
            user.age = age
            async_session.add(user)
        await async_session.commit()

        # 나이로 내림차순 정렬
        query = Query(User).with_session(async_session)
        result = await query.order_by(OrderBy("age", "DESC")).async_all()

        ages = [u.age for u in result]
        assert ages == sorted(ages, reverse=True)


class TestQueryPagination:
    """페이지네이션 테스트"""

    @pytest.mark.asyncio
    async def test_limit(self, async_session: AsyncSession):
        """LIMIT"""
        # 데이터 생성
        for i in range(5):
            user = User()
            user.name = f"user{i}"
            user.email = f"user{i}@example.com"
            async_session.add(user)
        await async_session.commit()

        # LIMIT 3
        query = Query(User).with_session(async_session)
        result = await query.limit(3).async_all()

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_offset(self, async_session: AsyncSession):
        """OFFSET"""
        # 데이터 생성 (순서대로)
        for i in range(5):
            user = User()
            user.name = f"user{i}"
            user.email = f"user{i}@example.com"
            async_session.add(user)
        await async_session.commit()

        # OFFSET 2, LIMIT 2
        query = Query(User).with_session(async_session)
        result = (
            await query.order_by(OrderBy("name", "ASC")).offset(2).limit(2).async_all()
        )

        assert len(result) == 2


class TestQueryFirst:
    """단일 조회 테스트"""

    @pytest.mark.asyncio
    async def test_first(self, async_session: AsyncSession):
        """첫 번째 결과"""
        # 데이터 생성
        for i in range(3):
            user = User()
            user.name = f"user{i}"
            user.email = f"user{i}@example.com"
            async_session.add(user)
        await async_session.commit()

        # first()
        query = Query(User).with_session(async_session)
        result = await query.order_by(OrderBy("name", "ASC")).async_first()

        assert result is not None

    @pytest.mark.asyncio
    async def test_first_none(self, async_session: AsyncSession):
        """결과 없을 때 first()"""
        query = Query(User).with_session(async_session)
        result = await query.filter(Condition("name", "=", "nonexistent")).async_first()

        assert result is None


class TestQueryCount:
    """집계 테스트"""

    @pytest.mark.asyncio
    async def test_count(self, async_session: AsyncSession):
        """COUNT"""
        # 데이터 생성
        for i in range(5):
            user = User()
            user.name = f"user{i}"
            user.email = f"user{i}@example.com"
            async_session.add(user)
        await async_session.commit()

        # count()
        query = Query(User).with_session(async_session)
        count = await query.async_count()

        assert count >= 5

    @pytest.mark.asyncio
    async def test_exists(self, async_session: AsyncSession):
        """EXISTS"""
        # 데이터 생성
        user = User()
        user.name = "alice"
        user.email = "alice@example.com"
        async_session.add(user)
        await async_session.commit()

        query = Query(User).with_session(async_session)

        # 존재하는 경우
        exists = await query.filter(Condition("name", "=", "alice")).async_exists()
        assert exists is True

        # 존재하지 않는 경우
        not_exists = await query.filter(Condition("name", "=", "nobody")).async_exists()
        assert not_exists is False
