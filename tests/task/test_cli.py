"""CLI 테스트"""

import pytest
import sys
from unittest.mock import patch, MagicMock

from bloom.__main__ import import_from_string, main


class TestImportFromString:
    """import_from_string 함수 테스트"""

    def test_import_module_and_attribute(self):
        """모듈:속성 형식 임포트"""
        # os.path.join 임포트
        join = import_from_string("os.path:join")
        import os.path

        assert join is os.path.join

    def test_import_nested_attribute(self):
        """중첩 속성 임포트"""
        # bloom.Application 임포트
        Application = import_from_string("bloom:Application")
        from bloom import Application as BloomApp

        assert Application is BloomApp

    def test_invalid_format_raises_error(self):
        """잘못된 형식은 에러"""
        with pytest.raises(ImportError, match="Invalid import string"):
            import_from_string("os.path.join")  # 콜론 없음

    def test_module_not_found_raises_error(self):
        """모듈을 찾을 수 없으면 에러"""
        with pytest.raises(ImportError, match="Could not import module"):
            import_from_string("nonexistent_module:something")

    def test_attribute_not_found_raises_error(self):
        """속성을 찾을 수 없으면 에러"""
        with pytest.raises(ImportError, match="Could not find attribute"):
            import_from_string("os:nonexistent_attribute")


class TestMainCLI:
    """메인 CLI 테스트"""

    def test_no_command_shows_help(self, capsys):
        """명령어 없으면 도움말 표시"""
        from click.testing import CliRunner
        from bloom.__main__ import cli

        runner = CliRunner()
        result = runner.invoke(cli, [])
        # Click은 명령어 없이 실행하면 help를 보여주고 성공(0) 또는 실패(2) 반환
        assert result.exit_code in [0, 2]
        assert "Usage:" in result.output or "Commands:" in result.output

    def test_task_worker_command_uses_default_application(self, capsys):
        """task --worker 명령어는 기본 application:application.queue 사용"""
        from click.testing import CliRunner
        from bloom.__main__ import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["task", "--worker"])
        # 기본값 사용 시 application 모듈이 없으면 친절한 에러
        assert result.exit_code != 0
        assert "Could not import default application" in result.output

    def test_task_worker_command_with_explicit_application(self, capsys):
        """task --worker 명령어는 명시적 application 지정 가능"""
        from click.testing import CliRunner
        from bloom.__main__ import cli

        runner = CliRunner()
        result = runner.invoke(
            cli, ["task", "--worker", "--application=nonexistent:app.queue"]
        )
        assert result.exit_code != 0
        # 명시적 지정 시 import 에러
        assert "Could not import module" in result.output

    def test_task_without_worker_shows_help(self, capsys):
        """task 명령어만 실행하면 도움말 표시"""
        from click.testing import CliRunner
        from bloom.__main__ import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["task"])
        assert result.exit_code == 0
        assert "Usage:" in result.output
