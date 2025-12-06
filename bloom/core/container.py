from .manager import get_container_registry


class Container[T]:
    instance: T | None
    kls: type[T]

    def __init__(self, kls: type[T]):
        self.kls = kls
        self.instance = None

    """의존성 주입 컨테이너의 기본 클래스"""

    async def initialize(self) -> T:
        """컨테이너 초기화 메서드 (비동기)"""
        return self.kls()

    async def shutdown(self) -> None:
        """컨테이너 종료 메서드 (비동기)"""
