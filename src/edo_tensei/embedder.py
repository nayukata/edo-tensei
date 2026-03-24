"""Ruri v3-310m embedding via ONNX Runtime.

PyTorchを使わず、ONNX Runtimeとtokenizersだけで推論する。
メモリ消費を大幅に削減（PyTorch 19GB → ONNX 1-2GB程度）。

プレフィックススキーム:
  - "検索クエリ: " → 検索クエリ用
  - "検索文書: "   → 検索対象文書用
"""

from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

MODEL_DIR = Path.home() / ".edo-tensei" / "models" / "ruri-v3-310m-onnx"

_session: ort.InferenceSession | None = None
_tokenizer: Tokenizer | None = None


def _get_session() -> ort.InferenceSession:
    global _session
    if _session is None:
        model_path = MODEL_DIR / "model.onnx"
        if not model_path.exists():
            raise FileNotFoundError(
                f"ONNXモデルが見つかりません: {model_path}\n"
                "初回セットアップが必要です。READMEを参照してください。"
            )
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 2
        opts.intra_op_num_threads = 2
        _session = ort.InferenceSession(str(model_path), sess_options=opts)
    return _session


def _get_tokenizer() -> Tokenizer:
    global _tokenizer
    if _tokenizer is None:
        tokenizer_path = MODEL_DIR / "tokenizer.json"
        if not tokenizer_path.exists():
            raise FileNotFoundError(
                f"トークナイザーが見つかりません: {tokenizer_path}\n"
                "初回セットアップが必要です。READMEを参照してください。"
            )
        _tokenizer = Tokenizer.from_file(str(tokenizer_path))
    return _tokenizer


def _mean_pooling(last_hidden_state: np.ndarray, attention_mask: np.ndarray) -> np.ndarray:
    """Mean pooling with attention mask."""
    mask_expanded = np.expand_dims(attention_mask, axis=-1).astype(np.float32)
    sum_embeddings = np.sum(last_hidden_state * mask_expanded, axis=1)
    sum_mask = np.clip(np.sum(mask_expanded, axis=1), a_min=1e-9, a_max=None)
    return sum_embeddings / sum_mask


def _normalize(vectors: np.ndarray) -> np.ndarray:
    """L2正規化."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.clip(norms, a_min=1e-9, a_max=None)


def _encode(texts: list[str]) -> np.ndarray:
    """テキストリストを埋め込みベクトルに変換."""
    session = _get_session()
    tokenizer = _get_tokenizer()

    tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
    tokenizer.enable_truncation(max_length=8192)

    encodings = tokenizer.encode_batch(texts)

    input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
    attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)

    outputs = session.run(
        None,
        {"input_ids": input_ids, "attention_mask": attention_mask},
    )

    last_hidden_state = outputs[0]
    pooled = _mean_pooling(last_hidden_state, attention_mask)
    return _normalize(pooled)


def unload_model() -> None:
    """モデルとセッションをメモリから解放する."""
    import gc

    global _session, _tokenizer
    _session = None
    _tokenizer = None
    gc.collect()


def embed_query(text: str) -> list[float]:
    """検索クエリ用の埋め込みを生成."""
    vectors = _encode([f"検索クエリ: {text}"])
    return vectors[0].tolist()


def embed_documents(texts: list[str]) -> list[list[float]]:
    """複数文書を1件ずつ埋め込み生成.

    バッチ処理はONNX Runtimeのメモリが累積的に膨張するため、
    1件ずつ処理してメモリを抑える。
    """
    import gc

    results: list[list[float]] = []
    for text in texts:
        vectors = _encode([f"検索文書: {text}"])
        results.append(vectors[0].tolist())
        # ONNX Runtimeの中間バッファを解放
        gc.collect()
    return results
