"""Configuration loader - loads configuration from various sources"""

import os
import json
import re
from pathlib import Path
from typing import Any


class ConfigurationLoader:
    """다양한 소스에서 설정을 로드하는 클래스"""

    def __init__(self):
        self._config: dict[str, Any] = {}
        # 환경변수 참조 패턴: ${VAR_NAME} 또는 ${VAR_NAME:default_value}
        self._env_pattern = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")

    def load_from_dict(
        self, config_dict: dict[str, Any], resolve_env: bool = True
    ) -> "ConfigurationLoader":
        """
        딕셔너리에서 설정 로드

        Args:
            config_dict: 설정 딕셔너리
            resolve_env: 환경변수 참조를 해석할지 여부 (기본값: True)
        """
        if resolve_env:
            config_dict = self._resolve_env_vars(config_dict)
        self._merge_config(config_dict)
        return self

    def load_from_json(self, path: str | Path) -> "ConfigurationLoader":
        """JSON 파일에서 설정 로드"""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            config_dict = json.load(f)
            self._merge_config(config_dict)
        return self

    def load_from_yaml(
        self, path: str | Path, resolve_env: bool = True
    ) -> "ConfigurationLoader":
        """
        YAML 파일에서 설정 로드

        Args:
            path: YAML 파일 경로
            resolve_env: 환경변수 참조를 해석할지 여부 (기본값: True)
        """
        try:
            import yaml
        except ImportError:
            raise ImportError(
                "PyYAML is required to load YAML files. Install it with: pip install pyyaml"
            )

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            config_dict = yaml.safe_load(f)
            if config_dict:
                if resolve_env:
                    config_dict = self._resolve_env_vars(config_dict)
                self._merge_config(config_dict)
        return self

    def load_from_env(
        self, prefix: str = "", separator: str = "_"
    ) -> "ConfigurationLoader":
        """
        환경 변수에서 설정 로드

        환경 변수 형식: PREFIX_KEY_SUBKEY=value
        예: APP_DATABASE_HOST=localhost -> {"app": {"database": {"host": "localhost"}}}
        """
        env_config: dict[str, Any] = {}

        for key, value in os.environ.items():
            if prefix and not key.startswith(prefix):
                continue

            # prefix 제거
            if prefix:
                key = key[len(prefix) :]

            # 대소문자를 소문자로 변환
            parts = key.lower().split(separator)

            # 중첩 딕셔너리 생성
            current = env_config
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]

            # 값 설정 (타입 추론 시도)
            current[parts[-1]] = self._parse_value(value)

        self._merge_config(env_config)
        return self

    def load_from_dotenv(self, path: str | Path = ".env") -> "ConfigurationLoader":
        """
        .env 파일에서 설정 로드

        .env 파일 형식:
            DATABASE_HOST=localhost
            DATABASE_PORT=5432
        """
        path = Path(path)
        if not path.exists():
            return self

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()

                    # 따옴표 제거
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]

                    os.environ[key] = value

        # 환경 변수로 설정되었으므로 load_from_env 호출
        return self.load_from_env()

    def get_config(self) -> dict[str, Any]:
        """로드된 전체 설정 반환"""
        return self._config

    def get_nested_value(self, key_path: str, separator: str = ".") -> Any:
        """
        중첩된 키 경로로 값 조회

        예: get_nested_value("app.database.host") -> config["app"]["database"]["host"]
        """
        keys = key_path.split(separator)
        current = self._config

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None

        return current

    def _merge_config(self, new_config: dict[str, Any]) -> None:
        """기존 설정에 새 설정을 병합 (덮어쓰기)"""
        self._deep_merge(self._config, new_config)

    def _deep_merge(self, target: dict, source: dict) -> None:
        """딕셔너리 깊은 병합"""
        for key, value in source.items():
            if (
                key in target
                and isinstance(target[key], dict)
                and isinstance(value, dict)
            ):
                self._deep_merge(target[key], value)
            else:
                target[key] = value

    def _parse_value(self, value: str) -> Any:
        """문자열 값을 적절한 타입으로 변환"""
        # 불리언
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False

        # 숫자
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        # 문자열
        return value

    def _resolve_env_vars(self, obj: Any) -> Any:
        """
        환경변수 참조를 재귀적으로 해석

        지원 형식:
            - ${ENV_VAR}: 환경변수 값으로 치환 (없으면 빈 문자열)
            - ${ENV_VAR:default}: 환경변수 값으로 치환 (없으면 default 사용)

        예:
            "database.host: ${DB_HOST:localhost}" -> "database.host: localhost" (DB_HOST 없을 때)
        """
        if isinstance(obj, dict):
            return {key: self._resolve_env_vars(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._resolve_env_vars(item) for item in obj]
        elif isinstance(obj, str):
            return self._resolve_env_var_string(obj)
        else:
            return obj

    def _resolve_env_var_string(self, text: str) -> Any:
        """
        문자열 내 환경변수 참조 해석

        Returns:
            환경변수가 전체 문자열이면 타입 변환 시도, 부분이면 문자열 치환
        """

        def replace_match(match: re.Match) -> str:
            var_name = match.group(1)
            default_value = match.group(2) if match.group(2) is not None else ""
            return os.environ.get(var_name, default_value)

        # 전체가 하나의 환경변수 참조인 경우 (타입 변환 시도)
        full_match = self._env_pattern.fullmatch(text)
        if full_match:
            resolved = replace_match(full_match)
            return self._parse_value(resolved)

        # 부분 치환 (문자열 유지)
        return self._env_pattern.sub(replace_match, text)
