"""MCP Server: Claude Codeからtool呼び出しで記憶を保存・検索."""

import json

from mcp.server.fastmcp import FastMCP

from .db import get_stats, open_db
from .search import hybrid_search
from .service import save_transcript as _save_transcript

mcp = FastMCP("edo-tensei")


@mcp.tool()
def search_memory(query: str, limit: int = 5) -> str:
    """過去の会話記憶を検索する.

    キーワード検索（FTS5 trigram）とベクトル検索（Ruri v3）を
    RRF（Reciprocal Rank Fusion）で統合したハイブリッド検索。
    時間減衰あり（半減期60日）。

    Args:
        query: 検索クエリ
        limit: 返す結果の最大数（デフォルト5）
    """
    results = hybrid_search(query, limit=limit)

    if not results:
        return "該当する記憶が見つかりませんでした。"

    output = []
    for i, r in enumerate(results, 1):
        output.append(
            f"--- 記憶 {i} (score: {r['rrf_score']}, "
            f"session: {r['session_id']}, "
            f"date: {r['created_at']}) ---\n"
            f"{r['content']}"
        )
    return "\n\n".join(output)


@mcp.tool()
def save_transcript(transcript: str, session_id: str = "") -> str:
    """会話のtranscriptを記憶として保存する.

    transcriptをQ&Aチャンクに分割し、Ruri v3でベクトル化して
    SQLiteに保存する。JSONL形式とプレーンテキスト形式に対応。

    Args:
        transcript: 会話のtranscript（JSONL形式またはプレーンテキスト）
        session_id: セッションID（空の場合は自動生成）
    """
    result = _save_transcript(transcript, session_id)

    if result["chunks"] == 0:
        return "保存するチャンクがありませんでした。"

    msg = f"セッション '{result['session_id']}' に {result['chunks']} 件のチャンクを保存しました。"
    if result["cleared"]:
        msg += f"（旧データ {result['cleared']} 件を置換）"
    return msg


@mcp.tool()
def memory_stats() -> str:
    """記憶の統計情報を表示する."""
    with open_db() as db:
        stats = get_stats(db)
    return json.dumps(stats, ensure_ascii=False, indent=2)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
