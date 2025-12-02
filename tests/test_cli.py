"""Bloom CLI 테스트"""

import pytest
from click.testing import CliRunner

from bloom.__main__ import cli


class TestMainCLI:
    """메인 CLI 테스트"""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_cli_help(self, runner):
        """CLI 헬프 출력"""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Bloom Framework CLI" in result.output

    def test_version_command(self, runner):
        """version 명령어"""
        result = runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        assert "bloom" in result.output.lower() or "version" in result.output.lower()

    def test_startproject_command_help(self, runner):
        """startproject 명령어 헬프"""
        result = runner.invoke(cli, ["startproject", "--help"])
        assert result.exit_code == 0
        assert "project" in result.output.lower()

    def test_server_command_help(self, runner):
        """server 명령어 헬프"""
        result = runner.invoke(cli, ["server", "--help"])
        assert result.exit_code == 0
        assert "server" in result.output.lower() or "port" in result.output.lower()


class TestTestsCLI:
    """tests CLI 테스트"""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_tests_help(self, runner):
        """tests --help"""
        result = runner.invoke(cli, ["tests", "--help"])
        assert result.exit_code == 0
        assert "pytest" in result.output.lower()

    def test_tests_verbose_option(self, runner):
        """tests -v 옵션 확인"""
        result = runner.invoke(cli, ["tests", "--help"])
        assert "-v" in result.output or "--verbose" in result.output

    def test_tests_exitfirst_option(self, runner):
        """tests -x 옵션 확인"""
        result = runner.invoke(cli, ["tests", "--help"])
        assert "-x" in result.output or "--exitfirst" in result.output

    def test_tests_coverage_option(self, runner):
        """tests --cov 옵션 확인"""
        result = runner.invoke(cli, ["tests", "--help"])
        assert "--cov" in result.output


class TestTaskCLI:
    """task CLI 테스트"""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_task_help(self, runner):
        """task --help"""
        result = runner.invoke(cli, ["task", "--help"])
        assert result.exit_code == 0
        assert "worker" in result.output.lower() or "task" in result.output.lower()

    def test_task_worker_option(self, runner):
        """task --worker 옵션 확인"""
        result = runner.invoke(cli, ["task", "--help"])
        assert "-w" in result.output or "--worker" in result.output

    def test_task_concurrency_option(self, runner):
        """task --concurrency 옵션 확인"""
        result = runner.invoke(cli, ["task", "--help"])
        assert "-c" in result.output or "--concurrency" in result.output

    def test_task_without_options_shows_help(self, runner):
        """옵션 없이 호출하면 헬프 표시"""
        result = runner.invoke(cli, ["task"])
        # 헬프가 표시되어야 함
        assert "worker" in result.output.lower() or "Usage" in result.output


class TestRoutesCLI:
    """routes CLI 테스트"""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_routes_help(self, runner):
        """routes --help"""
        result = runner.invoke(cli, ["routes", "--help"])
        assert result.exit_code == 0
        assert "route" in result.output.lower()


class TestComponentsCLI:
    """components CLI 테스트"""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_components_help(self, runner):
        """components --help"""
        result = runner.invoke(cli, ["components", "--help"])
        assert result.exit_code == 0
        assert "component" in result.output.lower()


class TestShellCLI:
    """shell CLI 테스트"""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_shell_help(self, runner):
        """shell --help"""
        result = runner.invoke(cli, ["shell", "--help"])
        assert result.exit_code == 0
        assert "shell" in result.output.lower() or "interactive" in result.output.lower()


class TestCheckCLI:
    """check CLI 테스트"""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_check_help(self, runner):
        """check --help"""
        result = runner.invoke(cli, ["check", "--help"])
        assert result.exit_code == 0


class TestLazyCommandLoading:
    """LazyCommand 로딩 테스트"""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_lazy_commands_are_listed(self, runner):
        """lazy 로드되는 커맨드들이 목록에 표시"""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        # lazy 커맨드들이 목록에 있어야 함
        assert "tests" in result.output
        assert "task" in result.output

    def test_lazy_command_help_works(self, runner):
        """lazy 커맨드의 help도 동작"""
        result = runner.invoke(cli, ["tests", "--help"])
        assert result.exit_code == 0
        # 실제 커맨드의 help가 로드되어야 함
        assert "pytest" in result.output.lower()


class TestStartappCLI:
    """startapp CLI 테스트"""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_startapp_help(self, runner):
        """startapp --help"""
        result = runner.invoke(cli, ["startapp", "--help"])
        assert result.exit_code == 0
        assert "app" in result.output.lower()


class TestDbCLI:
    """db CLI 테스트"""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_db_help(self, runner):
        """db --help"""
        result = runner.invoke(cli, ["db", "--help"])
        assert result.exit_code == 0
        assert "database" in result.output.lower() or "migrate" in result.output.lower()


class TestRunCLI:
    """run CLI 테스트"""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_run_help(self, runner):
        """run --help"""
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "script" in result.output.lower() or "run" in result.output.lower()
