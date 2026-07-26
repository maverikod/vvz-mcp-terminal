"""Host-safe packaging contract tests for docker/build-deb.sh."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BuildDebContractTests(unittest.TestCase):
    def test_build_deb_copies_optional_lib_only_when_present(self) -> None:
        text = (ROOT / "docker/build-deb.sh").read_text(encoding="utf-8")
        self.assertIn('if [ -d "$DEBIAN_SRC/lib" ]; then', text)
        self.assertIn('cp -a "$DEBIAN_SRC/lib" "$PKG_WORK/"', text)
        self.assertTrue((ROOT / "docker/debian/lib/systemd/system").is_dir())

    def test_build_deb_uses_tmp_staging_and_repairs_output_ownership(self) -> None:
        text = (ROOT / "docker/build-deb.sh").read_text(encoding="utf-8")
        self.assertIn('PKG_STAGE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/mcp-terminal-deb-build.XXXXXX")"', text)
        self.assertIn('trap cleanup EXIT', text)
        self.assertIn('OUTPUT_OWNER="$(stat -c \'%u:%g\' "$PROJECT_ROOT")"', text)
        self.assertIn('chown "$OUTPUT_OWNER" "$OUTPUT_DIR" "$DEB_FILE"', text)


if __name__ == "__main__":
    unittest.main()
