#!/bin/bash
# 保存処理の実体。on-session-end.sh から nohup で呼ばれる。
# タイムアウト付き。

UV_CMD="$1"
PROJECT_DIR="$2"
TRANSCRIPT_PATH="$3"
SESSION_ID="$4"
LOG="$5"
TIMEOUT="${6:-300}"

"$UV_CMD" run --directory "$PROJECT_DIR" \
  edo-tensei save "$TRANSCRIPT_PATH" --session-id "$SESSION_ID" \
  >> "$LOG" 2>&1 &
SAVE_PID=$!

# ウォッチドッグ: タイムアウトで強制終了
(sleep "$TIMEOUT" && kill "$SAVE_PID" 2>/dev/null && echo "[$(date)] TIMEOUT: killed save (pid=$SAVE_PID)" >> "$LOG") &
WATCHDOG_PID=$!

wait "$SAVE_PID" 2>/dev/null
kill "$WATCHDOG_PID" 2>/dev/null
