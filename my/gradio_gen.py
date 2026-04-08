"""
Irodori-TTS 独自生成UI（Gradio）。

本家 gradio_app_voicedesign.py をベースに、以下の変更を加えた生成画面:
- 候補グリッド（32枠）・num_candidates スライダーを廃止（常に1件生成）
- ファイル名規則を {YYYYMMDD_HHMMSS}_{seed}.wav に変更
- 直近5件の履歴表示（Audio×5）
- autoplay ON/OFF トグル
- generate_forever モード（チェックONで連続生成）
- 生成完了時に DB へ書き込み
- キュー再生（再生中に新しい音声が来ても中断せずキューに積む）

Usage:
    python -m my.gradio_gen [--server-name 127.0.0.1] [--server-port 7862]
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Generator

import gradio as gr

# --------------------------------------------------------------------------- #
#  本家 gradio_app_voicedesign.py からユーティリティ関数をインポート
#
#  Why: 同じロジックの重複実装を避けるため、パラメータ解析・ランタイム管理
#       などの純粋なユーティリティは本家から再利用する。
#       build_ui() と _run_generation() は本ファイルで独自に再実装する。
# --------------------------------------------------------------------------- #
from gradio_app_voicedesign import (
    FIXED_SECONDS,
    _build_runtime_key,
    _clear_runtime_cache,
    _default_checkpoint,
    _default_codec_device,
    _default_model_device,
    _describe_runtime,
    _format_timings,
    _on_codec_device_change,
    _on_model_device_change,
    _parse_optional_float,
    _parse_optional_int,
    _precision_choices_for_device,
    _resolve_checkpoint_path,
)
from irodori_tts.inference_runtime import (
    SamplingRequest,
    get_cached_runtime,
    list_available_runtime_devices,
    save_wav,
)

# 自前の DB モジュール
from my.db import init_db, insert_generation

# 直近履歴の最大表示件数
_MAX_HISTORY = 5

# キューの最大サイズ（これ以上溜まると古いものから破棄）
_MAX_QUEUE_SIZE = 10

# グローバルな停止フラグ管理用（session_hash -> 停止要求）
_session_stop_flags: dict[str, bool] = {}

# 生成した wav を保存するディレクトリ
_OUTPUT_DIR = Path(__file__).resolve().parent / "data" / "outputs"

# --------------------------------------------------------------------------- #
#  キュー再生用カスタム JavaScript
#
#  Why: gr.Audio は HTML5 の <audio> 要素の ended イベントを Python 側に
#       通知する仕組みを持っていない。そのため、再生中に新しい音声が来たとき
#       「現在の再生を中断せずキューに積み、再生完了後に次を再生する」という
#       キュー再生を実現するには、ブラウザ側の JavaScript で制御する必要がある。
#
#  仕組み:
#       1. gr.Blocks(head=...) で <script> タグを注入する
#       2. MutationObserver で #audio-0 内の <audio> 要素の src 変更を監視
#       3. 再生中に新しい src が来たら autoplay 属性を除去しキューに積む
#       4. ended イベントで次のキューアイテムを再生
#       5. キューの状態をインジケーター (#queue-indicator) に表示
#
#  注意:
#       - Gradio の DOM 構造に依存するため、バージョンアップで壊れる可能性がある
#       - autoplay OFF 時は Python 側が autoplay 属性を設定しないため、
#         JS のキューには積まれない（従来と同じ動作）
# --------------------------------------------------------------------------- #
_QUEUE_PLAYBACK_JS = f"""
<script>
(function() {{
    'use strict';

    // --- キュー管理の状態 ---
    // audioQueue: 再生待ちの音声 URL を格納する配列（FIFO）
    const audioQueue = [];
    // isPlaying: 現在 <audio> 要素で再生中かどうか
    let isPlaying = false;
    // currentSrc: 現在再生中（または最後に設定された）音声の URL
    let currentSrc = null;
    // MAX_QUEUE_SIZE: キューの最大サイズ（Python 側の定数と同じ値）
    const MAX_QUEUE_SIZE = {_MAX_QUEUE_SIZE};

    /**
     * キューインジケーターの表示を更新する。
     * #queue-indicator という要素が存在すれば、キュー内のアイテム数を表示する。
     */
    function updateIndicator() {{
        const el = document.getElementById('queue-indicator');
        if (!el) return;
        // textarea 要素を探す（Gradio の Textbox は内部的に textarea を使う）
        const textarea = el.querySelector('textarea');
        if (textarea) {{
            const count = audioQueue.length;
            // Gradio の input イベントをシミュレートして値を反映
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLTextAreaElement.prototype, 'value'
            ).set;
            nativeInputValueSetter.call(
                textarea,
                count > 0 ? 'キュー: ' + count + '件待ち' : ''
            );
            textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}
    }}

    /**
     * 指定された <audio> 要素で音声を再生する。
     * @param {{HTMLAudioElement}} audioEl - 再生対象の audio 要素
     * @param {{string}} src - 再生する音声の URL
     */
    function playAudio(audioEl, src) {{
        isPlaying = true;
        currentSrc = src;
        audioEl.src = src;
        audioEl.play().catch(function(e) {{
            // ブラウザのAutoplay Policyによりブロックされた場合のフォールバック
            console.warn('[queue-playback] play() blocked:', e.message);
            isPlaying = false;
            updateIndicator();
        }});
        console.log('[queue-playback] playing:', src);
    }}

    /**
     * #audio-0 コンポーネント内の <audio> 要素を監視し、
     * src 変更時のキュー制御と ended イベントの処理をセットアップする。
     *
     * Why MutationObserver を使うか:
     *   Gradio は yield のたびに DOM を再構築することがある。
     *   <audio> 要素自体が置き換わる可能性があるため、常に監視して
     *   新しい <audio> 要素にもイベントリスナーを付け直す必要がある。
     */
    function setupQueuePlayback() {{
        const container = document.getElementById('audio-0');
        if (!container) {{
            console.warn('[queue-playback] #audio-0 not found, retrying...');
            setTimeout(setupQueuePlayback, 500);
            return;
        }}

        // 現在リスナーを付けている <audio> 要素を追跡
        let trackedAudio = null;

        /**
         * <audio> 要素にイベントリスナーを設定する。
         * @param {{HTMLAudioElement}} audioEl - 対象の audio 要素
         */
        function attachListeners(audioEl) {{
            if (trackedAudio === audioEl) return; // 既にアタッチ済み
            trackedAudio = audioEl;

            // ended: 再生が最後まで到達したときに発火するブラウザ標準イベント
            audioEl.addEventListener('ended', function() {{
                console.log('[queue-playback] ended event fired');
                if (audioQueue.length > 0) {{
                    // キューに次がある場合: 先頭を取り出して再生
                    const nextSrc = audioQueue.shift();
                    console.log('[queue-playback] playing next from queue, remaining:', audioQueue.length);
                    updateIndicator();
                    playAudio(audioEl, nextSrc);
                }} else {{
                    // キューが空の場合: 再生終了
                    isPlaying = false;
                    console.log('[queue-playback] queue empty, idle');
                    updateIndicator();
                }}
            }});

            // pause: ユーザーが手動で一時停止した場合
            audioEl.addEventListener('pause', function() {{
                // ended ではなくユーザー操作による pause の場合
                // （ended の直前にも pause は発火するが、ended 側で処理済み）
                if (!audioEl.ended) {{
                    console.log('[queue-playback] paused by user');
                }}
            }});

            // play: 再生開始時（ユーザー操作またはautoplay）
            audioEl.addEventListener('play', function() {{
                isPlaying = true;
                currentSrc = audioEl.src;
                console.log('[queue-playback] play started');
            }});
        }}

        /**
         * コンテナ内の <audio> 要素を探してリスナーを設定する。
         * audio の src が変わった場合のキュー制御も行う。
         */
        function checkAndSetup() {{
            // Gradio 6.x では <audio> は shadow DOM ではなく通常の子要素
            const audioEl = container.querySelector('audio');
            if (!audioEl) return;

            attachListeners(audioEl);

            // src が変わった && 再生中の場合: キューに積む
            const newSrc = audioEl.src;
            if (newSrc && newSrc !== currentSrc && newSrc !== '' && !newSrc.endsWith('/')) {{
                if (isPlaying) {{
                    // 再生中 → autoplay を除去してキューに追加
                    audioEl.removeAttribute('autoplay');
                    audioEl.pause();

                    // キューが上限を超えた場合は古いものを破棄
                    if (audioQueue.length >= MAX_QUEUE_SIZE) {{
                        const dropped = audioQueue.shift();
                        console.log('[queue-playback] queue full, dropped oldest:', dropped);
                    }}
                    audioQueue.push(newSrc);
                    console.log('[queue-playback] queued:', newSrc, 'queue size:', audioQueue.length);
                    updateIndicator();

                    // 元の再生中の音声に戻す
                    // Why: Gradio が src を新しいものに上書きしてしまうため、
                    //      再生中の音声を復元して中断を防ぐ
                    audioEl.src = currentSrc;
                    audioEl.play().catch(function() {{}});
                }} else {{
                    // 再生中でない → そのまま再生させる（autoplay に任せる）
                    currentSrc = newSrc;
                    isPlaying = true;
                    console.log('[queue-playback] new audio, auto-playing:', newSrc);
                    updateIndicator();
                }}
            }}
        }}

        // MutationObserver: DOM の変更を監視する仕組み
        // #audio-0 の子要素や属性が変わるたびに checkAndSetup を呼ぶ
        const observer = new MutationObserver(function(mutations) {{
            // 少し遅延させて Gradio の DOM 更新が完了するのを待つ
            setTimeout(checkAndSetup, 50);
        }});

        observer.observe(container, {{
            childList: true,   // 子要素の追加・削除を監視
            subtree: true,     // 孫要素以下も含めて監視
            attributes: true,  // 属性の変更を監視
            attributeFilter: ['src']  // src 属性の変更のみを対象
        }});

        // 初回チェック
        checkAndSetup();
        console.log('[queue-playback] initialized, observing #audio-0');
    }}

    // ページ読み込み完了後にセットアップを開始
    // Why: Gradio の DOM 構築が完了してから audio 要素を探す必要がある
    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', function() {{
            setTimeout(setupQueuePlayback, 1000);
        }});
    }} else {{
        setTimeout(setupQueuePlayback, 1000);
    }}
}})()
</script>
"""


def _run_generation(
    checkpoint: str,
    model_device: str,
    model_precision: str,
    codec_device: str,
    codec_precision: str,
    enable_watermark: bool,
    text: str,
    caption: str,
    num_steps: int,
    seed_raw: str,
    cfg_guidance_mode: str,
    cfg_scale_text: float,
    cfg_scale_caption: float,
    cfg_scale_raw: str,
    cfg_min_t: float,
    cfg_max_t: float,
    context_kv_cache: bool,
    max_text_len_raw: str,
    max_caption_len_raw: str,
    truncation_factor_raw: str,
    rescale_k_raw: str,
    rescale_sigma_raw: str,
    autoplay: bool,
    forever: bool,
    history_paths: list[str],
    request: gr.Request = None,
) -> Generator[tuple, None, None]:
    """
    音声を1件生成し、履歴・DB を更新する。

    forever=True の場合はジェネレータとして繰り返し生成を行い、
    Gradio 側で yield ごとにUIが更新される。
    forever=False の場合でもジェネレータとして1回だけ yield する
    （Gradio の .click() で統一的に扱うため）。

    Args:
        checkpoint〜rescale_sigma_raw: サンプリング関連パラメータ（本家と同等）
        autoplay:      最新音声を自動再生するかどうか
        forever:       連続生成モードかどうか
        history_paths: 直近5件の wav パスリスト（gr.State から受け取る）
        request:       Gradio のリクエスト情報（セッション管理用）

    Yields:
        tuple: (Audio×5 の更新, ログ文字列, タイミング文字列, 更新後の history_paths)
    """

    def stdout_log(msg: str) -> None:
        """標準出力にログを書き出すヘルパー"""
        print(msg, flush=True)

    # --- パラメータのバリデーションとパース ---
    runtime_key = _build_runtime_key(
        checkpoint=checkpoint,
        model_device=model_device,
        model_precision=model_precision,
        codec_device=codec_device,
        codec_precision=codec_precision,
        enable_watermark=enable_watermark,
    )

    text_value = str(text).strip()
    caption_value = str(caption).strip()

    if text_value == "":
        raise ValueError("text（テキスト）は必須です。")

    cfg_scale = _parse_optional_float(cfg_scale_raw, "cfg_scale")
    max_text_len = _parse_optional_int(max_text_len_raw, "max_text_len")
    max_caption_len = _parse_optional_int(max_caption_len_raw, "max_caption_len")
    truncation_factor = _parse_optional_float(truncation_factor_raw, "truncation_factor")
    rescale_k = _parse_optional_float(rescale_k_raw, "rescale_k")
    rescale_sigma = _parse_optional_float(rescale_sigma_raw, "rescale_sigma")
    seed = _parse_optional_int(seed_raw, "seed")

    # 出力ディレクトリを確保
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # DB を初期化（テーブルが無ければ作る）
    init_db()

    # セッションIDを取得・フラグをリセット
    session_id = request.session_hash if request else "default"
    _session_stop_flags[session_id] = False

    # --- 生成ループ（forever=False なら1回で終了） ---
    # Why: while True + break で「最低1回は実行」を保証しつつ、
    #      forever フラグで連続生成に対応する
    iteration = 0
    while True:
        # 停止要求があれば生成開始前にBreak
        if _session_stop_flags.get(session_id, False):
            stdout_log(f"[my-gen] Generation stopped by user (session: {session_id})")
            break

        iteration += 1

        runtime, reloaded = get_cached_runtime(runtime_key)
        if not runtime.model_cfg.use_caption_condition:
            raise ValueError(
                "読み込んだチェックポイントは caption conditioning をサポートしていません。"
                "gradio_app.py を使用してください。"
            )

        stdout_log(f"[my-gen] runtime: {'reloaded' if reloaded else 'reused'} (iteration {iteration})")

        result = runtime.synthesize(
            SamplingRequest(
                text=text_value,
                caption=caption_value or None,
                ref_wav=None,
                ref_latent=None,
                no_ref=True,
                ref_normalize_db=-16.0,
                ref_ensure_max=True,
                num_candidates=1,  # 常に1件だけ生成（候補グリッド廃止）
                decode_mode="sequential",
                seconds=FIXED_SECONDS,
                max_ref_seconds=30.0,
                max_text_len=max_text_len,
                max_caption_len=max_caption_len,
                num_steps=int(num_steps),
                seed=None if seed is None else int(seed),
                cfg_guidance_mode=str(cfg_guidance_mode),
                cfg_scale_text=float(cfg_scale_text),
                cfg_scale_caption=float(cfg_scale_caption),
                cfg_scale_speaker=0.0,
                cfg_scale=cfg_scale,
                cfg_min_t=float(cfg_min_t),
                cfg_max_t=float(cfg_max_t),
                truncation_factor=truncation_factor,
                rescale_k=rescale_k,
                rescale_sigma=rescale_sigma,
                context_kv_cache=bool(context_kv_cache),
                speaker_kv_scale=None,
                speaker_kv_min_t=None,
                speaker_kv_max_layers=None,
                trim_tail=True,
            ),
            log_fn=stdout_log,
        )

        # --- ファイル保存 ---
        # ファイル名規則: {YYYYMMDD_HHMMSS}_{seed}.wav
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        used_seed = result.used_seed
        out_filename = f"{stamp}_{used_seed}.wav"
        out_path = save_wav(
            _OUTPUT_DIR / out_filename,
            result.audios[0].float(),
            result.sample_rate,
        )
        out_path_str = str(out_path)

        stdout_log(f"[my-gen] saved: {out_path_str}")

        # --- DB に書き込み ---
        insert_generation(
            text=text_value,
            caption=caption_value or None,
            seed=used_seed,
            num_steps=int(num_steps),
            cfg_scale_text=float(cfg_scale_text),
            cfg_scale_caption=float(cfg_scale_caption),
            cfg_guidance_mode=str(cfg_guidance_mode),
            checkpoint=str(checkpoint).strip(),
            file_path=out_path_str,
        )
        stdout_log("[my-gen] DB insert 完了")

        # --- 履歴を更新 ---
        # 先頭に追加して5件に切り詰める
        history_paths = [out_path_str] + history_paths[: _MAX_HISTORY - 1]

        # --- ログ文字列を組み立て ---
        runtime_msg = "runtime: reloaded" if reloaded else "runtime: reused"
        detail_lines = [
            runtime_msg,
            f"iteration: {iteration}",
            f"seed_used: {used_seed}",
            f"saved: {out_path_str}",
            *result.messages,
        ]
        detail_text = "\n".join(detail_lines)
        timing_text = _format_timings(result.stage_timings, result.total_to_decode)

        # --- Audio×5 の更新を組み立て ---
        # Why: gr.update() だと autoplay=False を送ってもブラウザ側の <audio> 要素に
        #      autoplay 属性が残留してしまう問題がある。gr.Audio() コンストラクタ形式で
        #      返すことで、autoplay OFF 時は属性自体を設定しないようにして確実に制御する。
        #
        # キュー再生の仕組み（autoplay ON 時）:
        #   Python 側は常に autoplay=True で最新音声を設定する。
        #   ブラウザ側の JS（_QUEUE_PLAYBACK_JS）が再生中かどうかを判定し、
        #   再生中なら autoplay を除去してキューに積む。
        #   つまり「キューに積むか即再生か」の判断は JS 側に委ねている。
        audio_updates: list[gr.Audio] = []
        for i in range(_MAX_HISTORY):
            if i < len(history_paths):
                should_autoplay = autoplay and i == 0
                # autoplay は最新の1件（i==0）かつ autoplay=True の場合のみ有効
                # autoplay=False の場合はキーワード自体を渡さず、属性残留を防ぐ
                if should_autoplay:
                    audio_updates.append(
                        gr.Audio(
                            value=history_paths[i],
                            visible=True,
                            autoplay=True,
                        )
                    )
                else:
                    audio_updates.append(
                        gr.Audio(
                            value=history_paths[i],
                            visible=True,
                        )
                    )
            else:
                audio_updates.append(gr.Audio(value=None, visible=False))

        yield (*audio_updates, detail_text, timing_text, history_paths)

        # forever=False なら1回で終了
        if not forever:
            break
            
        # 停止要求があれば1回出力した後でもBreak
        if _session_stop_flags.get(session_id, False):
            stdout_log(f"[my-gen] Generation stopped by user after yield (session: {session_id})")
            break

        # forever モード時は seed=None にしてランダム化
        # Why: 同じ seed で繰り返しても同じ音声が生成されるだけなので、
        #      連続生成時はランダムシードに切り替える
        seed = None


def build_ui() -> gr.Blocks:
    """
    Gradio UI を構築して返す。

    本家 build_ui() との主な差分:
    - 候補グリッド（32枠）を廃止し、直近5件の履歴表示に置き換え
    - autoplay トグルを追加
    - Forever（連続生成）チェックボックスを追加
    - num_candidates スライダーを削除
    """
    default_checkpoint = _default_checkpoint()
    default_model_device = _default_model_device()
    default_codec_device = _default_codec_device()
    device_choices = list_available_runtime_devices()
    model_precision_choices = _precision_choices_for_device(default_model_device)
    codec_precision_choices = _precision_choices_for_device(default_codec_device)

    # head: HTML の <head> セクションに注入するカスタム JavaScript
    # キュー再生用の JS をここで読み込む
    with gr.Blocks(title="Irodori-TTS My Generator", head=_QUEUE_PLAYBACK_JS) as demo:
        gr.Markdown("# Irodori-TTS 独自生成UI")
        gr.Markdown(
            "VoiceDesign版モデル向けの独自UIです。"
            "caption を入れると caption/style conditioning、空欄なら text-only で推論します。"
        )

        # --- モデル設定行 ---
        with gr.Row():
            checkpoint = gr.Textbox(
                label="Checkpoint (.pt/.safetensors or HF repo id)",
                value=default_checkpoint,
                scale=4,
            )
            model_device = gr.Dropdown(
                label="Model Device",
                choices=device_choices,
                value=default_model_device,
                scale=1,
            )
            model_precision = gr.Dropdown(
                label="Model Precision",
                choices=model_precision_choices,
                value=model_precision_choices[0],
                scale=1,
            )
            codec_device = gr.Dropdown(
                label="Codec Device",
                choices=device_choices,
                value=default_codec_device,
                scale=1,
            )
            codec_precision = gr.Dropdown(
                label="Codec Precision",
                choices=codec_precision_choices,
                value=codec_precision_choices[0],
                scale=1,
            )
            # ウォーターマークは常にOFF（gr.State で非表示管理）
            enable_watermark = gr.State(False)

        # --- モデル読み込み/解放ボタン ---
        with gr.Row():
            load_model_btn = gr.Button("Load Model")
            clear_cache_btn = gr.Button("Unload Model")
            clear_cache_msg = gr.Textbox(label="Model Status", interactive=False)

        # --- テキスト入力 ---
        text = gr.Textbox(label="Text", lines=4)
        caption = gr.Textbox(
            label="Caption / Style Prompt (optional)",
            lines=4,
        )

        # --- サンプリング設定 ---
        # Why: num_candidates は常に1なのでスライダーを削除
        with gr.Accordion("Sampling", open=True):
            with gr.Row():
                num_steps = gr.Slider(
                    label="Num Steps", minimum=1, maximum=120, value=40, step=1
                )
                seed_raw = gr.Textbox(label="Seed (blank=random)", value="")

            with gr.Row():
                cfg_guidance_mode = gr.Dropdown(
                    label="CFG Guidance Mode",
                    choices=["independent", "joint", "alternating"],
                    value="independent",
                )
                cfg_scale_text = gr.Slider(
                    label="CFG Scale Text",
                    minimum=0.0,
                    maximum=10.0,
                    value=2.0,
                    step=0.1,
                )
                cfg_scale_caption = gr.Slider(
                    label="CFG Scale Caption",
                    minimum=0.0,
                    maximum=10.0,
                    value=4.0,
                    step=0.1,
                )

        # --- Advanced 設定 ---
        with gr.Accordion("Advanced (Optional)", open=False):
            cfg_scale_raw = gr.Textbox(label="CFG Scale Override (optional)", value="")
            with gr.Row():
                cfg_min_t = gr.Number(label="CFG Min t", value=0.5)
                cfg_max_t = gr.Number(label="CFG Max t", value=1.0)
                context_kv_cache = gr.Checkbox(label="Context KV Cache", value=True)
            with gr.Row():
                max_text_len_raw = gr.Textbox(label="Max Text Len (optional)", value="")
                max_caption_len_raw = gr.Textbox(label="Max Caption Len (optional)", value="")
            with gr.Row():
                truncation_factor_raw = gr.Textbox(
                    label="Truncation Factor (optional)", value=""
                )
                rescale_k_raw = gr.Textbox(label="Rescale k (optional)", value="")
                rescale_sigma_raw = gr.Textbox(label="Rescale sigma (optional)", value="")

        # --- 生成制御 ---
        with gr.Row():
            generate_btn = gr.Button("Generate", variant="primary", scale=3)
            # autoplay: 最新の1件を自動再生するかの切り替え
            autoplay = gr.Checkbox(label="Autoplay", value=True, scale=1)
            # forever: ONにすると停止ボタンを押すまで連続生成する
            forever = gr.Checkbox(label="Forever", value=False, scale=1)
            # Gradio の .click() で連続生成を止めるための停止ボタン
            stop_btn = gr.Button("Stop", variant="stop", scale=1)

        # --- 直近5件の履歴表示 ---
        # Why: 候補グリッド（32枠）を廃止し、直近5件の生成結果を縦に並べて表示する。
        #      最新が上に来るため、生成のたびに新しい音声がすぐ確認できる。
        gr.Markdown("### 直近の生成結果")
        # gr.State: Gradio のセッション内でデータを保持する仕組み
        # ここでは直近5件の wav ファイルパスを配列で管理する
        history_state = gr.State(value=[])

        out_audios: list[gr.Audio] = []
        for i in range(_MAX_HISTORY):
            # elem_id: カスタム JS から DOM 要素を特定するために使用
            # 最新の1件 (i=0) は "audio-0" という ID を付与し、
            # JS のキュー再生ロジックがこの要素を監視する
            out_audios.append(
                gr.Audio(
                    label=f"#{i + 1}",
                    type="filepath",
                    interactive=False,
                    visible=(False),  # 初期状態では非表示（生成後に表示される）
                    elem_id=f"audio-{i}",
                )
            )

        # --- キューインジケーター ---
        # Why: Forever モードで生成が再生より速い場合、キューに溜まった件数を
        #      ユーザーに知らせるための表示。JS 側から値を更新する。
        gr.Textbox(
            label="",
            interactive=False,
            elem_id="queue-indicator",
            max_lines=1,
            container=False,
        )

        # --- ログ出力 ---
        out_log = gr.Textbox(label="Run Log", lines=6)
        out_timing = gr.Textbox(label="Timing", lines=6)

        # --- イベントバインド ---

        # 生成ボタンクリック時
        # Why: _run_generation はジェネレータ関数なので、Gradio は yield ごとに
        #      UI を逐次更新する。forever=True の場合は停止ボタンで中断できる。
        generate_btn.click(
            _run_generation,
            inputs=[
                checkpoint,
                model_device,
                model_precision,
                codec_device,
                codec_precision,
                enable_watermark,
                text,
                caption,
                num_steps,
                seed_raw,
                cfg_guidance_mode,
                cfg_scale_text,
                cfg_scale_caption,
                cfg_scale_raw,
                cfg_min_t,
                cfg_max_t,
                context_kv_cache,
                max_text_len_raw,
                max_caption_len_raw,
                truncation_factor_raw,
                rescale_k_raw,
                rescale_sigma_raw,
                autoplay,
                forever,
                history_state,
            ],
            outputs=[*out_audios, out_log, out_timing, history_state],
        )

        def _handle_stop(req: gr.Request):
            """停止フラグを立てて現在の処理が終わり次第ループを抜ける"""
            sid = req.session_hash if req else "default"
            _session_stop_flags[sid] = True
            return "※停止要求を受け付けました。現在の生成が完了すると停止します。"

        # 停止ボタン: generate_forever のジェネレータループを中断する
        # Why: queue=False にすることで順次処理キューをバイパスし、即座にフラグを立てる。
        #      cancels=[] を使うと UI 全体がエラー表示になってしまう問題を回避するため。
        stop_btn.click(fn=_handle_stop, inputs=[], outputs=[out_log], queue=False)

        # デバイス変更時に精度選択肢を動的更新
        model_device.change(
            _on_model_device_change, inputs=[model_device], outputs=[model_precision]
        )
        codec_device.change(
            _on_codec_device_change, inputs=[codec_device], outputs=[codec_precision]
        )

        # モデル読み込み/解放
        load_model_btn.click(
            _describe_runtime,
            inputs=[
                checkpoint,
                model_device,
                model_precision,
                codec_device,
                codec_precision,
                enable_watermark,
            ],
            outputs=[clear_cache_msg],
        )
        clear_cache_btn.click(_clear_runtime_cache, outputs=[clear_cache_msg])

    return demo


def main() -> None:
    """エントリーポイント: コマンドライン引数を解析して Gradio サーバーを起動"""
    parser = argparse.ArgumentParser(
        description="独自生成UI for Irodori-TTS VoiceDesign checkpoints."
    )
    parser.add_argument("--server-name", default="127.0.0.1")
    parser.add_argument("--server-port", type=int, default=7862)
    parser.add_argument("--share", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    demo = build_ui()
    # concurrency_limit=1: GPU を使うため、同時に1件しか処理しない
    demo.queue(default_concurrency_limit=1)
    demo.launch(
        server_name=args.server_name,
        server_port=args.server_port,
        share=bool(args.share),
        debug=bool(args.debug),
        inbrowser=True,
    )


if __name__ == "__main__":
    main()
