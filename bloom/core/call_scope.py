from contextvars import ContextVar


call_scope_contexts = ContextVar[list["CallFrame"]](
    "current_call_scope", default=list()
)


class CallFrame:
    def __init__(self):
        self.id = id(self)

    def __repr__(self):
        return f"<CallFrame id={self.id}>"


class CallScope:
    def __init__(self):
        self.frames = call_scope_contexts.get()
        self.frame = CallFrame()

    async def __aenter__(self) -> "CallScope":
        self.frames.append(self.frame)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self.frames.pop()
