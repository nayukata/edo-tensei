"""Ruri v3-310m embedding wrapper.

プレフィックススキームにより用途に応じた埋め込みを生成する:
  - "検索クエリ: " → 検索クエリ用
  - "検索文書: "   → 検索対象文書用
"""

from sentence_transformers import SentenceTransformer

MODEL_NAME = "cl-nagoya/ruri-v3-310m"

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """モデルをlazy loadする（初回は約1.2GBダウンロード）."""
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME, device="cpu")
    return _model


def embed_query(text: str) -> list[float]:
    """検索クエリ用の埋め込みを生成."""
    model = get_model()
    vec = model.encode(f"検索クエリ: {text}", normalize_embeddings=True)
    return vec.tolist()


def embed_documents(texts: list[str]) -> list[list[float]]:
    """複数文書を一括で埋め込み生成（バッチ処理）."""
    model = get_model()
    prefixed = [f"検索文書: {t}" for t in texts]
    vecs = model.encode(prefixed, normalize_embeddings=True, batch_size=32)
    return vecs.tolist()
