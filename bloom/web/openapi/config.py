"""OpenAPI 설정"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OpenAPIContact:
    """API 연락처 정보"""

    name: str | None = None
    url: str | None = None
    email: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.name:
            result["name"] = self.name
        if self.url:
            result["url"] = self.url
        if self.email:
            result["email"] = self.email
        return result


@dataclass
class OpenAPILicense:
    """API 라이선스 정보"""

    name: str
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"name": self.name}
        if self.url:
            result["url"] = self.url
        return result


@dataclass
class OpenAPIServer:
    """API 서버 정보"""

    url: str
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"url": self.url}
        if self.description:
            result["description"] = self.description
        return result


@dataclass
class OpenAPITag:
    """API 태그 정보"""

    name: str
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"name": self.name}
        if self.description:
            result["description"] = self.description
        return result


@dataclass
class OpenAPIConfig:
    """
    OpenAPI 스펙 설정

    사용 예시:
        @Component
        class Config:
            @Factory
            def openapi_config(self) -> OpenAPIConfig:
                return OpenAPIConfig(
                    title="My API",
                    version="1.0.0",
                    description="RESTful API",
                    servers=[OpenAPIServer(url="https://api.example.com")],
                )
    """

    title: str = "Bloom API"
    version: str = "1.0.0"
    description: str | None = None
    terms_of_service: str | None = None
    contact: OpenAPIContact | None = None
    license: OpenAPILicense | None = None
    servers: list[OpenAPIServer] = field(default_factory=list)
    tags: list[OpenAPITag] = field(default_factory=list)

    # 경로 설정
    openapi_url: str = "/openapi.json"
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"

    # OpenAPI 버전
    openapi_version: str = "3.0.3"

    def get_info(self) -> dict[str, Any]:
        """OpenAPI info 객체 생성"""
        info: dict[str, Any] = {
            "title": self.title,
            "version": self.version,
        }
        if self.description:
            info["description"] = self.description
        if self.terms_of_service:
            info["termsOfService"] = self.terms_of_service
        if self.contact:
            info["contact"] = self.contact.to_dict()
        if self.license:
            info["license"] = self.license.to_dict()
        return info

    def get_servers(self) -> list[dict[str, Any]]:
        """OpenAPI servers 배열 생성"""
        return [s.to_dict() for s in self.servers]

    def get_tags(self) -> list[dict[str, Any]]:
        """OpenAPI tags 배열 생성"""
        return [t.to_dict() for t in self.tags]
