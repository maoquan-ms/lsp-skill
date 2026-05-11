#!/usr/bin/env bash
# install-jdtls.sh — Auto-install Eclipse JDT Language Server on Linux
set -euo pipefail

# Update release date
# ---------- Configuration ----------
JDTLS_VERSION_LATEST=$(curl -Ls 'https://download.eclipse.org/jdtls/snapshots/latest.txt')
DOWNLOAD_URL="https://download.eclipse.org/jdtls/snapshots/$JDTLS_VERSION_LATEST"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/share/jdtls}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"

# ---------- Helpers ----------
info()  { printf '\033[1;32m[INFO]\033[0m  %s\n' "$*"; }
warn()  { printf '\033[1;33m[WARN]\033[0m  %s\n' "$*"; }
error() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

check_cmd() {
  command -v "$1" >/dev/null 2>&1 || error "'$1' is required but not found. Please install it first."
}

# ---------- Pre-checks ----------
check_cmd java
check_cmd curl
check_cmd tar

JAVA_VER=$(java -version 2>&1 | head -1 | sed -E 's/.*"([0-9]+).*/\1/')
if [ "$JAVA_VER" -lt 17 ] 2>/dev/null; then
  error "JDK 17+ is required (detected version $JAVA_VER)"
fi
info "Detected Java version: $JAVA_VER"

# ---------- Download & Install ----------
if [ -d "$INSTALL_DIR" ]; then
  if [ "${FORCE_REINSTALL:-0}" = "1" ]; then
    info "Force reinstall: removing $INSTALL_DIR"
    rm -rf "$INSTALL_DIR"
  else
    warn "Install directory already exists: $INSTALL_DIR"
    read -rp "Remove and reinstall? [y/N] " ans
    case "$ans" in
      [yY]*) rm -rf "$INSTALL_DIR" ;;
      *)     info "Aborted."; exit 0 ;;
    esac
  fi
fi

mkdir -p "$INSTALL_DIR"
TMPFILE=$(mktemp /tmp/jdtls-XXXXXX.tar.gz)
trap 'rm -f "$TMPFILE"' EXIT

info "Downloading jdtls ${JDTLS_VERSION_LATEST} ..."
curl -fSL --progress-bar -o "$TMPFILE" "$DOWNLOAD_URL" \
  || error "Download failed. Check version/timestamp or network connection.\n  URL: $DOWNLOAD_URL"

info "Extracting to $INSTALL_DIR ..."
tar -xzf "$TMPFILE" -C "$INSTALL_DIR"

# ---------- Create launcher script ----------
mkdir -p "$BIN_DIR"
LAUNCHER="$BIN_DIR/jdtls"

cat > "$LAUNCHER" << 'SCRIPT'
#!/usr/bin/env bash
# jdtls launcher — auto-generated
set -euo pipefail

JDTLS_HOME="${JDTLS_HOME:-$HOME/.local/share/jdtls}"
DATA_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/jdtls-workspace"

CONFIG="$JDTLS_HOME/config_linux"
LAUNCHER_JAR=$(find "$JDTLS_HOME/plugins" -name 'org.eclipse.equinox.launcher_*.jar' | head -1)

if [ -z "$LAUNCHER_JAR" ]; then
  echo "Error: Cannot find equinox launcher jar in $JDTLS_HOME/plugins" >&2
  exit 1
fi

exec java \
  -Declipse.application=org.eclipse.jdt.ls.core.id1 \
  -Dosgi.bundles.defaultStartLevel=4 \
  -Declipse.product=org.eclipse.jdt.ls.core.product \
  -Dlog.level=ALL \
  -Xms256m \
  -Xmx1G \
  --add-modules=ALL-SYSTEM \
  --add-opens java.base/java.util=ALL-UNNAMED \
  --add-opens java.base/java.lang=ALL-UNNAMED \
  -jar "$LAUNCHER_JAR" \
  -configuration "$CONFIG" \
  -data "$DATA_DIR" \
  "$@"
SCRIPT

chmod +x "$LAUNCHER"

# ---------- PATH hint ----------
info "Installed successfully!"
info "  jdtls home : $INSTALL_DIR"
info "  launcher   : $LAUNCHER"

if ! echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
  warn "$BIN_DIR is not in your PATH. Add it with:"
  echo "  export PATH=\"$BIN_DIR:\$PATH\""
fi

info "Run 'jdtls' to start the language server."
