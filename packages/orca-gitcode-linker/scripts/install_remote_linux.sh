#!/usr/bin/env bash
set -euo pipefail

HOST="${1:-}"
PORT="${PORT:-8787}"
REMOTE_DIR="${REMOTE_DIR:-.local/share/orca-gitcode-linker}"
SERVICE_NAME="orca-gitcode-linker.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "$HOST" ]]; then
  echo "Usage: $0 <ssh-host> [port-via-PORT]" >&2
  exit 1
fi

ssh "$HOST" "mkdir -p \"\$HOME/$REMOTE_DIR\""
scp -r "$SCRIPT_DIR/../src/orca_gitcode_linker" "$HOST:$REMOTE_DIR/"
ssh "$HOST" "REMOTE_DIR='$REMOTE_DIR' PORT='$PORT' SERVICE_NAME='$SERVICE_NAME' bash -s" <<'REMOTE'
set -euo pipefail
rm -f "$HOME/$REMOTE_DIR/gitcode_links.py"
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/$SERVICE_NAME" <<UNIT
[Unit]
Description=GitCode Gitea-compatible adapter for Orca

[Service]
Type=simple
ExecStart=/usr/bin/python3 -m orca_gitcode_linker --port $PORT
Environment=PYTHONPATH=$HOME/$REMOTE_DIR
Environment=PYTHONUNBUFFERED=1
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now "$SERVICE_NAME"

PAM_ENV="$HOME/.pam_environment"
touch "$PAM_ENV"
chmod 600 "$PAM_ENV"
grep -v '^ORCA_GITEA_API_BASE_URL ' "$PAM_ENV" > "$PAM_ENV.tmp" || true
grep -v '^ORCA_GITEA_TOKEN ' "$PAM_ENV.tmp" > "$PAM_ENV" || true
rm -f "$PAM_ENV.tmp"
printf 'ORCA_GITEA_API_BASE_URL DEFAULT=http://127.0.0.1:%s/api/v1\n' "$PORT" >> "$PAM_ENV"
printf 'ORCA_GITEA_TOKEN DEFAULT=orca-gitcode-linker\n' >> "$PAM_ENV"

for _ in $(seq 1 20); do
  if curl -fsS "http://127.0.0.1:$PORT/api/v1/healthz" >/dev/null 2>&1; then
    echo "Adapter is running on http://127.0.0.1:$PORT/api/v1"
    echo "Reconnect or restart this Orca environment once so orcad inherits ORCA_GITEA_* from ~/.pam_environment."
    exit 0
  fi
  sleep 0.5
done
echo "Adapter did not become healthy; check: journalctl --user -u $SERVICE_NAME" >&2
exit 1
REMOTE
