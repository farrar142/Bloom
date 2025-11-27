"""파라미터 리졸버 베이스 클래스"""

from abc import ABC, abstractmethod
from typing import Any, get_origin, get_args

from vessel.web.http import HttpRequest


class ParameterResolver(ABC):
    """
    HTTP 핸들러 파라미터를 해석하는 베이스 클래스

    각 리졸버는 특정 타입의 파라미터를 처리할 수 있는지 확인하고,
    HttpRequest로부터 해당 파라미터 값을 추출합니다.
    """

    @abstractmethod
    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        """
        이 리졸버가 해당 파라미터를 처리할 수 있는지 확인

        Args:
            param_name: 파라미터 이름
            param_type: 파라미터 타입 (전체 타입, 예: RequestBody[UserData])
            origin: 제네릭 origin (예: RequestBody)

        Returns:
            처리 가능 여부
        """
        ...

    @abstractmethod
    async def resolve(
        self,
        param_name: str,
        param_type: type,
        request: HttpRequest,
        path_params: dict[str, str],
    ) -> Any:
        """
        파라미터 값 해석

        Args:
            param_name: 파라미터 이름
            param_type: 파라미터 타입
            request: HTTP 요청
            path_params: 경로 파라미터

        Returns:
            해석된 파라미터 값
        """
        ...


def get_type_info(param_type: type) -> tuple[type | None, tuple[type, ...]]:
    """
    타입 정보 추출

    Args:
        param_type: 파라미터 타입

    Returns:
        (origin, args) 튜플
        예: RequestBody[UserData] -> (RequestBody, (UserData,))
        예: list[Address] -> (list, (Address,))
        예: str -> (None, ())
    """
    origin = get_origin(param_type)
    args = get_args(param_type)
    return origin, args
