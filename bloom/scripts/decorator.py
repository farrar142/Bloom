"""Script decorator - Click 기반 스크립트 정의

@script 데코레이터를 사용하여 커스텀 스크립트를 정의합니다.
함수 기반과 클래스 기반 두 가지 패턴을 지원합니다.

함수 기반:
    @script
    @click.option("--count", type=int, default=10)
    def seed_data(count: int, app):
        repo = app.container.get(UserRepository)
        # ...

클래스 기반 (DI 지원):
    @script
    class SeedDataScript(BaseScript):
        user_repo: UserRepository  # 필드 주입

        @click.option("--count", type=int, default=10)
        def handle(self, count: int):
            for i in range(count):
                self.user_repo.save(User(name=f"User {i}"))
"""

from __future__ import annotations

import functools
import re
from abc import ABC, abstractmethod
from typing import Any, Callable, TypeVar, TYPE_CHECKING

import click

if TYPE_CHECKING:
    from bloom.application import Application

F = TypeVar("F", bound=Callable[..., Any])
T = TypeVar("T")

# 등록된 스크립트들을 저장하는 레지스트리
_script_registry: dict[str, click.Command] = {}

# 클래스 스크립트 레지스트리 (인스턴스화 필요)
_class_script_registry: dict[str, type["BaseScript"]] = {}


class BaseScript(ABC):
    """클래스 기반 스크립트의 베이스 클래스

    DI 컨테이너로부터 필드 주입을 받아 사용할 수 있습니다.

    Usage:
        @script
        class SeedDataScript(BaseScript):
            '''테스트 데이터 시딩'''

            user_repo: UserRepository  # 필드 주입
            config: AppConfig          # 필드 주입

            @click.option("--count", "-c", type=int, default=10)
            @click.option("--dry-run", is_flag=True)
            def handle(self, count: int, dry_run: bool):
                if dry_run:
                    click.echo(f"[DRY RUN] Would create {count} users")
                    return

                for i in range(count):
                    self.user_repo.save(User(name=f"User {i}"))
                click.secho(f"✓ Created {count} users", fg="green")
    """

    # 스크립트 이름 (None이면 클래스 이름에서 자동 생성)
    name: str | None = None

    def __init__(self) -> None:
        """기본 생성자 (DI에서 필드 주입 후 호출됨)"""
        pass

    @abstractmethod
    def handle(self, **options: Any) -> None:
        """스크립트 실행 로직

        Args:
            **options: Click 옵션/인자들
        """
        pass


def _to_kebab_case(name: str) -> str:
    """CamelCase를 kebab-case로 변환

    SeedDataScript -> seed-data
    MyTestScript -> my-test
    """
    # Script 접미사 제거
    if name.endswith("Script"):
        name = name[:-6]
    # CamelCase -> kebab-case
    name = re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()
    return name


def script(
    func_or_class: F | type[BaseScript] | None = None, *, name: str | None = None
) -> F | type[BaseScript] | Callable[[F | type[BaseScript]], F | type[BaseScript]]:
    """스크립트 데코레이터 (함수/클래스 모두 지원)

    함수나 BaseScript 클래스를 등록하고 Click Command로 변환합니다.

    Args:
        func_or_class: 스크립트 함수 또는 BaseScript 상속 클래스
        name: 스크립트 이름 (기본값: 함수/클래스 이름에서 자동 생성)

    Usage (함수):
        @script
        @click.option("--count", "-c", type=int, default=10)
        def seed_data(count: int, app):
            '''테스트 데이터 시딩'''
            repo = app.container.get(UserRepository)
            # ...

    Usage (클래스):
        @script
        class SeedDataScript(BaseScript):
            '''테스트 데이터 시딩'''
            user_repo: UserRepository

            @click.option("--count", "-c", type=int, default=10)
            def handle(self, count: int):
                # ...
    """

    def decorator(target: F | type[BaseScript]) -> F | type[BaseScript]:
        if isinstance(target, type) and issubclass(target, BaseScript):
            return _register_class_script(target, name)
        elif callable(target):
            return _register_function_script(target, name)  # type: ignore
        else:
            raise TypeError(
                f"@script decorator expects a function or BaseScript subclass, "
                f"got {type(target)}"
            )

    if func_or_class is not None:
        return decorator(func_or_class)
    return decorator  # type: ignore


def _register_function_script(fn: F, custom_name: str | None) -> F:
    """함수 기반 스크립트 등록"""
    script_name = custom_name or fn.__name__

    # Click 파라미터들 수집 (옵션, 인자)
    params = getattr(fn, "__click_params__", [])

    @functools.wraps(fn)
    def wrapper(**kwargs: Any) -> Any:
        return fn(**kwargs)

    # Click Command 생성
    cmd = click.Command(
        name=script_name,
        callback=wrapper,
        help=fn.__doc__,
        params=list(reversed(params)),
    )

    # 원본 함수 참조 저장
    cmd._original_func = fn  # type: ignore
    cmd._is_class_script = False  # type: ignore

    # 레지스트리에 등록
    _script_registry[script_name] = cmd

    return fn


def _register_class_script(
    cls: type[BaseScript], custom_name: str | None
) -> type[BaseScript]:
    """클래스 기반 스크립트 등록"""
    # 스크립트 이름 결정
    script_name = custom_name or cls.name or _to_kebab_case(cls.__name__)

    # handle 메서드에서 Click 파라미터 수집
    handle_method = getattr(cls, "handle", None)
    if handle_method is None:
        raise TypeError(
            f"BaseScript subclass {cls.__name__} must implement 'handle' method"
        )

    params = getattr(handle_method, "__click_params__", [])

    # 플레이스홀더 콜백 (실제 실행은 cli.py에서 인스턴스 생성 후)
    def placeholder_callback(**kwargs: Any) -> Any:
        pass

    # Click Command 생성
    cmd = click.Command(
        name=script_name,
        callback=placeholder_callback,
        help=cls.__doc__,
        params=list(reversed(params)),
    )

    # 클래스 참조 저장
    cmd._script_class = cls  # type: ignore
    cmd._is_class_script = True  # type: ignore

    # 레지스트리에 등록
    _script_registry[script_name] = cmd
    _class_script_registry[script_name] = cls

    return cls


def get_registered_scripts() -> dict[str, click.Command]:
    """등록된 스크립트들 반환"""
    return _script_registry.copy()


def get_class_scripts() -> dict[str, type[BaseScript]]:
    """등록된 클래스 스크립트들 반환"""
    return _class_script_registry.copy()


def clear_registry() -> None:
    """레지스트리 초기화 (테스트용)"""
    _script_registry.clear()
    _class_script_registry.clear()
