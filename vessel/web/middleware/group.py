"""
미들웨어 그룹

관련된 미들웨어들을 그룹화하여 일괄 관리합니다.
그룹 단위로 활성화/비활성화가 가능합니다.

사용 예시:
    ```python
    from vessel.web.middleware import MiddlewareGroup

    # 그룹 생성 및 미들웨어 추가
    auth_group = MiddlewareGroup("auth")
    auth_group.add(jwt_middleware, session_middleware)

    # 개발 환경에서 인증 비활성화
    if is_development:
        auth_group.disable()

    # 그룹 활성화
    auth_group.enable()
    ```

MiddlewareChain에서 사용:
    ```python
    chain = MiddlewareChain()

    # 그룹을 특정 위치에 추가
    security_group = chain.add_group_before(cors_middleware)
    auth_group = chain.add_group_after(auth_middleware, target_group=security_group)
    ```
"""

from .base import Middleware


class MiddlewareGroup:
    """
    미들웨어 그룹 - 순서가 있는 미들웨어 컬렉션

    관련된 미들웨어들을 묶어서 관리합니다.
    그룹 전체를 활성화/비활성화할 수 있습니다.

    Attributes:
        name: 그룹 이름 (디버깅용)
        middlewares: 그룹에 속한 미들웨어 리스트
        enabled: 그룹 활성화 상태

    사용 예시:
        ```python
        # 로깅 관련 미들웨어 그룹
        logging_group = MiddlewareGroup("logging")
        logging_group.add(request_logger, response_logger, error_logger)

        # 프로덕션에서 상세 로깅 비활성화
        if not is_debug:
            logging_group.disable()
        ```
    """

    def __init__(self, name: str = "default"):
        self.name = name
        self.middlewares: list[Middleware] = []
        self.enabled = True

    def add(self, *middlewares: Middleware) -> "MiddlewareGroup":
        """
        미들웨어 추가

        Args:
            *middlewares: 추가할 미들웨어들

        Returns:
            self (메서드 체이닝용)

        Raises:
            TypeError: Middleware 인스턴스가 아닌 경우

        Examples:
            ```python
            group = MiddlewareGroup("security")
            group.add(cors_middleware).add(auth_middleware)

            # 또는 한 번에 여러 개 추가
            group.add(cors, auth, csrf)
            ```
        """
        for middleware in middlewares:
            if not isinstance(middleware, Middleware):
                raise TypeError(f"{middleware} is not a Middleware instance")
            self.middlewares.append(middleware)
        return self

    def disable(self) -> "MiddlewareGroup":
        """
        이 그룹 비활성화

        비활성화된 그룹의 미들웨어는 실행되지 않습니다.

        Returns:
            self (메서드 체이닝용)
        """
        self.enabled = False
        return self

    def enable(self) -> "MiddlewareGroup":
        """
        이 그룹 활성화

        Returns:
            self (메서드 체이닝용)
        """
        self.enabled = True
        return self

    def get_active_middlewares(self) -> list[Middleware]:
        """
        활성화된 미들웨어 목록 반환

        그룹이 비활성화되면 빈 리스트를 반환합니다.

        Returns:
            활성화된 미들웨어 리스트
        """
        return self.middlewares if self.enabled else []

    def __repr__(self) -> str:
        status = "enabled" if self.enabled else "disabled"
        return f"MiddlewareGroup(name={self.name}, middlewares={len(self.middlewares)}, {status})"
