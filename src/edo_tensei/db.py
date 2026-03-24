"""SQLite database with FTS5 trigram + sqlite-vec for hybrid search."""

import sqlite3
import struct
from contextlib import contextmanager
from pathlib import Path

import sqlite_vec

DB_PATH = Path.home() / ".edo-tensei" / "memory.db"
VECTOR_DIM = 768  # Ruri v3-310m


def serialize_f32(vector: list[float]) -> bytes:
    """list[float] → sqlite-vec用のbytes."""
    return struct.pack(f"{len(vector)}f", *vector)


@contextmanager
def open_db(db_path: Path | None = None):
    """DB接続をコンテキストマネージャで管理。初期化も自動実行."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path))
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    db.row_factory = sqlite3.Row
    _init_schema(db)
    try:
        yield db
    finally:
        db.close()


def _init_schema(db: sqlite3.Connection) -> None:
    db.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            content TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            content,
            tokenize='trigram'
        );
    """)

    try:
        db.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS memories_vec "
            f"USING vec0(embedding float[{VECTOR_DIM}])"
        )
    except sqlite3.OperationalError:
        pass  # already exists

    db.commit()


def ensure_session(db: sqlite3.Connection, session_id: str) -> None:
    db.execute(
        "INSERT OR IGNORE INTO sessions (session_id) VALUES (?)",
        (session_id,),
    )


def insert_memory(
    db: sqlite3.Connection,
    session_id: str,
    content: str,
    chunk_index: int,
    embedding: list[float],
) -> int:
    """メモリ（チャンク）を保存し、FTS5とベクトルインデックスに同期."""
    cursor = db.execute(
        "INSERT INTO memories (session_id, content, chunk_index) VALUES (?, ?, ?)",
        (session_id, content, chunk_index),
    )
    memory_id = cursor.lastrowid

    db.execute(
        "INSERT INTO memories_fts (rowid, content) VALUES (?, ?)",
        (memory_id, content),
    )

    db.execute(
        "INSERT INTO memories_vec (rowid, embedding) VALUES (?, ?)",
        (memory_id, serialize_f32(embedding)),
    )

    return memory_id


_BATCH_SIZE = 500


def clear_session_memories(db: sqlite3.Connection, session_id: str) -> int:
    """既存のセッションデータを削除（再保存時の重複防止）.

    SQLITE_MAX_VARIABLE_NUMBER を超えないようバッチ分割する。
    """
    rows = db.execute(
        "SELECT id FROM memories WHERE session_id = ?", (session_id,)
    ).fetchall()
    if not rows:
        return 0

    ids = [r["id"] for r in rows]

    for i in range(0, len(ids), _BATCH_SIZE):
        batch = ids[i : i + _BATCH_SIZE]
        placeholders = ",".join("?" * len(batch))
        db.execute(f"DELETE FROM memories_fts WHERE rowid IN ({placeholders})", batch)
        db.execute(f"DELETE FROM memories_vec WHERE rowid IN ({placeholders})", batch)
        db.execute(f"DELETE FROM memories WHERE id IN ({placeholders})", batch)

    return len(ids)


def fts_search(db: sqlite3.Connection, query: str, limit: int = 20) -> list[dict]:
    """FTS5 trigram全文検索（フレーズマッチ）."""
    if len(query) < 3:
        return []

    escaped = query.replace('"', '""')

    try:
        rows = db.execute(
            """
            SELECT m.id, m.content, m.session_id, m.created_at,
                   rank AS score
            FROM memories_fts fts
            JOIN memories m ON m.id = fts.rowid
            WHERE memories_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (f'"{escaped}"', limit),
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


def vec_search(
    db: sqlite3.Connection, embedding: list[float], limit: int = 20
) -> list[dict]:
    """sqlite-vecベクトル類似度検索."""
    rows = db.execute(
        """
        SELECT v.rowid AS id, v.distance,
               m.content, m.session_id, m.created_at
        FROM memories_vec v
        JOIN memories m ON m.id = v.rowid
        WHERE v.embedding MATCH ?
            AND k = ?
        ORDER BY v.distance
        """,
        (serialize_f32(embedding), limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_stats(db: sqlite3.Connection) -> dict:
    session_count = db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    memory_count = db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    return {"sessions": session_count, "memories": memory_count}
