"""파라미터 마커 타입들"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, TypeVar

T = TypeVar("T")


class RequestBodyType[T]:
    """
    요청 바디 마커 타입

    사용법:
        @Post("/users")
        async def create(self, data: RequestBody[UserData]) -> dict:
            # data는 UserData 인스턴스
            return {"username": data.username}
    """

    def __class_getitem__(cls, item: type[T]):
        """제네릭 타입 지원"""
        # 실제로는 타입 힌트로만 사용됨
        return Annotated[cls, item]


@dataclass
class KeyValue:
    """
    키-값 쌍을 나타내는 기본 클래스

    Attributes:
        key: 원본 키 (헤더명, 쿠키명 등)
        value: 값
    """

    key: str
    value: str

    def __str__(self) -> str:
        return self.value


class HttpHeader(KeyValue):
    """
    HTTP 헤더 값

    사용법:
        # 파라미터 이름으로 헤더 키 추론 (user_agent -> user-agent)
        async def handler(self, user_agent: HttpHeader) -> str:
            print(user_agent.key)    # "user-agent"
            print(user_agent.value)  # "Mozilla/5.0..."

        # 정확한 헤더 키 지정
        async def handler(self, ua: HttpHeader["User-Agent"]) -> str:
            print(ua.key)    # "User-Agent"
            print(ua.value)  # "Mozilla/5.0..."
    """

    def __class_getitem__(cls, header_name: str):
        """헤더 이름 지정"""
        return Annotated[cls, header_name]


class HttpCookie(KeyValue):
    """
    HTTP 쿠키 값

    사용법:
        # 파라미터 이름으로 쿠키 키 추론
        async def handler(self, session_id: HttpCookie) -> str:
            print(session_id.key)    # "session_id"
            print(session_id.value)  # "abc123"

        # 정확한 쿠키 키 지정
        async def handler(self, sid: HttpCookie["session_id"]) -> str:
            print(sid.key)    # "session_id"
            print(sid.value)  # "abc123"
    """

    def __class_getitem__(cls, cookie_name: str):
        """쿠키 이름 지정"""
        return Annotated[cls, cookie_name]


# 런타임 alias (RequestBodyType을 RequestBody로 사용)
RequestBody = RequestBodyType

if TYPE_CHECKING:
    # 타입 체커용 더 정확한 타입
    type RequestBody[T] = Annotated[T, RequestBodyType[T]]
