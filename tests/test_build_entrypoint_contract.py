"""Host-safe checks for the canonical root build entrypoint."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BuildEntrypointContractTests(unittest.TestCase):
    def test_build_sh_delegates_to_docker_build_script(self) -> None:
        text = (ROOT / "build.sh").read_text(encoding="utf-8")
        self.assertIn('exec bash "$SCRIPT_DIR/docker/build.sh" "$@"', text)


if __name__ == "__main__":
    unittest.main()
