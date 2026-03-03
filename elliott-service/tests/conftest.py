import sys
from unittest.mock import MagicMock

# Mock external dependencies not available in the test environment
for mod in [
    "artcommonlib",
    "artcommonlib.dotconfig",
    "artcommonlib.logutil",
    "elliottlib",
    "elliottlib.cli",
    "elliottlib.cli.cli_opts",
    "elliottlib.cli.find_bugs_sweep_cli",
    "elliottlib.errata",
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()
