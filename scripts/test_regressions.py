"""Run every unittest regression, requiring the JavaScript runtime and no skips."""
from pathlib import Path
import shutil
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    if not shutil.which("node"):
        print("Node.js is required: JavaScript regression coverage must not be skipped.", file=sys.stderr)
        return 1
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.skipped:
        print("Skipped regressions are not allowed in the mandatory suite.", file=sys.stderr)
    return 0 if result.wasSuccessful() and not result.skipped and result.testsRun else 1


if __name__ == "__main__":
    raise SystemExit(main())
