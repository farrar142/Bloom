"""UploadedFile 리졸버"""

from typing import Annotated, Any, get_args, get_origin

from vessel.web.http import HttpRequest
from vessel.web.params.types import UploadedFile

from ..base import ParameterResolver, is_optional, unwrap_optional
from ..registry import UNRESOLVED


class UploadedFileResolver(ParameterResolver):
    """
    UploadedFile 파라미터 리졸버

    request.files에서 업로드된 파일을 추출합니다.
    Optional[T] 지원: 파일이 없으면 None 반환.

    지원 형태:
        - file: UploadedFile - 파라미터 이름으로 파일 추출
        - file: UploadedFile["avatar"] - 지정된 필드명으로 파일 추출
        - files: list[UploadedFile] - 파라미터 이름으로 여러 파일 추출
        - files: list[UploadedFile["images"]] - 지정된 필드명으로 여러 파일 추출
        - file: UploadedFile | None - Optional 지원
    """

    def _is_uploaded_file_type(self, param_type: type) -> bool:
        """UploadedFile 또는 UploadedFile["key"] 타입인지 확인"""
        if param_type is UploadedFile:
            return True
        origin = get_origin(param_type)
        if origin is Annotated:
            args = get_args(param_type)
            if args and args[0] is UploadedFile:
                return True
        return False

    def _is_list_uploaded_file(self, param_type: type) -> bool:
        """list[UploadedFile] 또는 list[UploadedFile["key"]] 타입인지 확인"""
        origin = get_origin(param_type)
        if origin is list:
            args = get_args(param_type)
            if args:
                inner_type = args[0]
                if inner_type is UploadedFile:
                    return True
                inner_origin = get_origin(inner_type)
                if inner_origin is Annotated:
                    inner_args = get_args(inner_type)
                    if inner_args and inner_args[0] is UploadedFile:
                        return True
        return False

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        # Optional[T] 처리
        if is_optional(param_type):
            inner_type = unwrap_optional(param_type)
            return self._is_uploaded_file_type(
                inner_type
            ) or self._is_list_uploaded_file(inner_type)

        # UploadedFile 직접 또는 Annotated
        if self._is_uploaded_file_type(param_type):
            return True

        # list[UploadedFile]
        if self._is_list_uploaded_file(param_type):
            return True

        return False

    async def resolve(
        self,
        param_name: str,
        param_type: type,
        request: HttpRequest,
        path_params: dict[str, str],
    ) -> Any:
        # Optional 처리
        optional = is_optional(param_type)
        actual_type = unwrap_optional(param_type) if optional else param_type

        origin = get_origin(actual_type)

        # list[UploadedFile] 또는 list[UploadedFile["field_name"]]
        if origin is list:
            result = self._resolve_list(param_name, actual_type, request)
            if not result and optional:
                return None
            return result

        # UploadedFile["field_name"] (Annotated)
        if origin is Annotated:
            result = self._resolve_single_annotated(param_name, actual_type, request)
            if result is None and not optional:
                return UNRESOLVED
            return result

        # UploadedFile 직접
        result = self._resolve_single(param_name, request)
        if result is None and not optional:
            return UNRESOLVED
        return result

    def _resolve_single(
        self, param_name: str, request: HttpRequest
    ) -> UploadedFile | None:
        """파라미터 이름으로 단일 파일 추출"""
        files = request.files.get(param_name, [])
        return files[0] if files else None

    def _resolve_single_annotated(
        self, param_name: str, param_type: type, request: HttpRequest
    ) -> UploadedFile | None:
        """Annotated에서 필드명 추출하여 단일 파일 반환"""
        args = get_args(param_type)
        field_name = args[1] if len(args) > 1 else param_name
        files = request.files.get(field_name, [])
        return files[0] if files else None

    def _resolve_list(
        self, param_name: str, param_type: type, request: HttpRequest
    ) -> list[UploadedFile]:
        """여러 파일 추출"""
        args = get_args(param_type)
        if not args:
            return []

        inner_type = args[0]
        inner_origin = get_origin(inner_type)

        # list[UploadedFile["field_name"]]
        if inner_origin is Annotated:
            inner_args = get_args(inner_type)
            field_name = inner_args[1] if len(inner_args) > 1 else param_name
        else:
            # list[UploadedFile]
            field_name = param_name

        return request.files.get(field_name, [])
