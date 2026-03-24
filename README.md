# edo-tensei

Claude Codeの長期記憶。過去の会話を保存・検索し、文脈を引き継ぐ。

## 特徴

- **ハイブリッド検索** — FTS5 trigram（キーワード）+ Ruri v3（ベクトル）をRRFで統合
- **SQLite 1ファイル** — 外部サービス不要、`~/.edo-tensei/memory.db` に全データ格納
- **LLM不使用で保存** — 埋め込み生成はローカルモデル（Ruri v3-310m ONNX）、トークン消費ゼロ
- **軽量ランタイム** — ONNX Runtimeで推論。PyTorch不要でメモリ消費を大幅削減
- **時間減衰** — 半減期60日、古い記憶ほどスコアが下がる
- **自動保存** — SessionEnd hookでセッション終了時に自動保存。手動操作ゼロ

## セットアップ

```bash
git clone https://github.com/nayukata/edo-tensei.git
cd edo-tensei
uv sync
```

### ONNXモデルの準備（初回のみ）

Ruri v3をONNX形式に変換する。PyTorchは変換時のみ一時的に使用し、実行時には不要。

```bash
uv run --with 'optimum[onnxruntime]' --with torch python -c "
from optimum.onnxruntime import ORTModelForFeatureExtraction
from huggingface_hub import snapshot_download
import shutil, os

output_dir = os.path.expanduser('~/.edo-tensei/models/ruri-v3-310m-onnx')
model = ORTModelForFeatureExtraction.from_pretrained('cl-nagoya/ruri-v3-310m', export=True)
model.save_pretrained(output_dir)

cache_dir = snapshot_download('cl-nagoya/ruri-v3-310m', allow_patterns=['tokenizer*', 'special_tokens*'])
for f in ['tokenizer.json', 'tokenizer.model', 'tokenizer_config.json', 'special_tokens_map.json']:
    src = os.path.join(cache_dir, f)
    if os.path.exists(src):
        shutil.copy2(src, os.path.join(output_dir, f))
print('Done.')
"
```

`~/.edo-tensei/models/ruri-v3-310m-onnx/` にモデルファイルが保存される（約1.2GB）。

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

Claudeが適切なタイミングで `search_memory` を呼ぶよう、`~/.claude/CLAUDE.md` に以下を追加する。

```markdown
## 記憶 (edo-tensei)

過去の会話がedo-tensei MCPサーバーに蓄積されている。
`search_memory` の検索コストはほぼゼロ。呼んで損することはない。

### 検索する条件
- ユーザーの発言に「前に」「以前」「あの時」「前回」など過去を参照する表現がある
- 設計判断・技術選定・方針決定の議論が始まった（過去に同じトピックで議論した可能性がある）
- バグや問題の原因調査で、過去に同種の問題を扱ったかもしれない
- ユーザーの要求に対して、既に却下された方針や試して失敗したアプローチが存在するかもしれない

### 検索しない条件
- typo修正、スタイル変更など設計判断を伴わない作業
- 初めて扱うことが明らかなトピック（新しい技術の導入相談など）

### 検索結果の扱い
- ヒットしたら、過去の文脈・判断理由を踏まえて回答する
- ヒットしなければそのまま進める
- 過去の結論をそのまま適用するのではなく、現在の状況と照合して判断する
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
| 埋め込みモデル | [Ruri v3-310m](https://huggingface.co/cl-nagoya/ruri-v3-310m)（日本語特化, 768次元, ONNX Runtime推論） |
| キーワード検索 | SQLite FTS5 trigram トークナイザ |
| ベクトル検索 | [sqlite-vec](https://github.com/asg017/sqlite-vec) |
| 統合手法 | RRF（Reciprocal Rank Fusion） |
| 時間減衰 | 半減期60日の指数減衰 |

## 参考

- [Claude Codeに長期記憶を実装した](https://zenn.dev/noprogllama/articles/7c24b2c2410213) — 設計思想の元になった記事
