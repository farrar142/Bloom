"""bloom.core.exceptions - DI Container 예외 정의"""

from typing import Any


class BloomException(Exception):
    """Bloom 프레임워크 기본 예외"""

    pass


class ContainerException(BloomException):
    """컨테이너 관련 예외"""

    pass


class ComponentNotFoundError(ContainerException):
    """컴포넌트를 찾을 수 없음"""

    def __init__(self, cls: type):
        self.cls = cls
        super().__init__(f"Component not found: {cls.__name__}")


class DuplicateComponentError(ContainerException):
    """중복된 컴포넌트 등록"""

    def __init__(self, cls: type):
        self.cls = cls
        super().__init__(f"Component already registered: {cls.__name__}")


class CircularDependencyError(ContainerException):
    """순환 의존성 감지"""

    def __init__(self, cycle: list[type]):
        self.cycle = cycle
        names = " -> ".join(c.__name__ for c in cycle)
        super().__init__(f"Circular dependency detected: {names}")


class DependencyResolutionError(ContainerException):
    """의존성 해결 실패"""

    def __init__(self, cls: type, field: str, expected_type: type):
        self.cls = cls
        self.field = field
        self.expected_type = expected_type
        super().__init__(
            f"Cannot resolve dependency '{field}' of type '{expected_type.__name__}' "
            f"for component '{cls.__name__}'"
        )


class ScopeError(ContainerException):
    """스코프 관련 오류"""

    pass


class RequestScopeError(ScopeError):
    """Request 스코프 외부에서 REQUEST 스코프 컴포넌트 접근"""

    def __init__(self, cls: type):
        self.cls = cls
        super().__init__(
            f"Cannot access REQUEST scoped component '{cls.__name__}' "
            f"outside of request context"
        )


class CallScopeError(ScopeError):
    """Call 스코프 외부에서 CALL 스코프 컴포넌트 접근"""

    def __init__(self, cls: type):
        self.cls = cls
        super().__init__(
            f"Cannot access CALL scoped component '{cls.__name__}' "
            f"outside of @Handler context"
        )


class LifecycleError(BloomException):
    """라이프사이클 관련 오류"""

    def __init__(self, cls: type, phase: str, cause: Exception):
        self.cls = cls
        self.phase = phase
        self.cause = cause
        super().__init__(f"Lifecycle error in '{cls.__name__}' during {phase}: {cause}")


class ConfigurationError(BloomException):
    """설정 관련 오류"""

    pass


class ValueNotFoundError(ConfigurationError):
    """@Value 설정값을 찾을 수 없음"""

    def __init__(self, key: str):
        self.key = key
        super().__init__(f"Configuration value not found: {key}")
