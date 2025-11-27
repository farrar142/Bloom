"""파라미터 마커 타입들"""

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


if TYPE_CHECKING:
    type RequestBody[T] = Annotated[T, RequestBodyType[T]]
else:
    RequestBody = RequestBodyType
