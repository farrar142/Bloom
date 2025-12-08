from typing import Self
from .core import get_container_manager


class Application:
    def __init__(self) -> None:
        self.container_manager = get_container_manager()

    async def ready(self) -> Self:
        await self.container_manager.initialize()
        return self
