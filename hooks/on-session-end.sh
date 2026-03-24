#!/bin/bash
# SessionEnd hook: 会話transcriptをedo-tenseiに自動保存
# 環境非依存: スクリプト自身のディレクトリからプロジェクトパスを解決

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

LOG="$HOME/.edo-tensei/hook.log"
mkdir -p "$HOME/.edo-tensei"

# ログローテーション: 1MB超えたら切り詰め
if [ -f "$LOG" ] && [ "$(stat -f%z "$LOG" 2>/dev/null || stat -c%s "$LOG" 2>/dev/null || echo 0)" -gt 1048576 ]; then
  tail -100 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

INPUT=$(cat)
echo "[$(date)] Hook fired." >> "$LOG"

TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)

echo "[$(date)] transcript=$TRANSCRIPT_PATH session=$SESSION_ID" >> "$LOG"

if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
  echo "[$(date)] ERROR: transcript not found at '$TRANSCRIPT_PATH'" >> "$LOG"
  exit 0
fi

# uv をPATHから探す。見つからなければ一般的な場所を試す
UV_CMD="$(command -v uv 2>/dev/null || echo "")"
if [ -z "$UV_CMD" ]; then
  for candidate in /opt/homebrew/bin/uv "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
    if [ -x "$candidate" ]; then
      UV_CMD="$candidate"
      break
    fi
  done
fi

if [ -z "$UV_CMD" ]; then
  echo "[$(date)] ERROR: uv not found in PATH" >> "$LOG"
  exit 0
fi

# バックグラウンド実行 + タイムアウト（最大5分で強制終了）
# macOSにはtimeoutコマンドがないため、シェルで実装
TIMEOUT=300
(
  "$UV_CMD" run --directory "$PROJECT_DIR" \
    edo-tensei save "$TRANSCRIPT_PATH" --session-id "$SESSION_ID" \
    >> "$LOG" 2>&1 &
  SAVE_PID=$!
  (sleep "$TIMEOUT" && kill "$SAVE_PID" 2>/dev/null && echo "[$(date)] TIMEOUT: killed save process (pid=$SAVE_PID)" >> "$LOG") &
  WATCHDOG_PID=$!
  wait "$SAVE_PID" 2>/dev/null
  kill "$WATCHDOG_PID" 2>/dev/null
) &
disown
echo "[$(date)] Save kicked off (timeout=${TIMEOUT}s)" >> "$LOG"

exit 0
