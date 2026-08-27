# Irodori-TTS v3 → v4 変更点まとめ

このドキュメントは、フォーク元 ([Aratako/Irodori-TTS](https://github.com/Aratako/Irodori-TTS)) における v3 から v4（v4-Small / v4.1-Small）への主要な変更点と、独自UI（`my/` 配下）における対応内容をまとめたものです。

---

## 概要

v4（およびデフォルトモデルの v4.1-Small）では、**事前学習済みテキストエンコーダー（Sarashina 2.2-0.5B）** の採用による表現力向上、**TorchAO によるモデル量子化（INT8 / INT4 / FP8）** のネイティブサポート、**複数クリップ入力による話者クローニング**、およびモデルダウンロード機構の刷新が行われました。
また、従来の「VoiceDesign（スタイル指示）」モデルと「Reference Audio（話者クローニング）」モデルが統一され、1つのモデルアーキテクチャで両方の条件付けを柔軟に扱えるようになっています。

---

## 1. Irodori-TTS v4.1-Small のリリースと統合アーキテクチャ ⭐ 最大の変更

### v3 との比較
- **v3**: スクラッチから学習したテキストエンコーダーを採用し、通常モデル（参照音声/話者埋め込み）と VoiceDesign モデル（キャプション/スタイル指示）に分かれていた。
- **v4 / v4.1-Small**: 事前学習済みの日本語言語モデル（`sbintuitions/sarashina2.2-0.5b`）をテキストエンコーダーとして活用（`text_encoder_type: pretrained`）。
  - テキスト理解力・発音・イントネーションの自然さが向上。
  - 話者埋め込み（Speaker Inversion / Reference Clips）とスタイルキャプション（VoiceDesign）が同一のチェックポイントで統合サポート。

### デフォルトチェックポイント
- `Aratako/Irodori-TTS-v4.1-Small`

---

## 2. 複数リファレンス音声クリップ（Multiple Reference Clips） ⭐ 新機能

### v3 の挙動
- 単一の音声ファイル（`ref_wav`）を入力し、最大参照長は固定で `30.0` 秒で切り詰められていた。

### v4 の挙動
- **複数クリップ入力（`ref_wavs` / `ref_latents`）**: 同一話者の短くクリーンな複数の音声クリップをアップロードして連結可能。
  - v4-Small の学習方式に合致し、1つの長い未編集録音よりも、短いクリーンクリップを複数指定する方が高精度な話者再現が可能。
- **最大参照長の動的設定（`max_ref_seconds`）**:
  - デフォルト値が `None` に変更され、チェックポイント内の推奨値（v4-Small では最大120秒）が自動適用される。
  - レガシーモデル（v2/v3）の場合は自動で従来の30秒フォールバックが適用される。

---

## 3. モデル量子化（Quantization / TorchAO）のサポート ⭐ 新機能

### 量子化フォーマット
PyTorchの最新量子化ライブラリ `torchao` を利用し、以下の量子化モデルのロード・推論・学習後量子化がサポートされました：
- `int8-weight-only`（INT8 重み量子化: メモリ削減と高速化のバランス）
- `int4-weight-only`（INT4 重み量子化: 大幅なVRAM削減）
- `float8-weight-only`（FP8 重み量子化）
- `int8-dynamic-activation-int8-weight`（動的アクティベーション＋重み INT8）

### 推論での使い方
Hugging Face のサブフォルダ指定（例: `owner/repo/subfolder`）により直接量子化モデルを指定してダウンロード・推論できます：
```bash
uv run python infer.py \
  --hf-checkpoint Aratako/Irodori-TTS-v4.1-Small/int8-weight-only \
  --text "量子化モデルでの高速音声生成のテストです。" \
  --output-wav output.wav
```

### チェックポイントの量子化
```bash
uv run python quantize_checkpoint.py \
  --checkpoint path/to/model.safetensors \
  --output path/to/model_int8.safetensors \
  --mode int8-weight-only
```

---

## 4. モデルダウンロードとアセット管理の強化

- `download_hf_checkpoint` の導入により、Hugging Face リポジトリからのダウンロード時に `model.safetensors` だけでなく同梱されている `tokenizer/` 関連アセットも自動でスナップショット取得・解決されるようになりました。
- `owner/repo/subfolder` 形式に対応し、量子化版などの派生モデルの取得が容易になりました。

---

## 5. 主要コード・APIの変更点

| 項目 | v3 | v4 |
|---|---|---|
| **SamplingRequest 参照指定** | `ref_wav: str \| None` | `ref_wav: str \| None`, `ref_wavs: list[str] \| None`, `ref_latents: list[str] \| None` |
| **SamplingRequest 最大参照長** | `max_ref_seconds: float = 30.0` | `max_ref_seconds: float \| None = None`（自動推奨値） |
| **Gradio 参照音声解決関数** | `_resolve_ref_wav` | `_resolve_ref_wavs`, `_coerce_gradio_file_path` |
| **Gradio 参照音声UI** | `gr.Audio` / 単一ファイル | `gr.File(file_count="multiple", allow_reordering=True)` |
| **設定ロード関数** | `load_experiment_yaml` | `load_config_yaml` |
| **不要クラスの削除** | `SamplingConfig` | 廃止（削除） |

---

## 6. 独自UI（`my/`）での対応内容

1. **インポートエラーの解消**:
   - `gradio_app_voicedesign` / `gradio_app` から削除された `_resolve_ref_wav` を `_resolve_ref_wavs` / `_coerce_gradio_file_path` に更新。
2. **デフォルトチェックポイントの移行**:
   - `my/gradio_gen.py` および `my/gradio_ref.py` のデフォルトモデルを `Aratako/Irodori-TTS-v4.1-Small` に更新。
   - 既存設定からの自動アップグレードマップ（`_UPGRADE_MAP`）に v4.1-Small を追加。
3. **複数リファレンス音声（Multiple Clips）UI**:
   - `my/gradio_ref.py` の音声アップロードコンポーネントを複数ファイル（並び替え可能）に刷新。
   - `SamplingRequest(ref_wavs=..., max_ref_seconds=None)` による推論実行に対応。
4. **DB / バージョン推定の拡張**:
   - `my/db.py` の `guess_model_version()` に `v4`, `v4-small`, `v4.1-small` の判定を追加。
   - 複数リファレンス音声指定時も `ref_wav` カラムへ安全にファイル名一覧を格納するように対応。
5. **Streamlit 履歴閲覧**:
   - `my/streamlit_history.py` における `v4` 系モデルバッジの表示とメタデータ表示に対応。
6. **モデル選択肢（Checkpoint）の更新**:
   - `_checkpoint_choices` の公式リポジトリ一覧に `Aratako/Irodori-TTS-v4.1-Small`、`Aratako/Irodori-TTS-v4-Small`、および各種 TorchAO 量子化モデル（`int8-weight-only`, `int4-weight-only`, `float8-weight-only`, `int8-dynamic-activation-int8-weight`）を追加し、UIのドロップダウンから直接選択可能に対応。
