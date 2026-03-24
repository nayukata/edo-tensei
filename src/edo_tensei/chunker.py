"""Transcript → Q&Aチャンク分割.

Claude Codeのtranscriptをパースし、Q&A形式のチャンクに分割する。
チャンクサイズはトークン数で制御し、Ruri v3の8192トークン制限内に収める。
"""

import json


def parse_jsonl_transcript(jsonl_text: str) -> list[dict]:
    """Claude CodeのJSONL transcript をパースし、user/assistantメッセージを抽出."""
    messages = []
    for line in jsonl_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        entry_type = entry.get("type", "")
        if entry_type not in ("user", "assistant"):
            continue

        msg = entry.get("message")
        if not msg or not isinstance(msg, dict):
            continue

        role = msg.get("role", "")
        if role not in ("user", "assistant"):
            continue

        messages.append(msg)
    return messages


def _extract_text(message: dict) -> str:
    """メッセージからテキスト内容を抽出."""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return str(content)


def _estimate_tokens(text: str) -> int:
    """トークン数を推定する.

    日本語は1文字あたり約2-3トークン、英語は1単語あたり約1.3トークン。
    安全側に倒して日本語2.5、英語1.5で推定する。
    厳密なトークナイズはモデル依存のため、推定値を使う。
    """
    ja_chars = sum(1 for c in text if ord(c) > 0x2FFF)
    en_chars = len(text) - ja_chars
    return int(ja_chars * 2.5 + en_chars * 0.4)


MAX_TOKENS = 7000  # Ruri v3の8192制限に余裕を持たせる


def _truncate_by_tokens(text: str, max_tokens: int = MAX_TOKENS) -> str:
    """トークン数推定でテキストを切り詰める."""
    if _estimate_tokens(text) <= max_tokens:
        return text

    # バイナリサーチで切り詰め位置を決定
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if _estimate_tokens(text[:mid]) <= max_tokens:
            low = mid
        else:
            high = mid - 1

    return text[:low] + "...(truncated)"


def chunk_transcript(messages: list[dict]) -> list[str]:
    """メッセージリストをQ&Aチャンクに分割.

    ユーザーの質問とアシスタントの回答をペアにして1チャンクとする。
    連続するassistantメッセージは1つの回答として結合する。
    """
    chunks: list[str] = []
    current_user_msg: str | None = None
    current_assistant_parts: list[str] = []

    def _flush() -> None:
        nonlocal current_user_msg, current_assistant_parts
        assistant_text = "\n".join(current_assistant_parts).strip()

        if current_user_msg and assistant_text:
            chunk = f"Q: {current_user_msg}\nA: {assistant_text}"
        elif current_user_msg:
            chunk = f"Q: {current_user_msg}"
        elif assistant_text:
            chunk = f"A: {assistant_text}"
        else:
            current_user_msg = None
            current_assistant_parts = []
            return

        chunks.append(_truncate_by_tokens(chunk))
        current_user_msg = None
        current_assistant_parts = []

    for msg in messages:
        role = msg.get("role", "")
        text = _extract_text(msg)

        if not text.strip():
            continue

        if role in ("user", "human"):
            _flush()
            current_user_msg = text.strip()
        elif role == "assistant":
            current_assistant_parts.append(text.strip())

    _flush()
    return chunks


def chunk_plain_text(text: str, max_tokens: int = 3000) -> list[str]:
    """プレーンテキストをトークン数推定で分割（フォールバック用）."""
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        candidate = (current + "\n\n" + para).strip() if current else para
        if _estimate_tokens(candidate) > max_tokens and current:
            chunks.append(current.strip())
            current = para
        else:
            current = candidate

    if current.strip():
        chunks.append(current.strip())

    return chunks
