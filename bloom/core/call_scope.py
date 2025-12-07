from contextvars import ContextVar
from typing import overload, Literal, Awaitable, Callable, Any
import asyncio


class CallFrame:
    datas: list

    def __init__(self):
        self.id = id(self)
        self.datas = []

    def __repr__(self) -> str:
        return f"<CallFrame id={self.id} datas={self.datas}>"

    def add_data(self, data: Any) -> None:
        self.datas.append(data)


class CallStackTracker:
    def __init__(self):
        self.__stack: list[CallFrame] = []
        self.__add_event_listeners: list[Callable[[CallFrame], None]] = []
        self.__exit_event_listeners: list[Callable[[CallFrame], None]] = []

    async def add_frame(self, frame: CallFrame) -> CallFrame:
        self.__stack.append(frame)
        await asyncio.gather(
            *[listener(frame) for listener in self.__add_event_listeners]
        )

    async def remove_frame(self, frame: CallFrame) -> None:
        self.__stack.remove(frame)
        await asyncio.gather(
            *[listener(frame) for listener in self.__exit_event_listeners]
        )

    def add_event_listener(self, listener: Callable[[CallFrame], Awaitable]) -> None:
        self.__add_event_listeners.append(listener)

    def exit_event_listener(self, listener: Callable[[CallFrame], Awaitable]) -> None:
        self.__exit_event_listeners.append(listener)

    def remove_event_listener(self, listener: Callable[[CallFrame], None]):
        self.__exit_event_listeners.remove(listener)

    def remove_add_event_listener(self, listener: Callable[[CallFrame], None]):
        self.__add_event_listeners.remove(listener)

    @overload
    async def current_frame(self, required: Literal[True]) -> CallFrame: ...
    @overload
    async def current_frame(self) -> CallFrame | None: ...
    async def current_frame(self, required: bool) -> CallFrame | None:
        if self.__stack:
            return self.__stack[-1]
        if required:
            raise RuntimeError("No active CallFrame in the current CallStack")
        return None

    async def __aenter__(self):
        frame = CallFrame()
        await self.add_frame(frame)
        return frame

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.remove_frame(await self.current_frame(True))


call_stack_tracker_contextvar: ContextVar[CallStackTracker] = ContextVar[
    CallStackTracker
]("call_stack_tracker", default=CallStackTracker())


def call_stack():
    return call_stack_tracker_contextvar.get()
