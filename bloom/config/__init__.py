"""Configuration management system"""

from typing import TYPE_CHECKING

__all__ = [
    "ConfigurationProperties",
    "ConfigManager",
    "Env",
    "EnvStr",
    "EnvInt",
    "EnvFloat",
    "EnvBool",
    "EnvEnum",
    "EnvEnumMarker",
]


def __getattr__(name: str):
    """Lazy import"""

    if name == "ConfigurationProperties":
        from .properties import ConfigurationProperties

        return ConfigurationProperties

    if name == "ConfigManager":
        from .manager import ConfigManager

        return ConfigManager

    if name in (
        "Env",
        "EnvStr",
        "EnvInt",
        "EnvFloat",
        "EnvBool",
        "EnvEnum",
        "EnvEnumMarker",
    ):
        from . import env

        return getattr(env, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# TYPE_CHECKING용 (IDE 지원)
if TYPE_CHECKING:
    from .properties import ConfigurationProperties
    from .manager import ConfigManager
    from .env import Env, EnvStr, EnvInt, EnvFloat, EnvBool, EnvEnum, EnvEnumMarker
