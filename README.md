# edo-tensei

Claude Codeの長期記憶。過去の会話を保存・検索し、文脈を引き継ぐ。

## 特徴

- **ハイブリッド検索** — FTS5 trigram（キーワード）+ Ruri v3（ベクトル）をRRFで統合
- **SQLite 1ファイル** — 外部サービス不要、`~/.edo-tensei/memory.db` に全データ格納
- **LLM不使用で保存** — 埋め込み生成はローカルモデル（Ruri v3-310m）、トークン消費ゼロ
- **時間減衰** — 半減期60日、古い記憶ほどスコアが下がる
- **自動保存** — SessionEnd hookでセッション終了時に自動保存。手動操作ゼロ

## セットアップ

```bash
git clone https://github.com/nayukata/edo-tensei.git
cd edo-tensei
uv sync
```

初回実行時にRuri v3モデル（約1.2GB）が自動ダウンロードされる。

## Claude Codeへの登録

### 1. MCPサーバーの登録

```bash
claude mcp add --transport stdio --scope user edo-tensei -- \
  uv run --directory /path/to/edo-tensei python -m edo_tensei.server
```

全プロジェクトから以下のツールが使える。

| ツール | 説明 |
|--------|------|
| `search_memory(query, limit)` | 過去の会話を検索 |
| `save_transcript(transcript, session_id)` | 会話を記憶として保存 |
| `memory_stats()` | 統計情報を表示 |

### 2. SessionEnd hookの登録

`~/.claude/settings.json` に以下を追加する。

```json
{
  "hooks": {
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/edo-tensei/hooks/on-session-end.sh"
          }
        ]
      }
    ]
  }
}
```

`/path/to/edo-tensei` は実際のclone先パスに置き換える。

### 3. CLAUDE.mdへの記述（推奨）

Claudeが自発的に `search_memory` を呼ぶよう、`~/.claude/CLAUDE.md` に以下を追加する。

```markdown
## 記憶 (edo-tensei)

過去の会話記憶がedo-tensei MCPサーバーに保存されている。積極的に活用すること。

### 必ず検索するタイミング
- 新しいタスク・機能実装・設計議論を始める時
- バグ修正や問題解決に取り組む時
- 「前に」「以前」「あの時の」「前回」等のキーワードがある時

### 検索のやり方
- 迷ったらとりあえず `search_memory` を呼ぶ。コストはほぼゼロ
- 検索結果がヒットしたら、過去の文脈・判断理由を踏まえて回答する
- ヒットしなければそのまま進めてよい
```

## CLI

```bash
uv run edo-tensei save transcript.jsonl          # transcriptを保存
uv run edo-tensei search "API設計"               # 記憶を検索
uv run edo-tensei stats                           # 統計情報
uv run edo-tensei serve                           # MCPサーバー起動
```

## 検索の仕組み

```
クエリ
 ├─ FTS5 trigram → キーワードマッチ（固有名詞に強い）
 ├─ Ruri v3     → 意味的類似度（言い換えに強い）
 └─ RRF統合 × 時間減衰（半減期60日） → 最終スコア
```

## 技術スタック

| 項目 | 詳細 |
|------|------|
| 埋め込みモデル | [Ruri v3-310m](https://huggingface.co/cl-nagoya/ruri-v3-310m)（日本語特化, 768次元） |
| キーワード検索 | SQLite FTS5 trigram トークナイザ |
| ベクトル検索 | [sqlite-vec](https://github.com/asg017/sqlite-vec) |
| 統合手法 | RRF（Reciprocal Rank Fusion） |
| 時間減衰 | 半減期60日の指数減衰 |

## 参考

- [Claude Codeに長期記憶を実装した](https://zenn.dev/noprogllama/articles/7c24b2c2410213) — 設計思想の元になった記事
