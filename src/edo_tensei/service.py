"""保存ロジックの共通化.

parse → chunk → embed → save のフローを1箇所にまとめる。
server.py と cli.py はこのモジュールを呼ぶだけ。
"""

import uuid
from pathlib import Path

from .chunker import chunk_plain_text, chunk_transcript, parse_jsonl_transcript
from .db import clear_session_memories, ensure_session, insert_memory, open_db
from .embedder import embed_documents


def save_transcript(
    transcript: str,
    session_id: str = "",
    db_path: Path | None = None,
) -> dict:
    """会話transcriptを記憶として保存する.

    Returns:
        保存結果の辞書 {"session_id": str, "chunks": int, "cleared": int}
    """
    if not session_id:
        session_id = f"session-{uuid.uuid4().hex[:12]}"

    # JSONL形式か判定してチャンク化
    try:
        messages = parse_jsonl_transcript(transcript)
        chunks = chunk_transcript(messages) if messages else chunk_plain_text(transcript)
    except Exception:
        chunks = chunk_plain_text(transcript)

    if not chunks:
        return {"session_id": session_id, "chunks": 0, "cleared": 0}

    # Ruri v3でバッチ埋め込み生成
    embeddings = embed_documents(chunks)

    # DB保存（1トランザクション）
    with open_db(db_path) as db:
        ensure_session(db, session_id)
        cleared = clear_session_memories(db, session_id)

        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            insert_memory(db, session_id, chunk, i, emb)

        db.commit()

    return {"session_id": session_id, "chunks": len(chunks), "cleared": cleared}
