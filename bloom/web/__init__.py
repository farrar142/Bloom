"""bloom.web - Web Layer Module"""

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
    # Router
    Router,
    Route,
    RouteMatch,
    # Decorators
    Controller,
    RequestMapping,
    GetMapping,
    PostMapping,
    PutMapping,
    DeleteMapping,
    PatchMapping,
    # Params
    PathVariable,
    Query,
    RequestBody,
    RequestField,
    Header,
    Cookie,
    UploadedFile,
    Authentication,
    # Resolver
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

# Messaging (WebSocket + STOMP)
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
