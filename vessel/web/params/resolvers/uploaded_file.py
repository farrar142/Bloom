"""UploadedFile 리졸버"""

from typing import Annotated, Any, get_args, get_origin

from vessel.web.http import HttpRequest
from vessel.web.params.types import UploadedFile

from ..base import ParameterResolver
from ..registry import UNRESOLVED


class UploadedFileResolver(ParameterResolver):
    """
    UploadedFile 파라미터 리졸버

    request.files에서 업로드된 파일을 추출합니다.

    지원 형태:
        - file: UploadedFile - 파라미터 이름으로 파일 추출
        - file: UploadedFile["avatar"] - 지정된 필드명으로 파일 추출
        - files: list[UploadedFile] - 파라미터 이름으로 여러 파일 추출
        - files: list[UploadedFile["images"]] - 지정된 필드명으로 여러 파일 추출
    """

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        # UploadedFile 직접
        if param_type is UploadedFile:
            return True

        # UploadedFile["field_name"] (Annotated)
        if origin is Annotated:
            args = get_args(param_type)
            if args and args[0] is UploadedFile:
                return True

        # list[UploadedFile] 또는 list[UploadedFile["field_name"]]
        if origin is list:
            args = get_args(param_type)
            if args:
                inner_type = args[0]
                if inner_type is UploadedFile:
                    return True
                # list[UploadedFile["field_name"]]
                inner_origin = get_origin(inner_type)
                if inner_origin is Annotated:
                    inner_args = get_args(inner_type)
                    if inner_args and inner_args[0] is UploadedFile:
                        return True

        return False

    async def resolve(
        self,
        param_name: str,
        param_type: type,
        request: HttpRequest,
        path_params: dict[str, str],
    ) -> Any:
        origin = get_origin(param_type)

        # list[UploadedFile] 또는 list[UploadedFile["field_name"]]
        if origin is list:
            return self._resolve_list(param_name, param_type, request)

        # UploadedFile["field_name"] (Annotated)
        if origin is Annotated:
            return self._resolve_single_annotated(param_name, param_type, request)

        # UploadedFile 직접
        return self._resolve_single(param_name, request)

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
