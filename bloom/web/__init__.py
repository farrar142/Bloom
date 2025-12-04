"""bloom.web - Web Layer Module"""

from typing import TYPE_CHECKING

__all__ = [
    # Types
    "ASGIApp",
    "Scope",
    "Receive",
    "Send",
    "Message",
    # Request/Response
    "Request",
    "Response",
    "JSONResponse",
    "HTMLResponse",
    "PlainTextResponse",
    "StreamingResponse",
    "FileResponse",
    "SSEResponse",
    "SSEEvent",
    # Middleware
    "Middleware",
    "RequestScopeMiddleware",
    "ErrorHandlerMiddleware",
    "CORSMiddleware",
    # Application
    "ASGIApplication",
    # Router
    "Router",
    "Route",
    "RouteMatch",
    # Decorators
    "Controller",
    "RequestMapping",
    "GetMapping",
    "PostMapping",
    "PutMapping",
    "DeleteMapping",
    "PatchMapping",
    # Params
    "PathVariable",
    "Query",
    "RequestBody",
    "RequestField",
    "Header",
    "Cookie",
    "UploadedFile",
    "Authentication",
    # Resolver
    "ParameterResolver",
    "ResolverRegistry",
    # Upload
    "UploadedFileClass",
    "parse_multipart",
    "create_uploaded_file",
    # Error
    "HTTPException",
    "BadRequestError",
    "UnauthorizedError",
    "ForbiddenError",
    "NotFoundError",
    "MethodNotAllowedError",
    "ConflictError",
    "UnprocessableEntityError",
    "TooManyRequestsError",
    "InternalServerError",
    "ValidationError",
    "ExceptionHandler",
    "ExceptionHandlerRegistry",
    "json_error_response",
    # Auth
    "AuthenticationInfo",
    "AnonymousAuthentication",
    "Authenticated",
    # Messaging (WebSocket + STOMP)
    "WebSocketSession",
    "WebSocketHandler",
    "WebSocketEndpoint",
    "WebSocketState",
    "StompFrame",
    "StompCommand",
    "StompProtocol",
    "StompError",
    "MessageMapping",
    "SubscribeMapping",
    "SendTo",
    "MessageController",
    "MessageBroker",
    "SimpleBroker",
    "MessagePayload",
    "DestinationVariable",
    "MessageHeaders",
    "Principal",
    "SessionId",
    "StompMessageHandler",
    "MessageDispatcher",
]


def __getattr__(name: str):
    """Lazy import"""

    # Types
    if name in ("ASGIApp", "Scope", "Receive", "Send", "Message"):
        from . import types

        return getattr(types, name)

    # Request
    if name == "Request":
        from .request import Request

        return Request

    # Response
    if name in (
        "Response",
        "JSONResponse",
        "HTMLResponse",
        "PlainTextResponse",
        "StreamingResponse",
        "FileResponse",
        "SSEResponse",
        "SSEEvent",
    ):
        from . import response

        return getattr(response, name)

    # Middleware
    if name in (
        "Middleware",
        "RequestScopeMiddleware",
        "ErrorHandlerMiddleware",
        "CORSMiddleware",
    ):
        from . import middleware

        return getattr(middleware, name)

    # Application
    if name == "ASGIApplication":
        from .asgi import ASGIApplication

        return ASGIApplication

    # Routing
    if name in (
        "Router",
        "Route",
        "RouteMatch",
        "Controller",
        "RequestMapping",
        "GetMapping",
        "PostMapping",
        "PutMapping",
        "DeleteMapping",
        "PatchMapping",
        "PathVariable",
        "Query",
        "RequestBody",
        "RequestField",
        "Header",
        "Cookie",
        "UploadedFile",
        "Authentication",
        "ParameterResolver",
        "ResolverRegistry",
    ):
        from . import routing

        return getattr(routing, name)

    # Upload
    if name == "UploadedFileClass":
        from .upload import UploadedFile as UploadedFileClass

        return UploadedFileClass

    if name in ("parse_multipart", "create_uploaded_file"):
        from . import upload

        return getattr(upload, name)

    # Error
    if name in (
        "HTTPException",
        "BadRequestError",
        "UnauthorizedError",
        "ForbiddenError",
        "NotFoundError",
        "MethodNotAllowedError",
        "ConflictError",
        "UnprocessableEntityError",
        "TooManyRequestsError",
        "InternalServerError",
        "ValidationError",
        "ExceptionHandler",
        "ExceptionHandlerRegistry",
        "json_error_response",
    ):
        from . import error

        return getattr(error, name)

    # Auth
    if name in ("AuthenticationInfo", "AnonymousAuthentication", "Authenticated"):
        from . import auth

        return getattr(auth, name)

    # Messaging (WebSocket + STOMP)
    if name in (
        "WebSocketSession",
        "WebSocketHandler",
        "WebSocketEndpoint",
        "WebSocketState",
        "StompFrame",
        "StompCommand",
        "StompProtocol",
        "StompError",
        "MessageMapping",
        "SubscribeMapping",
        "SendTo",
        "MessageController",
        "MessageBroker",
        "SimpleBroker",
        "MessagePayload",
        "DestinationVariable",
        "MessageHeaders",
        "Principal",
        "SessionId",
        "StompMessageHandler",
        "MessageDispatcher",
    ):
        from . import messaging

        return getattr(messaging, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# TYPE_CHECKING용 (IDE 지원)
if TYPE_CHECKING:
    from .types import ASGIApp, Scope, Receive, Send, Message
    from .request import Request
    from .response import (
        Response,
        JSONResponse,
        HTMLResponse,
        PlainTextResponse,
        StreamingResponse,
        FileResponse,
        SSEResponse,
        SSEEvent,
    )
    from .middleware import (
        Middleware,
        RequestScopeMiddleware,
        ErrorHandlerMiddleware,
        CORSMiddleware,
    )
    from .asgi import ASGIApplication
    from .routing import (
        Router,
        Route,
        RouteMatch,
        Controller,
        RequestMapping,
        GetMapping,
        PostMapping,
        PutMapping,
        DeleteMapping,
        PatchMapping,
        PathVariable,
        Query,
        RequestBody,
        RequestField,
        Header,
        Cookie,
        UploadedFile,
        Authentication,
        ParameterResolver,
        ResolverRegistry,
    )
    from .upload import (
        UploadedFile as UploadedFileClass,
        parse_multipart,
        create_uploaded_file,
    )
    from .error import (
        HTTPException,
        BadRequestError,
        UnauthorizedError,
        ForbiddenError,
        NotFoundError,
        MethodNotAllowedError,
        ConflictError,
        UnprocessableEntityError,
        TooManyRequestsError,
        InternalServerError,
        ValidationError,
        ExceptionHandler,
        ExceptionHandlerRegistry,
        json_error_response,
    )
    from .auth import AuthenticationInfo, AnonymousAuthentication, Authenticated
    from .messaging import (
        WebSocketSession,
        WebSocketHandler,
        WebSocketEndpoint,
        WebSocketState,
        StompFrame,
        StompCommand,
        StompProtocol,
        StompError,
        MessageMapping,
        SubscribeMapping,
        SendTo,
        MessageController,
        MessageBroker,
        SimpleBroker,
        MessagePayload,
        DestinationVariable,
        MessageHeaders,
        Principal,
        SessionId,
        StompMessageHandler,
        MessageDispatcher,
    )
