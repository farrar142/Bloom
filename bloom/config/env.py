"""환경변수 주입 시스템

사용 예시:
    from bloom.config.env import Env, EnvStr, EnvInt, EnvEnum

    @Component
    class Service:
        password: EnvStr[Literal["PASSWORD"]]  # str로 PASSWORD 환경변수 주입
        port: EnvInt[Literal["PORT"]]          # int로 PORT 환경변수 주입
        debug: EnvBool[Literal["DEBUG"]]       # bool로 DEBUG 환경변수 주입
        algo: EnvEnum[JwtAlgorithm, Literal["JWT_ALGO"]]  # Enum으로 주입
"""

import os
from enum import Enum
from typing import Annotated, Any, Literal, TypeAliasType, get_origin, get_args


class Env[K]:
    """환경변수 마커 클래스

    K는 Literal["ENV_KEY"] 형태로 환경변수 키를 지정합니다.
    """

    pass


# 타입별 환경변수 alias
type EnvStr[K] = Annotated[str, Env[K]]
type EnvInt[K] = Annotated[int, Env[K]]
type EnvFloat[K] = Annotated[float, Env[K]]
type EnvBool[K] = Annotated[bool, Env[K]]


class EnvEnumMarker[E, K]:
    """Enum 환경변수 마커

    E: Enum 타입
    K: Literal["ENV_KEY"] 형태의 환경변수 키
    """

    pass


# Enum 환경변수 alias
# 사용법: algo: EnvEnum[JwtAlgorithm, Literal["JWT_ALGO"]]
type EnvEnum[E, K] = Annotated[E, EnvEnumMarker[E, K]]


def _resolve_type_alias(hint: Any) -> Any:
    """TypeAliasType을 해석하여 실제 Annotated 타입으로 변환

    EnvStr[Literal["KEY"]] -> Annotated[str, Env[Literal["KEY"]]]
    EnvEnum[MyEnum, Literal["KEY"]] -> Annotated[MyEnum, EnvEnumMarker[MyEnum, Literal["KEY"]]]
    """
    origin = getattr(hint, "__origin__", None)

    # TypeAliasType인 경우 (EnvStr, EnvInt, EnvEnum 등)
    if isinstance(origin, TypeAliasType):
        alias_name = getattr(origin, "__name__", "")

        # hint의 __args__: type alias에 전달된 인자들
        type_args = getattr(hint, "__args__", ())
        if not type_args:
            return hint

        # EnvEnum[E, K] 특별 처리: Annotated[E, EnvEnumMarker[E, K]]
        if alias_name == "EnvEnum" and len(type_args) >= 2:
            enum_type = type_args[0]  # 실제 Enum 타입 (예: Environment)
            literal_key = type_args[1]  # Literal["APP_ENV"]
            resolved_marker = EnvEnumMarker[enum_type, literal_key]
            return Annotated[enum_type, resolved_marker]

        # __value__: Annotated[str, Env[K]] 형태
        template = getattr(origin, "__value__", None)
        if template is None:
            return hint

        # template의 origin이 Annotated인지 확인
        if get_origin(template) is not Annotated:
            return hint

        # Annotated[str, Env[K]]에서 args 추출
        template_args = get_args(template)
        if len(template_args) < 2:
            return hint

        value_type = template_args[0]  # str, int 등
        env_marker_template = template_args[1]  # Env[K]

        # Env[K]를 Env[Literal["KEY"]]로 변환
        actual_key = type_args[0]  # Literal["KEY"]
        resolved_marker = Env[actual_key]

        # 새로운 Annotated 생성
        return Annotated[value_type, resolved_marker]

    return hint


def is_env_type(hint: Any) -> bool:
    """주어진 타입 힌트가 Env 타입인지 확인 (EnvEnum 포함)"""
    # TypeAliasType 해석
    resolved = _resolve_type_alias(hint)

    origin = get_origin(resolved)
    if origin is not Annotated:
        return False

    args = get_args(resolved)
    if len(args) < 2:
        return False

    # args[1]이 Env[K] 또는 EnvEnumMarker[E, K] 형태인지 확인
    marker = args[1]
    marker_origin = get_origin(marker)

    if marker_origin is Env:
        return True
    if marker_origin is EnvEnumMarker:
        return True

    # Env 클래스 자체인 경우도 처리
    if isinstance(marker, type) and issubclass(marker, Env):
        return True

    return False


def resolve_env_value(hint: Any, default: Any = None) -> Any:
    """Env 타입에서 환경변수 값을 해석하여 반환

    Args:
        hint: EnvStr[Literal["KEY"]], EnvEnum[E, Literal["KEY"]] 등의 타입 힌트
        default: 환경변수가 없을 때 기본값

    Returns:
        환경변수 값 (타입 변환됨)
    """
    # TypeAliasType 해석
    resolved = _resolve_type_alias(hint)

    origin = get_origin(resolved)
    if origin is not Annotated:
        return default

    args = get_args(resolved)
    if len(args) < 2:
        return default

    # args[0]: 실제 타입 (str, int, float, bool, Enum)
    # args[1]: Env[Literal["KEY"]] 또는 EnvEnumMarker[E, K]
    value_type = args[0]
    env_marker = args[1]

    marker_origin = get_origin(env_marker)

    # EnvEnumMarker[E, K] 처리
    if marker_origin is EnvEnumMarker:
        return _resolve_env_enum(env_marker, default)

    # Env[Literal["KEY"]]에서 KEY 추출
    env_key = _extract_env_key(env_marker)
    if env_key is None:
        return default

    # 환경변수 조회
    env_value = os.environ.get(env_key)
    if env_value is None:
        return default

    # 타입 변환
    return _convert_value(env_value, value_type)


def _resolve_env_enum(env_marker: Any, default: Any) -> Any:
    """EnvEnumMarker[E, K]에서 Enum 값 해석"""
    marker_args = get_args(env_marker)
    if len(marker_args) < 2:
        return default

    enum_type = marker_args[0]  # E (Enum 타입)
    literal_type = marker_args[1]  # Literal["KEY"]

    # Literal["KEY"]에서 "KEY" 추출
    literal_args = get_args(literal_type)
    if not literal_args:
        return default

    env_key = literal_args[0]

    # 환경변수 조회
    env_value = os.environ.get(env_key)
    if env_value is None:
        return default

    # Enum 변환
    if isinstance(enum_type, type) and issubclass(enum_type, Enum):
        try:
            # 이름으로 먼저 시도 (예: "HS256")
            return enum_type[env_value]
        except KeyError:
            try:
                # 값으로 시도 (예: "HS256" as value)
                return enum_type(env_value)
            except ValueError:
                return default

    return default


def _extract_env_key(env_marker: Any) -> str | None:
    """Env[Literal["KEY"]]에서 "KEY" 문자열 추출

    다음 형식 모두 지원:
    - Env[Literal["KEY"]] -> "KEY"
    - Env[ForwardRef("KEY")] -> "KEY" (문자열 키 직접 사용 시)
    """
    from typing import ForwardRef

    marker_origin = get_origin(env_marker)

    if marker_origin is Env:
        # Env[Literal["KEY"]] 또는 Env[ForwardRef("KEY")] 형태
        marker_args = get_args(env_marker)
        if marker_args:
            key_type = marker_args[0]

            # ForwardRef("KEY") -> "KEY"
            if isinstance(key_type, ForwardRef):
                return key_type.__forward_arg__

            # Literal["KEY"]에서 "KEY" 추출
            literal_args = get_args(key_type)
            if literal_args:
                return literal_args[0]

    return None


def _convert_value(value: str, target_type: type) -> Any:
    """문자열 값을 대상 타입으로 변환"""
    if target_type is str:
        return value
    elif target_type is int:
        return int(value)
    elif target_type is float:
        return float(value)
    elif target_type is bool:
        return value.lower() in ("true", "1", "yes", "on")
    else:
        # 기본적으로 문자열 반환
        return value
