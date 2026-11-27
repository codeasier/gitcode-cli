#!/usr/bin/env bash
set -euo pipefail

LABEL="com.codeasier.orca-gitcode-linker"
ENV_LABEL="com.codeasier.orca-gitcode-env"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
PORT="${PORT:-8765}"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
ENV_PLIST="$HOME/Library/LaunchAgents/$ENV_LABEL.plist"
LOG_DIR="$HOME/Library/Logs"
LOG_FILE="$LOG_DIR/orca-gitcode-linker.log"
TOKEN_FILE="$HOME/.config/orca-gitcode-linker/token"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This installer targets macOS. Install and run the orca-gitcode-linker command manually on other platforms." >&2
  exit 1
fi

if [[ "${1:-}" == "--uninstall" ]]; then
  launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
  launchctl bootout "gui/$(id -u)/$ENV_LABEL" >/dev/null 2>&1 || true
  rm -f "$PLIST" "$ENV_PLIST" "$TOKEN_FILE"
  launchctl unsetenv ORCA_GITEA_API_BASE_URL >/dev/null 2>&1 || true
  launchctl unsetenv ORCA_GITEA_TOKEN >/dev/null 2>&1 || true
  echo "Uninstalled $LABEL. Quit and reopen Orca to drop the adapter environment."
  exit 0
fi

"$PYTHON_BIN" - <<'PY'
import sys

if sys.version_info < (3, 9):
    raise SystemExit("Python 3.9 or newer is required.")
PY

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"

LINKER_BIN="${ORCA_GITCODE_LINKER_BIN:-$(command -v orca-gitcode-linker || true)}"
PYTHONPATH_SRC=""
if [[ -n "$LINKER_BIN" ]]; then
  ARGS=("$LINKER_BIN" "--port" "$PORT")
else
  PYTHONPATH_SRC="$(cd "$SCRIPT_DIR/../src" && pwd)"
  if [[ ! -f "$PYTHONPATH_SRC/orca_gitcode_linker/linker.py" ]]; then
    echo "orca-gitcode-linker is not on PATH and the source tree is missing at $PYTHONPATH_SRC" >&2
    exit 1
  fi
  ARGS=("$PYTHON_BIN" "-m" "orca_gitcode_linker" "--port" "$PORT")
fi
if [[ -n "${GC_TOKEN:-}" ]]; then
  mkdir -p "$(dirname "$TOKEN_FILE")"
  umask 077
  printf '%s\n' "$GC_TOKEN" > "$TOKEN_FILE"
  ARGS+=("--token-file" "$TOKEN_FILE")
fi

PLIST_PYTHONPATH="$PYTHONPATH_SRC" "$PYTHON_BIN" - "$PLIST" "${ARGS[@]}" "$LOG_FILE" "$LABEL" <<'PY'
import os
import plistlib
import sys
from pathlib import Path

plist_path = Path(sys.argv[1])
args = sys.argv[2:-2]
log_file = sys.argv[-2]
label = sys.argv[-1]
environment = {"PYTHONUNBUFFERED": "1"}
pythonpath = os.environ.get("PLIST_PYTHONPATH", "")
if pythonpath:
    environment["PYTHONPATH"] = pythonpath
payload = {
    "Label": label,
    "ProgramArguments": args,
    "RunAtLoad": True,
    "KeepAlive": True,
    "ThrottleInterval": 5,
    "ProcessType": "Background",
    "StandardOutPath": log_file,
    "StandardErrorPath": log_file,
    "EnvironmentVariables": environment,
}
with plist_path.open("wb") as output:
    plistlib.dump(payload, output)
PY

"$PYTHON_BIN" - "$ENV_PLIST" "$ENV_LABEL" "$PORT" <<'PY'
import plistlib
import sys
from pathlib import Path

plist_path = Path(sys.argv[1])
label = sys.argv[2]
port = sys.argv[3]
command = (
    f"launchctl setenv ORCA_GITEA_API_BASE_URL http://127.0.0.1:{port}/api/v1 && "
    "launchctl setenv ORCA_GITEA_TOKEN orca-gitcode-linker"
)
payload = {
    "Label": label,
    "ProgramArguments": ["/bin/sh", "-c", command],
    "RunAtLoad": True,
    "ProcessType": "Background",
}
with plist_path.open("wb") as output:
    plistlib.dump(payload, output)
PY

launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/$LABEL"
launchctl bootout "gui/$(id -u)/$ENV_LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$ENV_PLIST"
launchctl setenv ORCA_GITEA_API_BASE_URL "http://127.0.0.1:$PORT/api/v1"
launchctl setenv ORCA_GITEA_TOKEN "orca-gitcode-linker"

HEALTH=""
for _ in $(seq 1 20); do
  HEALTH="$(curl -fsS "http://127.0.0.1:$PORT/api/v1/healthz" 2>/dev/null || true)"
  if [[ -n "$HEALTH" ]]; then
    break
  fi
  sleep 0.5
done

if [[ -n "$HEALTH" ]]; then
  if [[ "$HEALTH" != *'"service":"orca-gitcode-linker"'* ]]; then
    echo "Port $PORT is answering, but not with this adapter. Stop that process or set PORT." >&2
    exit 1
  fi
  if [[ "$HEALTH" != *'"token_configured":true'* ]]; then
    echo "Warning: no GitCode token found. Run gc auth login or export GC_TOKEN, then reinstall." >&2
  fi
  echo "Adapter is running on http://127.0.0.1:$PORT/api/v1"
  echo "Orca environment set: ORCA_GITEA_API_BASE_URL and ORCA_GITEA_TOKEN"
  echo "Quit and reopen Orca, then open a GitCode worktree."
  exit 0
fi

echo "Adapter did not become healthy. Check $LOG_FILE" >&2
tail -n 20 "$LOG_FILE" >&2 || true
exit 1
