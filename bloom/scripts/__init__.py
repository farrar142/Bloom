"""Bloom Scripts - 커스텀 스크립트 시스템

Django의 management commands와 유사하게, 개발자가 프로젝트 내에서
커스텀 스크립트를 정의하고 CLI에서 실행할 수 있습니다.

함수 기반 스크립트:
    # 프로젝트/scripts/seed_data.py
    import click
    from bloom.scripts import script

    @script
    @click.option("--count", "-c", type=int, default=10)
    def seed_data(count: int, app):
        '''테스트 데이터 시딩'''
        repo = app.container.get(UserRepository)
        for i in range(count):
            repo.save(User(name=f"User {i}"))
        click.secho(f"✓ Created {count} users", fg="green")

클래스 기반 스크립트 (DI 필드 주입):
    # 프로젝트/scripts/seed_data.py
    import click
    from bloom.scripts import script, BaseScript

    @script
    class SeedDataScript(BaseScript):
        '''테스트 데이터 시딩'''
        user_repo: UserRepository  # 필드 주입

        @click.option("--count", "-c", type=int, default=10)
        def handle(self, count: int):
            for i in range(count):
                self.user_repo.save(User(name=f"User {i}"))
            click.secho(f"✓ Created {count} users", fg="green")

실행:
    $ bloom run seed_data --count 100
    $ bloom run seed-data --count 100  # 클래스 기반 (kebab-case)
"""

from .decorator import script, BaseScript
from .registry import ScriptRegistry

__all__ = [
    "script",
    "BaseScript",
    "ScriptRegistry",
]
