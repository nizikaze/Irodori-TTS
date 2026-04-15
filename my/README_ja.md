# Irodori-TTS 日本語解説

> [!NOTE]
> このドキュメントはルートディレクトリの [README.md](../README.md) を日本語訳し、フロントエンドやML/音声合成の知識が少ない方にも分かるよう補足説明を加えたものです。

---

## 概要

**Irodori-TTS** は、テキスト（文章）を音声に変換する TTS（Text-to-Speech）モデルです。

核となる技術は以下の通りです：

| 用語 | 意味 |
|------|------|
| **Flow Matching** | 拡散モデル（Diffusion Model）の一種で、ノイズからデータを少しずつ生成する手法。従来の拡散モデルよりシンプルで高速に学習・推論できる |
| **DACVAE** | Facebook Research が開発した音声用のオートエンコーダ（音声→圧縮表現→音声の変換器）。音声波形を「潜在表現（latent）」と呼ばれるコンパクトな数値列に変換する |
| **Echo-TTS** | Irodori-TTS のアーキテクチャ設計の元になった研究。Flow Matching を TTS に応用する手法を提案 |

設計の流れとしては、Echo-TTS の手法に基づき、DACVAE の連続的な潜在表現を生成ターゲットとして使っています。

---

## バージョンについて

> [!IMPORTANT]
> - `main` ブランチは **v2** のコードベースです。**Irodori-TTS-500M-v2** および **VoiceDesign** モデルと一緒に使います
> - 以前の v1 コードが必要な場合は `v1` タグを使ってください
> - v1 と v2 のチェックポイント（学習済みモデル）や前処理は互換性がありません
> - v1 モデルは [Aratako/Irodori-TTS-500M](https://huggingface.co/Aratako/Irodori-TTS-500M) からダウンロード可能です

モデルの重みや音声サンプルについては、[ベースモデルカード](https://huggingface.co/Aratako/Irodori-TTS-500M-v2) および [VoiceDesign モデルカード](https://huggingface.co/Aratako/Irodori-TTS-500M-v2-VoiceDesign) を参照してください。

---

## 主な機能（Features）

| 機能 | 説明 |
|------|------|
| **Flow Matching TTS** | Rectified Flow Diffusion Transformer（RF-DiT）を使い、DACVAE の連続的潜在表現上で音声を生成する |
| **Voice Cloning（声のクローン）** | リファレンス音声を入力するだけで、学習していない話者の声を真似て読み上げる（ゼロショット） |
| **Voice Design（声のデザイン）** | テキストの説明文（キャプション）で声の雰囲気やスタイルを指定できる |
| **マルチGPU学習** | `uv run torchrun` による分散学習。勾配累積、混合精度（bf16）、W&B ログに対応 |
| **PEFT LoRA ファインチューニング** | 少ないパラメータだけを追加学習する効率的な手法（LoRA）に対応。既存モデルを少量データで調整できる |
| **柔軟な推論** | CLI（コマンドライン）、Gradio Web UI、HuggingFace Hub からの直接ダウンロードに対応 |

### 用語補足

- **ゼロショット（Zero-shot）**: 事前に特定の話者のデータで学習していなくても、短い参照音声だけでその声を再現できること
- **bf16（bfloat16）**: 計算精度を少し下げる代わりにメモリ使用量を半減し、学習を高速化するテクニック
- **W&B（Weights & Biases）**: 機械学習の実験管理ツール。学習中の損失値やグラフをリアルタイムで確認できる
- **LoRA（Low-Rank Adaptation）**: モデル全体を書き換えずに、小さな追加パラメータだけを学習する手法。学習が速く、メモリも少なくて済む

---

## アーキテクチャ（モデル構造）

v2 では2種類のチェックポイント（モデル構成）をサポートしています：

### 1. ベースモデル (`Aratako/Irodori-TTS-500M-v2`)

**テキストエンコーダ + リファレンス潜在エンコーダ + 拡散トランスフォーマー** の3つで構成されます。

- リファレンス潜在エンコーダは、参照音声を DACVAE で変換した潜在表現を受け取り、話者の声やスタイルを条件として使います
- つまり「この人の声で読んで」という指示を音声で与える仕組みです

### 2. VoiceDesign モデル (`Aratako/Irodori-TTS-500M-v2-VoiceDesign`)

**テキストエンコーダ + キャプションエンコーダ + 拡散トランスフォーマー** の3つで構成されます。

- キャプションエンコーダが「落ち着いた女性の声で」のようなテキスト説明を処理します
- 参照音声のブランチは無効化されており、テキスト指示だけで声を制御します

### 共通の構成要素

| コンポーネント | 役割 |
|---------------|------|
| **テキストエンコーダ** | 事前学習済み LLM（大規模言語モデル）のトークン埋め込みを初期値として使用。Self-Attention + SwiGLU トランスフォーマー層＋ RoPE（回転位置エンコーディング）で構成 |
| **条件エンコーダ** | ベースモデルではリファレンス潜在エンコーダ、VoiceDesign ではキャプションエンコーダが担当 |
| **拡散トランスフォーマー（DiT）** | Joint-Attention DiT ブロック。Low-Rank AdaLN（タイムステップに応じた適応的正規化）、half-RoPE、SwiGLU MLP で構成 |

音声は、DACVAE コーデックによる連続的な潜在系列として表現されます。v2 では 32次元の [Semantic-DACVAE-Japanese-32dim](https://huggingface.co/Aratako/Semantic-DACVAE-Japanese-32dim) コーデックを使い、48kHz の波形を再構成します。

> [!TIP]
> **DiT（Diffusion Transformer）** は、画像生成で有名な Stable Diffusion 3 などでも使われているアーキテクチャで、トランスフォーマーの注意機構を拡散モデルに組み込んだものです。Irodori-TTS はこれを音声生成に応用しています。

---

## インストール

```bash
git clone https://github.com/Aratako/Irodori-TTS.git
cd Irodori-TTS
uv sync
```

> [!NOTE]
> - `uv` は Python のパッケージマネージャ兼プロジェクト管理ツールです（pip + venv の代替）
> - `uv sync` を実行すると、`pyproject.toml` に記載された依存関係がすべてインストールされます
> - Linux/Windows（CUDA 環境）では CUDA 対応の PyTorch が自動的にインストールされます
> - macOS（MPS）や CPU のみの環境では、デフォルトの PyTorch ビルドがインストールされます

---

## クイックスタート

### シンプルな推論（参照音声あり）

```bash
uv run python infer.py \
  --hf-checkpoint Aratako/Irodori-TTS-500M-v2 \
  --text "今日はいい天気ですね。" \
  --ref-wav path/to/reference.wav \
  --output-wav outputs/sample.wav
```

**何をしているか：**
- `--hf-checkpoint`: HuggingFace 上のモデルを指定（自動ダウンロードされる）
- `--text`: 読み上げたいテキスト
- `--ref-wav`: 声を真似したい参照音声ファイルのパス
- `--output-wav`: 生成された音声の保存先

### 参照音声なしでの推論

```bash
uv run python infer.py \
  --hf-checkpoint Aratako/Irodori-TTS-500M-v2 \
  --text "今日はいい天気ですね。" \
  --no-ref \
  --output-wav outputs/sample.wav
```

`--no-ref` を指定すると、参照音声なしでモデルが自動的に声を決めて読み上げます。

### VoiceDesign 推論（テキストで声を指定）

```bash
uv run python infer.py \
  --hf-checkpoint Aratako/Irodori-TTS-500M-v2-VoiceDesign \
  --text "今日はいい天気ですね。" \
  --caption "落ち着いた女性の声で、近い距離感でやわらかく自然に読み上げてください。" \
  --no-ref \
  --output-wav outputs/sample_voice_design.wav
```

**何をしているか：**
- `--caption` で、どんな声で読んでほしいかをテキストで指示します
- VoiceDesign モデル専用の機能です（ベースモデルでは使えません）

---

## Gradio Web UI

ブラウザで使えるグラフィカルな操作画面です。

### ベースモデル用

```bash
uv run python gradio_app.py --server-name 0.0.0.0 --server-port 7860
```

起動後、ブラウザで `http://localhost:7860` にアクセスしてください。

### VoiceDesign モデル用

```bash
uv run python gradio_app_voicedesign.py --server-name 0.0.0.0 --server-port 7861
```

> [!NOTE]
> - `--server-name 0.0.0.0` を指定すると、同じネットワーク上の他のデバイスからもアクセス可能になります
> - オンラインデモも公開されています：
>   - [ベースモデルデモ](https://huggingface.co/spaces/Aratako/Irodori-TTS-500M-v2-Demo)
>   - [VoiceDesign デモ](https://huggingface.co/spaces/Aratako/Irodori-TTS-500M-v2-VoiceDesign-Demo)
> - 他デバイスからのアクセス方法について詳しくは [ネットワークアクセスガイド](../docs/network_access_guide.md) を参照

---

## 推論（Inference）の詳細

### CLI から実行

HuggingFace Hub のモデルを使う場合：

```bash
uv run python infer.py \
  --hf-checkpoint Aratako/Irodori-TTS-500M-v2 \
  --text "今日はいい天気ですね。" \
  --ref-wav path/to/reference.wav \
  --output-wav outputs/sample.wav
```

ローカルに保存したチェックポイント（`.pt` や `.safetensors`）も使えます：

```bash
uv run python infer.py \
  --checkpoint outputs/checkpoint_final.safetensors \
  --text "今日はいい天気ですね。" \
  --ref-wav path/to/reference.wav \
  --output-wav outputs/sample.wav
```

VoiceDesign チェックポイントでキャプション条件付け：

```bash
uv run python infer.py \
  --hf-checkpoint Aratako/Irodori-TTS-500M-v2-VoiceDesign \
  --text "今日はいい天気ですね。" \
  --caption "落ち着いた、近い距離感の女性話者" \
  --no-ref \
  --output-wav outputs/sample_voice_design.wav
```

### 推論パラメータ一覧

以下は `infer.py` で使える全パラメータの一覧です。

#### 基本パラメータ

| パラメータ | デフォルト値 | 説明 |
|-----------|------------|------|
| `--checkpoint` / `--hf-checkpoint` | （必須、どちらか一方） | ローカルのチェックポイントファイル、または HuggingFace のリポジトリ ID |
| `--text` | （必須） | 読み上げるテキスト |
| `--caption` | None | VoiceDesign 用のスタイル指示テキスト（任意） |
| `--output-wav` | `output.wav` | 出力音声ファイルのパス |

#### リファレンス音声関連

| パラメータ | デフォルト値 | 説明 |
|-----------|------------|------|
| `--ref-wav` | None | リファレンス音声ファイルのパス（話者の声を指定するため） |
| `--ref-latent` | None | 事前計算済みのリファレンス潜在表現（`.pt`）|
| `--no-ref` | False | リファレンス音声による条件付けを無効にする |
| `--max-ref-seconds` | `30.0` | リファレンス音声の最大長（秒） |
| `--ref-normalize-db` | -16.0 | DACVAE エンコード前のリファレンス音量目標値（`none` で無効化） |
| `--ref-ensure-max` | True | `--ref-normalize-db` が無効な時、ピークが 1.0 を超えた場合のみ音量を下げる |

#### コーデック関連

| パラメータ | デフォルト値 | 説明 |
|-----------|------------|------|
| `--codec-repo` | `Aratako/Semantic-DACVAE-Japanese-32dim` | 潜在表現のエンコード・デコードに使うコーデックのリポジトリ |
| `--codec-deterministic-encode` | True | DACVAE エンコードを決定論的に行う（毎回同じ結果になる） |
| `--codec-deterministic-decode` | True | DACVAE デコード時のウォーターマークメッセージを決定論的に処理する |
| `--enable-watermark` | False | デコード時に DACVAE の電子透かし機能を有効にする |

#### サンプリング関連

| パラメータ | デフォルト値 | 説明 |
|-----------|------------|------|
| `--max-text-len` | チェックポイントのメタデータ or `256` | テキスト条件付けの最大トークン長 |
| `--max-caption-len` | チェックポイントのメタデータ or `max_text_len` | キャプション条件付けの最大トークン長 |
| `--num-steps` | 40 | オイラー積分のステップ数（多いほど高品質だが遅い） |
| `--num-candidates` | 1 | 1回の実行で生成する候補数 |
| `--decode-mode` | `sequential` | コーデックのデコードモード：`sequential`（逐次）または `batch`（一括） |

#### CFG（Classifier-Free Guidance）関連

> **CFG とは：** 条件付き生成の品質を向上させる手法。スケール値を上げると条件への忠実度が上がるが、上げすぎると不自然になる

| パラメータ | デフォルト値 | 説明 |
|-----------|------------|------|
| `--cfg-scale-text` | 3.0 | テキスト条件の CFG スケール |
| `--cfg-scale-caption` | 3.0 | キャプション条件の CFG スケール |
| `--cfg-scale-speaker` | 5.0 | 話者条件の CFG スケール |
| `--cfg-guidance-mode` | `independent` | CFG モード：`independent`（独立）、`joint`（結合）、`alternating`（交互） |
| `--cfg-scale` | None | 【非推奨】全条件に対する共通 CFG 値の上書き |
| `--cfg-min-t` | `0.5` | CFG を適用するタイムステップの下限 |
| `--cfg-max-t` | `1.0` | CFG を適用するタイムステップの上限 |

#### 高度なサンプリングパラメータ

| パラメータ | デフォルト値 | 説明 |
|-----------|------------|------|
| `--truncation-factor` | None | サンプリング前に初期ガウスノイズをスケーリングする係数 |
| `--rescale-k` / `--rescale-sigma` | None | 時間的スコアリスケーリングのパラメータ（セットで指定が必要） |
| `--context-kv-cache` | True | コンテキストの K/V 射影を事前計算してサンプリングを高速化 |
| `--speaker-kv-scale` | None | 話者の K/V スケーリングを追加してアイデンティティを強調 |
| `--speaker-kv-min-t` | `0.9` | このタイムステップ閾値以降は話者 K/V スケーリングを無効化 |
| `--speaker-kv-max-layers` | None | 話者 K/V スケーリングを最初の N 層のみに適用 |

#### デバイス・精度設定

| パラメータ | デフォルト値 | 説明 |
|-----------|------------|------|
| `--model-device` | auto | モデルのデバイス（`cuda`、`mps`、`cpu`） |
| `--codec-device` | auto | DACVAE コーデックのデバイス |
| `--model-precision` | `fp32` | モデルの計算精度（`fp32`：通常精度、`bf16`：半精度で高速化） |
| `--codec-precision` | `fp32` | コーデックの計算精度 |
| `--seed` | ランダム | 再現性のための乱数シード |
| `--compile-model` | False | `torch.compile` による推論高速化を有効にする |
| `--compile-dynamic` | False | `torch.compile` で `dynamic=True` を使用 |

#### 後処理

| パラメータ | デフォルト値 | 説明 |
|-----------|------------|------|
| `--trim-tail` | True | 末尾の無音区間をヒューリスティックに除去する |
| `--tail-window-size` | `20` | 末尾除去に使うウィンドウサイズ |
| `--tail-std-threshold` | `0.05` | 末尾除去の標準偏差しきい値 |
| `--tail-mean-threshold` | `0.1` | 末尾除去の平均値しきい値 |
| `--show-timings` | True | 各ステージの処理時間の内訳を表示する |

---

## 学習（Training）

学習は大きく3ステップです：

### ステップ 1: マニフェストの準備（DACVAE 潜在表現の事前計算）

HuggingFace データセットの音声データを DACVAE 潜在表現にエンコードし、学習用の JSONL マニフェスト（データカタログ）を作成します。

> [!NOTE]
> **なぜ事前計算するのか？** 学習中に毎回音声→潜在表現の変換を行うと非常に遅くなるため、事前にすべて変換して `.pt` ファイルとして保存しておきます。

#### 基本的な使い方

```bash
uv run python prepare_manifest.py \
  --dataset myorg/my_dataset \
  --split train \
  --audio-column audio \
  --text-column text \
  --output-manifest data/train_manifest.jsonl \
  --latent-dir data/latents \
  --device cuda
```

#### 話者IDを含める場合（話者条件付け学習用）

```bash
uv run python prepare_manifest.py \
  --dataset myorg/my_dataset \
  --split train \
  --audio-column audio \
  --text-column text \
  --speaker-column speaker \
  --output-manifest data/train_manifest.jsonl \
  --latent-dir data/latents \
  --device cuda
```

#### キャプションを含める場合（VoiceDesign 学習用）

```bash
uv run python prepare_manifest.py \
  --dataset myorg/my_dataset \
  --split train \
  --audio-column audio \
  --text-column text \
  --caption-column caption \
  --speaker-column speaker \
  --output-manifest data/train_manifest.jsonl \
  --latent-dir data/latents \
  --device cuda
```

VoiceDesign 学習時、`speaker_id` は任意です。VoiceDesign パスでは話者/リファレンス条件付けは無効化され、`text + caption` から学習します。

生成されるマニフェストの例：

```json
{"text": "こんにちは", "caption": "落ち着いた、近い距離感の女性話者", "latent_path": "data/latents/00001.pt", "speaker_id": "myorg/my_dataset:speaker_001", "num_frames": 750}
```

### ステップ 2: 学習の実行

#### シングル GPU 学習

```bash
uv run python train.py \
  --config configs/train_500m_v2.yaml \
  --manifest data/train_manifest.jsonl \
  --output-dir outputs/irodori_tts
```

#### VoiceDesign 学習

```bash
uv run python train.py \
  --config configs/train_500m_v2_voice_design.yaml \
  --manifest data/train_manifest.jsonl \
  --output-dir outputs/irodori_tts_voice_design
```

> [!NOTE]
> `train_500m_v2_voice_design.yaml` は `use_caption_condition: true` を設定し、話者/リファレンスブランチを無効化しています。キャプションなしの設定では、`speaker_id` やリファレンス入力が利用可能な場合に話者条件付けを使い続けます。
>
> VoiceDesign 設定では `caption_warmup: true` も有効になっています。`warmup_steps` は学習率スケジューラを制御し、`caption_warmup_steps` はキャプション以外の勾配を破棄する期間を制御します。この期間が終了すると通常の結合学習に戻ります。

#### マルチ GPU（DDP）学習

```bash
uv run torchrun --nproc_per_node 4 train.py \
  --config configs/train_500m_v2.yaml \
  --manifest data/train_manifest.jsonl \
  --output-dir outputs/irodori_tts \
  --device cuda
```

> **DDP（Distributed Data Parallel）**: 複数GPUにデータを分散して並列学習する仕組み。`--nproc_per_node 4` は4GPU使用を意味します。

学習は YAML 設定ファイルの `model` セクションと `train` セクションで設定します。CLI 引数は YAML の値を上書きします。全オプションは `uv run python train.py --help` で確認できます。

---

### ファインチューニング（既存モデルの追加学習）

#### リリース済みモデルからのファインチューニング

公開された推論用重み（`.safetensors`）を初期値として新しい学習を開始します。モデルの重みだけが初期化され、オプティマイザ/スケジューラの状態は新規になります。

```bash
uv run python train.py \
  --config configs/train_500m_v2.yaml \
  --manifest data/train_manifest.jsonl \
  --output-dir outputs/irodori_tts_ft \
  --init-checkpoint path/to/Irodori-TTS-500M-v2.safetensors
```

#### LoRA ファインチューニング

> [!IMPORTANT]
> **LoRA ファインチューニングとは：** ベースモデル本体の重みは凍結（固定）したまま、小さな追加パラメータ（LoRA アダプタ）だけを学習する手法です。
> 学習の結果として出力されるのは **LoRA アダプタの重みファイル**（アダプタ専用ディレクトリ）であり、ベースモデル全体のコピーではありません。
>
> **フルファインチューニングとの比較：**
>
> | 項目 | フルファインチューニング | LoRA ファインチューニング |
> |------|----------------------|------------------------|
> | 学習するパラメータ数 | 全パラメータ（5億個など） | ごく一部（数百万個程度） |
> | 必要メモリ | 大 | 小 |
> | 保存ファイルサイズ | 大（GB単位） | 小（MB〜数百MB程度） |
> | 学習速度 | 遅い | 速い |
> | 出力ファイル | `.pt`（モデル全体） | ディレクトリ（アダプタ重み＋状態） |
>
> **推論時の使い方は2通り：**
> 1. **LoRA アダプタのまま使う** → ベースモデル + LoRA アダプタを組み合わせてロード
> 2. **マージして使う** → `convert_checkpoint_to_safetensors.py` で LoRA をベースモデルに統合し、1つの `.safetensors` ファイルにまとめる（この場合、通常のモデルと同じように使える）
>
> 少量のデータで特定の声に特化させたい場合などに特に有効です。

```bash
uv run python train.py \
  --config configs/train_500m_v2_lora.yaml \
  --manifest data/train_manifest.jsonl \
  --output-dir outputs/irodori_tts_lora \
  --init-checkpoint path/to/Irodori-TTS-500M-v2.safetensors
```

#### VoiceDesign の LoRA ファインチューニング

```bash
uv run python train.py \
  --config configs/train_500m_v2_voice_design_lora.yaml \
  --manifest data/train_manifest.jsonl \
  --output-dir outputs/irodori_tts_voice_design_lora \
  --init-checkpoint path/to/Irodori-TTS-500M-v2.safetensors
```

#### LoRA ターゲットプリセット一覧

LoRA をどのモジュールに適用するかをプリセットで指定できます：

| プリセット名 | 対象範囲 |
|-------------|---------|
| `text_attn_mlp` | テキストエンコーダの注意機構 + 注意ゲート + MLP |
| `caption_attn_mlp` | キャプションエンコーダの注意機構 + 注意ゲート + MLP |
| `speaker_attn_mlp` | 話者エンコーダの注意機構 + 注意ゲート + MLP + `speaker_encoder.in_proj` |
| `diffusion_attn` | 拡散部分の注意機構のみ（テキスト/話者/キャプションのコンテキスト KV と注意ゲート含む） |
| `diffusion_attn_mlp` | `diffusion_attn` に加えて拡散部分の MLP |
| `all_attn` | テキスト/キャプション/話者/拡散の全注意ブロック（注意ゲート含む） |
| `diffusion_full` | 拡散スタック全体：`cond_module`、`in_proj/out_proj`、注意機構、MLP、AdaLN |
| `adaln` | 拡散ブロックの AdaLN 層のみ |
| `conditioning` | 条件付け側の射影のみ：`cond_module`、`speaker_encoder.in_proj`、拡散コンテキスト KV 射影 |
| `all_attn_mlp` | `all_attn` + テキスト/キャプション/話者/拡散の MLP + `speaker_encoder.in_proj` |
| `all_linear` | モデル内の全 `nn.Linear` 層。埋め込みと正規化の重みは含まない |

`--lora-target-modules` は正規表現文字列やカンマ区切りのモジュールサフィックスリストも受け付けます。学習再開時は、明示的にオーバーライドしない限り、保存された LoRA 設定が自動復元されます。

`--lora` が有効な場合、チェックポイントは PEFT アダプタ重み＋トレーナー状態を含むアダプタ専用ディレクトリとして保存されます。

---

### 中断した学習の再開

学習チェックポイントから既存の学習を再開します。フルモデルは `.pt`、LoRA はチェックポイントディレクトリを使います。どちらもオプティマイザ、スケジューラ、ステップの状態を復元します。

#### フルモデルの再開

```bash
uv run python train.py \
  --config configs/train_500m_v2.yaml \
  --manifest data/train_manifest.jsonl \
  --output-dir outputs/irodori_tts \
  --resume outputs/irodori_tts/checkpoint_0010000.pt
```

#### LoRA の再開

```bash
uv run python train.py \
  --config configs/train_500m_v2_lora.yaml \
  --manifest data/train_manifest.jsonl \
  --output-dir outputs/irodori_tts_lora \
  --resume outputs/irodori_tts_lora/checkpoint_0010000
```

> [!TIP]
> LoRA チェックポイントを別の環境に移動して、元のベースチェックポイントのパスが無効になった場合は、`--resume` と一緒に `--init-checkpoint path/to/base_model.safetensors` を指定して、保存されたベースモデルパスを上書きしてください。

---

### ステップ 3: チェックポイントの変換

学習チェックポイントを推論専用の safetensors 形式に変換します。

```bash
uv run python convert_checkpoint_to_safetensors.py outputs/checkpoint_final.pt
```

LoRA アダプタチェックポイントも直接変換できます：

```bash
uv run python convert_checkpoint_to_safetensors.py outputs/irodori_tts_lora/checkpoint_final
```

> [!NOTE]
> LoRA アダプタチェックポイントは変換時にベースモデルと自動的にマージされるため、エクスポートされた `.safetensors` ファイルはそのまま推論に使えます。

---

## プロジェクト構成

```text
Irodori-TTS/
├── train.py                    # 学習のエントリーポイント（DDP対応）
├── infer.py                    # CLI推論
├── gradio_app.py               # Gradio Web UI（ベースモデル用）
├── gradio_app_voicedesign.py   # Gradio Web UI（VoiceDesign用）
├── prepare_manifest.py         # データセット → DACVAE 潜在表現の前処理
├── convert_checkpoint_to_safetensors.py  # チェックポイント変換ツール
│
├── irodori_tts/                # コアライブラリ
│   ├── model.py                # TextToLatentRFDiT アーキテクチャ
│   ├── rf.py                   # Rectified Flow ユーティリティ & オイラー CFG サンプリング
│   ├── codec.py                # DACVAE コーデックのラッパー
│   ├── dataset.py              # データセットとコレータ
│   ├── tokenizer.py            # 事前学習済み LLM トークナイザのラッパー
│   ├── config.py               # モデル / 学習 / サンプリング設定のデータクラス
│   ├── inference_runtime.py    # キャッシュ済みスレッドセーフな推論ランタイム
│   ├── lora.py                 # PEFT LoRA 統合ヘルパー
│   ├── text_normalization.py   # 日本語テキスト正規化
│   ├── optim.py                # Muon + AdamW オプティマイザ
│   └── progress.py             # 学習進捗トラッカー
│
└── configs/
    ├── train_500m_v2.yaml                    # 500M v2 モデル設定
    ├── train_500m_v2_lora.yaml               # 500M v2 LoRA ファインチューニング設定
    ├── train_500m_v2_voice_design.yaml       # 500M v2 VoiceDesign フルファインチューニング設定
    ├── train_500m_v2_voice_design_lora.yaml  # 500M v2 VoiceDesign LoRA ファインチューニング設定
    ├── train_500m.yaml                       # 500M v1 モデル設定
    └── train_2.5b.yaml                       # 2.5B パラメータモデル設定
```

---

## ライセンス

- **コード**: [MIT License](../LICENSE) — 商用利用含め自由に利用可能
- **モデルの重み**: ライセンスの詳細は [ベースモデルカード](https://huggingface.co/Aratako/Irodori-TTS-500M-v2) および [VoiceDesign モデルカード](https://huggingface.co/Aratako/Irodori-TTS-500M-v2-VoiceDesign) を参照してください

---

## 謝辞（Acknowledgments）

このプロジェクトは以下の研究に基づいています：

- [Echo-TTS](https://jordandarefsky.com/blog/2025/echo/) — アーキテクチャと学習設計のリファレンス
- [DACVAE](https://github.com/facebookresearch/dacvae) — 音声用 VAE（オートエンコーダ）

---

## 引用（Citation）

学術論文等でこのプロジェクトを引用する場合：

```bibtex
@misc{irodori-tts,
  author = {Chihiro Arata},
  title = {Irodori-TTS: A Flow Matching-based Text-to-Speech Model with Emoji-driven Style Control},
  year = {2026},
  publisher = {GitHub},
  journal = {GitHub repository},
  howpublished = {\url{https://github.com/Aratako/Irodori-TTS}}
}
```
