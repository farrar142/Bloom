"""키-값 리졸버 베이스 클래스"""

from abc import abstractmethod
from typing import Annotated, Any, get_args

from vessel.web.http import HttpRequest

from ..base import ParameterResolver
from ..registry import UNRESOLVED
from ..types import KeyValue


class KeyValueResolver[T: KeyValue](ParameterResolver):
    """
    키-값 쌍 파라미터 리졸버의 베이스 클래스

    HttpHeader, HttpCookie 등 키-값 형태의 파라미터를 처리하는
    리졸버들의 공통 로직을 제공합니다.
    """

    @property
    @abstractmethod
    def target_type(self) -> type[T]:
        """처리할 타입 (HttpHeader, HttpCookie 등)"""
        ...

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        target = self.target_type

        # HttpHeader, HttpCookie (Annotated 없이)
        if param_type is target:
            return True

        # HttpHeader["Key"], HttpCookie["Key"] (Annotated[Type, "Key"])
        if origin is Annotated:
            args = get_args(param_type)
            if args and args[0] is target:
                return True

        return False

    async def resolve(
        self,
        param_name: str,
        param_type: type,
        request: HttpRequest,
        path_params: dict[str, str],
    ) -> Any:
        # 키 결정
        key = self._get_key(param_name, param_type)

        # 값 추출 (서브클래스에서 구현)
        value = self._extract_value(request, key)

        if value is None:
            return UNRESOLVED

        # KeyValue 인스턴스 생성
        return self.target_type(key=key, value=value)

    def _get_key(self, param_name: str, param_type: type) -> str:
        """키 결정"""
        # HttpHeader["User-Agent"], HttpCookie["session_id"] 형태인 경우
        args = get_args(param_type)
        if len(args) >= 2 and isinstance(args[1], str):
            return args[1]

        # 파라미터 이름에서 변환 (서브클래스에서 오버라이드 가능)
        return self._transform_param_name(param_name)

    def _transform_param_name(self, param_name: str) -> str:
        """파라미터 이름을 키로 변환 (기본: 그대로 사용)"""
        return param_name

    @abstractmethod
    def _extract_value(self, request: HttpRequest, key: str) -> str | None:
        """요청에서 값 추출 (서브클래스에서 구현)"""
        ...
