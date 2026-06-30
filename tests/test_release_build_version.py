"""Static release pipeline checks for image/package version coupling."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_build_sh_reads_version_from_pyproject_and_rejects_positional_version() -> None:
    text = _text("docker/build.sh")
    assert 'Path("pyproject.toml").read_text' in text
    assert "Unexpected argument" in text
    assert "version is read from pyproject.toml" in text
    assert 'bash "$SCRIPT_DIR/build-deb.sh"' in text
    assert 'bash "$SCRIPT_DIR/build-deb.sh" "$' not in text


def test_build_deb_reads_version_from_pyproject_and_rejects_override() -> None:
    text = _text("docker/build-deb.sh")
    assert 'Path("pyproject.toml").read_text' in text
    assert "does not accept a version argument" in text
    assert 'sed -i "s|@DOCKERHUB_REPO@|${DOCKERHUB_REPO}|g; s|@IMAGE_TAG@|${VERSION}|g"' in text
    assert "render-info-texi.py" in text
    assert "--markdown \"$PROJECT_ROOT/mcp_terminal/docs/INFO.md\"" in text


def test_debian_install_uses_image_spec_pull_before_recreate() -> None:
    docker_run = _text("docker/pkg/docker-run.sh")
    postinst = _text("docker/debian/DEBIAN/postinst")
    assert 'IMAGE_NAME="$(printf \'%s:%s\' "$DOCKERHUB_REPO" "$IMAGE_TAG")"' in docker_run
    assert 'docker pull "$IMAGE_NAME"' in docker_run
    assert '"$DOCKER_RUN" recreate' in postinst
