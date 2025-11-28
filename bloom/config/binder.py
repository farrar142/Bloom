"""Configuration binder - binds configuration dict to typed objects"""

from typing import Any, get_type_hints, get_origin, get_args
from dataclasses import is_dataclass, fields as dataclass_fields, MISSING
import inspect


class ConfigurationBinder:
    """설정 딕셔너리를 타입 안전한 객체로 바인딩"""

    def bind(
        self, config_dict: dict[str, Any], target_class: type, prefix: str = ""
    ) -> Any:
        """
        설정을 target_class 인스턴스로 바인딩

        Args:
            config_dict: 전체 설정 딕셔너리
            target_class: 바인딩할 클래스 (dataclass 또는 Pydantic BaseModel)
            prefix: 설정 prefix (예: "app.database")

        Returns:
            바인딩된 인스턴스
        """
        # prefix에 해당하는 설정 추출
        config_data = self._extract_config(config_dict, prefix)

        # Pydantic BaseModel 지원
        if self._is_pydantic_model(target_class):
            return self._bind_pydantic(config_data, target_class)

        # dataclass 지원
        if is_dataclass(target_class):
            return self._bind_dataclass(config_data, target_class)

        # 일반 클래스 (기본 생성자 사용)
        return self._bind_generic(config_data, target_class)

    def _extract_config(self, config_dict: dict[str, Any], prefix: str) -> dict[str, Any]:
        """prefix에 해당하는 설정 추출"""
        if not prefix:
            return config_dict

        keys = prefix.split(".")
        current = config_dict

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return {}

        return current if isinstance(current, dict) else {}

    def _is_pydantic_model(self, cls: type) -> bool:
        """Pydantic BaseModel인지 확인"""
        try:
            from pydantic import BaseModel

            return issubclass(cls, BaseModel)
        except ImportError:
            return False

    def _bind_pydantic(self, config_data: dict[str, Any], target_class: type) -> Any:
        """Pydantic 모델 바인딩"""
        # Pydantic은 자체적으로 검증 및 변환을 수행
        return target_class(**config_data)

    def _bind_dataclass(self, config_data: dict[str, Any], target_class: type) -> Any:
        """dataclass 바인딩"""
        try:
            type_hints = get_type_hints(target_class)
        except Exception:
            type_hints = {}

        kwargs = {}

        for field in dataclass_fields(target_class):
            field_name = field.name
            field_type = type_hints.get(field_name, field.type)

            if field_name in config_data:
                value = config_data[field_name]
                # 중첩된 dataclass 처리
                if isinstance(field_type, type) and is_dataclass(field_type):
                    value = self._bind_dataclass(value, field_type)
                # 중첩된 Pydantic 모델 처리
                elif isinstance(field_type, type) and self._is_pydantic_model(field_type):
                    value = self._bind_pydantic(value, field_type)
                else:
                    value = self._convert_value(value, field_type)

                kwargs[field_name] = value
            elif field.default is not MISSING:
                # 기본값 사용
                continue
            elif field.default_factory is not MISSING:  # type: ignore
                # default_factory 사용
                continue
            else:
                # 필수 필드인데 값이 없으면 None 또는 에러
                pass

        return target_class(**kwargs)

    def _bind_generic(self, config_data: dict[str, Any], target_class: type) -> Any:
        """일반 클래스 바인딩"""
        try:
            # __init__ 시그니처 확인
            sig = inspect.signature(target_class.__init__)
            kwargs = {}

            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue

                if param_name in config_data:
                    kwargs[param_name] = config_data[param_name]

            return target_class(**kwargs)
        except Exception:
            # 실패 시 빈 생성자 시도
            return target_class()

    def _convert_value(self, value: Any, target_type: type) -> Any:
        """값을 목표 타입으로 변환"""
        # Optional[T] 처리
        origin = get_origin(target_type)
        if origin is type(None) or str(origin) == "typing.Union":
            args = get_args(target_type)
            if len(args) == 2 and type(None) in args:
                # Optional[T]
                actual_type = args[0] if args[1] is type(None) else args[1]
                if value is None:
                    return None
                return self._convert_value(value, actual_type)

        # 기본 타입 변환
        if target_type in (int, float, str, bool):
            return target_type(value)

        # list, dict 등
        if origin in (list, dict, set, tuple):
            return value

        # 그 외는 그대로 반환
        return value
