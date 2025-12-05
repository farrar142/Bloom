"""Migrations for orders app"""

import importlib.util
from pathlib import Path

# 숫자로 시작하는 파일은 직접 import할 수 없으므로 동적 로드
_migration_file = Path(__file__).parent / "0001_create_order.py"
_spec = importlib.util.spec_from_file_location("migration_0001", _migration_file)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
migration = _module.migration

__all__ = ["migration"]
