"""Configuration manager - manages configuration loading and binding"""

from typing import Any
from pathlib import Path

from .loader import ConfigurationLoader
from .binder import ConfigurationBinder
from .properties import is_configuration_properties, get_prefix


class ConfigManager:
    """
    설정 관리자
    
    설정 로드, 바인딩, ConfigurationProperties 인스턴스 생성을 관리합니다.
    """

    def __init__(self):
        self._loader = ConfigurationLoader()
        self._binder = ConfigurationBinder()

    def load_config(
        self,
        source: str | Path | dict[str, Any] | None = None,
        source_type: str = "auto",
    ) -> "ConfigManager":
        """
        설정 로드

        Args:
            source: 설정 소스 (파일 경로, dict 등)
            source_type: 소스 타입 ("yaml", "json", "env", "dict", "auto")

        Returns:
            self (메서드 체이닝 지원)

        사용 예시:
            config_manager.load_config("config/application.yaml")
            config_manager.load_config({"app": {"name": "MyApp"}}, source_type="dict")
            config_manager.load_config(source_type="env")  # 환경 변수만 로드
        """
        if source is None:
            # 환경 변수만 로드
            self._loader.load_from_env()
            return self

        if isinstance(source, dict):
            self._loader.load_from_dict(source)
            return self

        # 파일 경로
        path = Path(source)

        if source_type == "auto":
            # 확장자로 타입 자동 감지
            suffix = path.suffix.lower()
            if suffix in (".yaml", ".yml"):
                source_type = "yaml"
            elif suffix == ".json":
                source_type = "json"
            elif suffix == ".env":
                source_type = "env"

        if source_type == "yaml":
            self._loader.load_from_yaml(path)
        elif source_type == "json":
            self._loader.load_from_json(path)
        elif source_type == "env":
            self._loader.load_from_dotenv(path)

        return self

    def get_config(self) -> dict[str, Any]:
        """로드된 전체 설정 반환"""
        return self._loader.get_config()

    def bind_configuration_properties(self, container_manager) -> None:
        """
        ConfigurationProperties를 바인딩하여 인스턴스 생성
        
        Args:
            container_manager: ContainerManager 인스턴스
        """
        config_dict = self._loader.get_config()

        for qual_containers in container_manager.get_all_containers().values():
            for qualifier, container in qual_containers.items():
                target = container.target

                # ConfigurationProperties인지 확인
                if not is_configuration_properties(target):
                    continue

                # prefix 추출
                prefix = get_prefix(target)

                # 설정 바인딩
                instance = self._binder.bind(config_dict, target, prefix)

                # 인스턴스 등록
                container_manager.set_instance(target, instance, qualifier=qualifier)

    def bind(
        self, target_class: type, prefix: str = ""
    ) -> Any:
        """
        특정 클래스에 설정 바인딩
        
        Args:
            target_class: 바인딩할 클래스
            prefix: 설정 prefix
            
        Returns:
            바인딩된 인스턴스
        """
        config_dict = self._loader.get_config()
        return self._binder.bind(config_dict, target_class, prefix)
