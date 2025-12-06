from .web import ASGIApplication


class Application:
    def __init__(self) -> None:
        self.asgi = ASGIApplication()
