#!/bin/bash
# Build mcp-terminal-docker Debian package (service image tag must match package version).
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEBIAN_SRC="$SCRIPT_DIR/debian"
PKG_WORK="$SCRIPT_DIR/dist/deb-build"
OUTPUT_DIR="$SCRIPT_DIR/dist"

# shellcheck source=dockerhub_repo.sh
source "$SCRIPT_DIR/dockerhub_repo.sh"

DOCKERHUB_REPO="$(dockerhub_repo_default)"
ARCH="${MCP_TERMINAL_DEB_ARCH:-amd64}"

# shellcheck source=sandbox_images.sh
source "$SCRIPT_DIR/sandbox_images.sh"
SANDBOX_IMAGE_PYTHON_DEV="$(sandbox_image_python_dev)"
SANDBOX_IMAGE_NODE_DEV="$(sandbox_image_node_dev)"
SANDBOX_IMAGE_BASE_TOOLS="$(sandbox_image_base_tools)"

if [ $# -gt 0 ]; then
  echo "[ERROR] build-deb.sh does not accept a version argument; version is read from pyproject.toml" >&2
  exit 1
fi

VERSION="$(python3 - <<'PY'
import re
from pathlib import Path
text = Path("pyproject.toml").read_text(encoding="utf-8")
m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
if not m:
    raise SystemExit("Cannot read version from pyproject.toml")
print(m.group(1))
PY
)"

PKG_NAME="mcp-terminal-docker"
DEB_FILE="${OUTPUT_DIR}/${PKG_NAME}_${VERSION}_${ARCH}.deb"

echo "[INFO] Building Debian package ${PKG_NAME} ${VERSION} (image ${DOCKERHUB_REPO}:${VERSION})"

rm -rf "$PKG_WORK"
mkdir -p "$PKG_WORK/DEBIAN" "$OUTPUT_DIR"
cp -a "$DEBIAN_SRC/DEBIAN/"* "$PKG_WORK/DEBIAN/"
cp -a "$DEBIAN_SRC/etc" "$PKG_WORK/"
cp -a "$DEBIAN_SRC/lib" "$PKG_WORK/"

mkdir -p "$PKG_WORK/usr/lib/mcp-terminal" "$PKG_WORK/usr/bin" "$PKG_WORK/usr/share/mcp-terminal" \
  "$PKG_WORK/usr/share/doc/mcp-terminal-docker" "$PKG_WORK/etc/mcp-terminal/mtls_certificates"

install -m 755 "$SCRIPT_DIR/pkg/install-server-config.sh" "$PKG_WORK/usr/lib/mcp-terminal/install-server-config.sh"
install -m 755 "$SCRIPT_DIR/pkg/ensure-mtls-certificates.sh" "$PKG_WORK/usr/lib/mcp-terminal/ensure-mtls-certificates.sh"
install -m 755 "$SCRIPT_DIR/pkg/docker-run.sh" "$PKG_WORK/usr/lib/mcp-terminal/docker-run.sh"
install -m 755 "$SCRIPT_DIR/pkg/pull-sandbox-images.sh" "$PKG_WORK/usr/lib/mcp-terminal/pull-sandbox-images.sh"
install -m 755 "$SCRIPT_DIR/pkg/ensure-host-user.sh" "$PKG_WORK/usr/lib/mcp-terminal/ensure-host-user.sh"
install -m 755 "$SCRIPT_DIR/pkg/prepare_project_layout.py" "$PKG_WORK/usr/lib/mcp-terminal/prepare_project_layout.py"
install -m 755 "$SCRIPT_DIR/pkg/ensure-host-permissions.sh" "$PKG_WORK/usr/lib/mcp-terminal/ensure-host-permissions.sh"
install -m 755 "$SCRIPT_DIR/pkg/ensure-ssh-target-user.sh" "$PKG_WORK/usr/lib/mcp-terminal/ensure-ssh-target-user.sh"
install -m 755 "$SCRIPT_DIR/pkg/manage-session-keys.sh" "$PKG_WORK/usr/lib/mcp-terminal/manage-session-keys.sh"

mkdir -p "$PKG_WORK/etc/mcp-terminal"
: > "$PKG_WORK/etc/mcp-terminal/ssh_known_hosts"
chmod 644 "$PKG_WORK/etc/mcp-terminal/ssh_known_hosts"
install -m 644 "$SCRIPT_DIR/pkg/watch_dir_bind_specs.py" "$PKG_WORK/usr/lib/mcp-terminal/watch_dir_bind_specs.py"
install -m 755 "$SCRIPT_DIR/pkg/mcp-terminal-info" "$PKG_WORK/usr/bin/mcp-terminal-info"
install -m 755 "$SCRIPT_DIR/pkg/mcp-terminal-docker" "$PKG_WORK/usr/bin/mcp-terminal-docker"
install -m 755 "$SCRIPT_DIR/pkg/mcp-terminal-preflight" "$PKG_WORK/usr/bin/mcp-terminal-preflight"
install -m 644 "$SCRIPT_DIR/pkg/image-spec.in" "$PKG_WORK/usr/lib/mcp-terminal/image-spec"
sed -i "s|@DOCKERHUB_REPO@|${DOCKERHUB_REPO}|g; s|@IMAGE_TAG@|${VERSION}|g" \
  "$PKG_WORK/usr/lib/mcp-terminal/image-spec"

install -m 644 "$SCRIPT_DIR/pkg/sandbox-images-spec.in" "$PKG_WORK/usr/lib/mcp-terminal/sandbox-images-spec"
sed -i \
  "s|@SANDBOX_IMAGE_PYTHON_DEV@|${SANDBOX_IMAGE_PYTHON_DEV}|g; \
   s|@SANDBOX_IMAGE_NODE_DEV@|${SANDBOX_IMAGE_NODE_DEV}|g; \
   s|@SANDBOX_IMAGE_BASE_TOOLS@|${SANDBOX_IMAGE_BASE_TOOLS}|g" \
  "$PKG_WORK/usr/lib/mcp-terminal/sandbox-images-spec"

TEMPLATE_SRC="$SCRIPT_DIR/packaging/term_server.json.template"
TEMPLATE_WORK="$PKG_WORK/usr/share/mcp-terminal/term_server.json.template"
mkdir -p "$(dirname "$TEMPLATE_WORK")"
sed "s|@VERSION@|${VERSION}|g" "$TEMPLATE_SRC" >"$TEMPLATE_WORK"
install -m 644 "$TEMPLATE_WORK" "$PKG_WORK/usr/share/doc/mcp-terminal-docker/term_server.json.example"
install -m 644 "$SCRIPT_DIR/README.md" "$PKG_WORK/usr/share/doc/mcp-terminal-docker/README.md"
install -m 644 "$PROJECT_ROOT/mcp_terminal/docs/INFO.md" \
  "$PKG_WORK/usr/share/doc/mcp-terminal-docker/MCP_TERMINAL_INFO.md"

MAN_SRC="$DEBIAN_SRC/man"
INFO_SRC="$DEBIAN_SRC/info"
mkdir -p "$PKG_WORK/usr/share/man/man1" "$PKG_WORK/usr/share/man/man5" "$PKG_WORK/usr/share/info"
for man_page in mcp-terminal-docker.1 mcp-terminal-info.1 mcp-terminal-preflight.1; do
  sed "s|@VERSION@|${VERSION}|g" "$MAN_SRC/$man_page" | gzip -9 -n >"$PKG_WORK/usr/share/man/man1/${man_page}.gz"
done
sed "s|@VERSION@|${VERSION}|g" "$MAN_SRC/mcp-terminal-config.5" | gzip -9 -n >"$PKG_WORK/usr/share/man/man5/mcp-terminal-config.5.gz"
INFO_TEXI_WORK="$(mktemp)"
python3 "$SCRIPT_DIR/pkg/render-info-texi.py" \
  --version "$VERSION" \
  --markdown "$PROJECT_ROOT/mcp_terminal/docs/INFO.md" \
  --output "$INFO_TEXI_WORK"
if command -v makeinfo >/dev/null 2>&1; then
  makeinfo --no-split -o "$PKG_WORK/usr/share/info/mcp-terminal-docker.info" "$INFO_TEXI_WORK"
else
  if [ -f "$INFO_SRC/mcp-terminal-docker.info" ]; then
    sed "s|@VERSION@|${VERSION}|g" "$INFO_SRC/mcp-terminal-docker.info" \
      >"$PKG_WORK/usr/share/info/mcp-terminal-docker.info"
  else
    echo "[ERROR] makeinfo not found and $INFO_SRC/mcp-terminal-docker.info missing" >&2
    echo "[ERROR] Install texinfo or commit a prebuilt .info file" >&2
    rm -f "$INFO_TEXI_WORK"
    exit 1
  fi
fi
rm -f "$INFO_TEXI_WORK"
chmod 644 "$PKG_WORK/usr/share/info/mcp-terminal-docker.info"

sed "s|@VERSION@|${VERSION}|g" "$PKG_WORK/DEBIAN/control" > "$PKG_WORK/DEBIAN/control.tmp"
mv "$PKG_WORK/DEBIAN/control.tmp" "$PKG_WORK/DEBIAN/control"

chmod 755 "$PKG_WORK/DEBIAN/postinst" "$PKG_WORK/DEBIAN/prerm" "$PKG_WORK/DEBIAN/postrm"

dpkg-deb --build --root-owner-group "$PKG_WORK" "$DEB_FILE"

echo "[SUCCESS] Debian package: $DEB_FILE"
ls -lh "$DEB_FILE"
cat <<EOF

Install on the target host:

  sudo dpkg -i '$DEB_FILE'
  sudo apt -f install

This pulls package dependencies (docker.io, adduser, python3, curl, …) via apt.

EOF
