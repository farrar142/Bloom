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
        with patch.object(sys, "argv", ["bloom"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

    def test_worker_command_requires_app(self, capsys):
        """worker 명령어는 app 인자 필요"""
        with patch.object(sys, "argv", ["bloom", "worker"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code != 0
