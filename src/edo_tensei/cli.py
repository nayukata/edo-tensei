"""CLI entry point for edo-tensei."""

import argparse
import json
import sys

from .db import get_stats, open_db
from .search import hybrid_search
from .service import save_transcript


def cmd_save(args: argparse.Namespace) -> None:
    """transcriptファイルを読み込んで記憶として保存."""
    if args.file == "-":
        transcript = sys.stdin.read()
    else:
        with open(args.file) as f:
            transcript = f.read()

    print("Ruri v3で埋め込み生成中...")
    result = save_transcript(transcript, session_id=args.session_id)

    if result["chunks"] == 0:
        print("保存するチャンクがありません。")
        return

    msg = f"セッション '{result['session_id']}' に {result['chunks']} 件保存しました。"
    if result["cleared"]:
        msg += f"（旧データ {result['cleared']} 件を置換）"
    print(msg)


def cmd_search(args: argparse.Namespace) -> None:
    """記憶を検索."""
    results = hybrid_search(args.query, limit=args.limit)

    if not results:
        print("該当する記憶が見つかりませんでした。")
        return

    for i, r in enumerate(results, 1):
        print(f"\n--- 記憶 {i} (score: {r['rrf_score']}, date: {r['created_at']}) ---")
        print(r["content"])


def cmd_stats(args: argparse.Namespace) -> None:
    """統計情報を表示."""
    with open_db() as db:
        stats = get_stats(db)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def cmd_serve(args: argparse.Namespace) -> None:
    """MCPサーバーを起動."""
    from .server import main as serve_main

    serve_main()


def main() -> None:
    parser = argparse.ArgumentParser(description="edo-tensei: Claude Code長期記憶")
    sub = parser.add_subparsers(dest="command")

    p_save = sub.add_parser("save", help="transcriptを記憶として保存")
    p_save.add_argument("file", help="transcriptファイルのパス（-でstdin）")
    p_save.add_argument("--session-id", default="", help="セッションID")
    p_save.set_defaults(func=cmd_save)

    p_search = sub.add_parser("search", help="記憶を検索")
    p_search.add_argument("query", help="検索クエリ")
    p_search.add_argument("--limit", type=int, default=5, help="結果数")
    p_search.set_defaults(func=cmd_search)

    p_stats = sub.add_parser("stats", help="統計情報")
    p_stats.set_defaults(func=cmd_stats)

    p_serve = sub.add_parser("serve", help="MCPサーバー起動")
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
