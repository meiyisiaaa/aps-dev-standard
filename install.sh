#!/usr/bin/env sh
set -eu

REPO="${APS_REPO:-meiyisiaaa/aps-dev-standard}"
VERSION="${APS_VERSION:-latest}"

case "$REPO" in
  */*) ;;
  *) echo "APS installer is not configured. Set APS_REPO=owner/repo or run scripts/configure_repository.py before publishing." >&2; exit 2 ;;
esac

PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  if command -v python3 >/dev/null 2>&1; then PYTHON=python3
  elif command -v python >/dev/null 2>&1; then PYTHON=python
  else echo "Python 3 is required." >&2; exit 2
  fi
fi

TMP="$(mktemp -d 2>/dev/null || mktemp -d -t aps)"
trap 'rm -rf "$TMP"' EXIT INT TERM

fetch() {
  url="$1" out="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --retry 2 "$url" -o "$out"
  elif command -v wget >/dev/null 2>&1; then
    wget -q "$url" -O "$out"
  else
    echo "curl or wget is required." >&2
    exit 2
  fi
}

verify_checksum() {
  "$PYTHON" - "$1" "$2" <<'PY'
import hashlib
import re
import sys
from pathlib import Path

asset, checksum = map(Path, sys.argv[1:])
match = next(
    (re.match(r"^\s*([0-9a-fA-F]{64})\s+\S+\s*$", line) for line in checksum.read_text(encoding="utf-8").splitlines() if line.strip()),
    None,
)
if not match:
    raise SystemExit("invalid SHA-256 sidecar")
h = hashlib.sha256()
with asset.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        h.update(chunk)
if h.hexdigest().lower() != match.group(1).lower():
    raise SystemExit("release SHA-256 mismatch")
PY
}

ASSET="$TMP/aps.zip"
CHECKSUM="$TMP/aps.zip.sha256"
if [ "$VERSION" = "latest" ]; then
  API="https://api.github.com/repos/$REPO/releases/latest"
  META="$TMP/release.json"
  if fetch "$API" "$META" 2>/dev/null; then
    TAG="$($PYTHON - "$META" <<'PY'
import json,sys
try:
    print(json.load(open(sys.argv[1], encoding='utf-8')).get('tag_name',''))
except Exception:
    print('')
PY
)"
  else
    TAG=""
  fi
else
  TAG="$VERSION"
fi

case "${TAG:-}" in
  ""|v*) ;;
  *) TAG="v$TAG" ;;
esac

DOWNLOADED=0
if [ -n "${TAG:-}" ]; then
  URL="https://github.com/$REPO/releases/download/$TAG/APS_CLI_${TAG#v}.zip"
  if fetch "$URL" "$ASSET" 2>/dev/null; then
    if ! fetch "${URL}.sha256" "$CHECKSUM" 2>/dev/null; then
      echo "Release asset has no downloadable SHA-256 sidecar." >&2
      exit 1
    fi
    if ! verify_checksum "$ASSET" "$CHECKSUM"; then
      echo "Release asset SHA-256 verification failed." >&2
      exit 1
    fi
    DOWNLOADED=1
  fi
fi

if [ "$DOWNLOADED" -ne 1 ]; then
  if [ "${APS_ALLOW_MAIN_FALLBACK:-0}" != "1" ]; then
    echo "No verified release asset is available. Set APS_ALLOW_MAIN_FALLBACK=1 to use the mutable main branch explicitly." >&2
    exit 1
  fi
  echo "No verified release asset; explicitly using the mutable main branch source archive."
  fetch "https://github.com/$REPO/archive/refs/heads/main.zip" "$ASSET"
fi

EXTRACT="$TMP/extract"
mkdir -p "$EXTRACT"
$PYTHON - "$ASSET" "$EXTRACT" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    z.extractall(sys.argv[2])
PY

INSTALLER="$($PYTHON - "$EXTRACT" <<'PY'
from pathlib import Path
import sys
root=Path(sys.argv[1])
files=list(root.rglob('install_cli.py'))
if not files:
    raise SystemExit(2)
# Prefer the shallowest installer.
files.sort(key=lambda p: len(p.parts))
print(files[0])
PY
)"

exec "$PYTHON" "$INSTALLER" "$@"
