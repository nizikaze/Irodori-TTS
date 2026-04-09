"""
Irodori-TTS 独自生成UI（Gradio）。

本家 gradio_app_voicedesign.py をベースに、以下の変更を加えた生成画面:
- 候補グリッド（32枠）・num_candidates スライダーを廃止（常に1件生成）
- ファイル名規則を {YYYYMMDD_HHMMSS}_{seed}.wav に変更
- 直近5件の履歴表示（Audio×5）
- autoplay ON/OFF トグル
- Generate Forever / Cancel Forever ボタンによる連続生成制御
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

# --------------------------------------------------------------------------- #
#  セッションごとの autoplay フラグ管理
#
#  Why: Gradio のジェネレータ関数は、inputs を関数呼び出し時に一度だけ評価する。
#       そのため Generate Forever のループ中に UI 上の autoplay チェックボックスを
#       変更しても、ジェネレータ内の autoplay 引数は最初の値のまま変わらない。
#       この問題を解決するため、autoplay の変更イベントでグローバル変数を更新し、
#       ジェネレータのループ内からそのフラグをリアルタイムに参照する。
# --------------------------------------------------------------------------- #
_session_autoplay_flags: dict[str, bool] = {}

# 生成した wav を保存するディレクトリ
_OUTPUT_DIR = Path(__file__).resolve().parent / "data" / "outputs"

# --------------------------------------------------------------------------- #
#  Generate Forever 稼働中に表示するアニメーションスピナーの HTML/CSS
#
#  Why: Generate Forever が動いていることをユーザーに視覚的に伝えるため。
#       CSSアニメーション（回転）で動くスピナーを生成ボタンの近くに表示する。
#       Gradio の gr.HTML で注入し、visible の切り替えで表示/非表示を制御する。
# --------------------------------------------------------------------------- #
_FOREVER_SPINNER_HTML = """
<div style="display: flex; align-items: center; gap: 8px; padding: 4px 0;">
    <div style="
        width: 20px;
        height: 20px;
        border: 3px solid rgba(124, 58, 237, 0.2);
        border-top-color: #7c3aed;
        border-radius: 50%;
        animation: forever-spin 0.8s linear infinite;
    "></div>
    <span style="
        font-size: 14px;
        font-weight: 600;
        color: #7c3aed;
    ">Generate Forever 実行中…</span>
</div>
<style>
    @keyframes forever-spin {
        to { transform: rotate(360deg); }
    }
</style>
"""

# --------------------------------------------------------------------------- #
#  キュー再生用カスタム JavaScript
#
#  Why: gr.Audio は HTML5 の <audio> 要素の ended イベントを Python 側に
#       通知する仕組みを持っていない。そのため、再生中に新しい音声が来たとき
#       「現在の再生を中断せずキューに積み、再生完了後に次を再生する」という
#       キュー再生を実現するには、ブラウザ側の JavaScript で制御する必要がある。
#       また Gradio の UI は頻繁に DOM や src を書き換えるため、それとは独立した
#       専用の <audio> プレイヤーを用いることで安定した再生を実現する。
# --------------------------------------------------------------------------- #
_QUEUE_PLAYBACK_JS = f"""
<script>
(function() {{
    'use strict';

    window._queueAudioList = [];
    window._isQueuePlaying = false;
    window._queueForcePaused = false;
    const MAX_QUEUE_SIZE = {_MAX_QUEUE_SIZE};

    /**
     * Python 側から発行された新しいオーディオURLをキューに追加する。
     */
    window.enqueueAudio = function(url) {{
        if (!url) return;
        
        window._queueAudioList.push(url);
        console.log('[queue-playback] queued:', url, 'size:', window._queueAudioList.length);
        window.updateQueueUI();
        
        // If not currently playing and not forcibly paused by user, start now
        if (!window._isQueuePlaying && !window._queueForcePaused) {{
            window.playNextInQueue();
        }}
    }};

    /**
     * 次のキューを再生する。
     */
    window.playNextInQueue = function() {{
        const audioEl = document.getElementById('queue-audio');
        if (!audioEl) return;
        
        if (window._queueAudioList.length > 0) {{
            let url = window._queueAudioList.shift();
            
            // max queue size limit
            while (window._queueAudioList.length > MAX_QUEUE_SIZE) {{
                window._queueAudioList.shift();
            }}

            window._isQueuePlaying = true;
            window._queueForcePaused = false;
            audioEl.src = url;
            audioEl.play().catch(function(e) {{
                console.warn('[queue-playback] play() blocked:', e.message);
                window._isQueuePlaying = false;
                window.updateQueueUI();
            }});
            console.log('[queue-playback] playing:', url);
        }} else {{
            window._isQueuePlaying = false;
            console.log('[queue-playback] queue empty, idle');
        }}
        window.updateQueueUI();
    }};

    /**
     * キューのUI状態を更新する。
     */
    window.updateQueueUI = function() {{
        const container = document.getElementById('queue-player-container');
        const badge = document.getElementById('queue-count-badge');
        if (!container || !badge) return;
        
        // Always show the player if there's anything playing, forced paused, or waiting
        if (window._isQueuePlaying || window._queueForcePaused || window._queueAudioList.length > 0) {{
            container.style.display = 'block';
        }} else {{
            container.style.display = 'none';
        }}
        
        if (window._queueAudioList.length > 0) {{
            badge.style.display = 'inline-block';
            badge.innerText = window._queueAudioList.length;
        }} else {{
            badge.style.display = 'none';
        }}
    }};
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
        autoplay:      最新音声を自動再生するかどうか（初回値、以降はセッション変数を参照）
        forever:       連続生成モードかどうか（ボタンに応じて固定値が渡される）
        history_paths: 直近5件の wav パスリスト（gr.State から受け取る）
        request:       Gradio のリクエスト情報（セッション管理用）

    Yields:
        tuple: (Audio×5 の更新, ログ文字列, タイミング文字列,
                更新後の history_paths, スピナー表示状態)
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

    # autoplay の初期値をセッション変数にも反映
    # Why: ジェネレータ起動前のチェックボックス状態を保持する
    _session_autoplay_flags[session_id] = autoplay

    # forever モード開始時にスピナーを表示
    if forever:
        stdout_log(f"[my-gen] Generate Forever started (session: {session_id})")

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

        # --- autoplay をリアルタイムに参照 ---
        # Why: Generate Forever ループ中に autoplay チェックボックスが変更された場合、
        #      セッション変数から最新の値を取得する。
        current_autoplay = _session_autoplay_flags.get(session_id, autoplay)

        # キュー再生用: Autoplay ON ならファイルパスを、OFF なら None を返す
        new_queue_path = out_path_str if current_autoplay else None

        # --- Audio×5 の更新を組み立て ---
        # Why: キュー再生用に独立したオーディオプレイヤーが全てを処理するため、
        #      履歴一覧の Audio コンポーネントは autoplay=False で固定する。
        #      これにより、Gradio 側が勝手に再生を開始して再生音が重複するのを防ぐ。
        audio_updates: list[gr.Audio] = []
        for i in range(_MAX_HISTORY):
            if i < len(history_paths):
                audio_updates.append(
                    gr.Audio(
                        value=history_paths[i],
                        visible=True,
                        autoplay=False,
                    )
                )
            else:
                audio_updates.append(gr.Audio(value=None, visible=False))

        # スピナーの表示状態を決定
        spinner_visible = forever

        yield (*audio_updates, detail_text, timing_text, history_paths, gr.update(visible=spinner_visible), new_queue_path)

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

    # --- ループ終了後: スピナーを確実に非表示にする ---
    # Why: 停止ボタンやエラーでループを抜けた場合でも、スピナーを非表示にする。
    #      最後の yield でスピナーを非表示にすることで、UIが正しい状態に戻る。
    if forever:
        stdout_log(f"[my-gen] Generate Forever ended (session: {session_id})")
        # 最後に Audio は変更せず、スピナーだけ非表示にする更新を yield
        # 各 Audio は現在の状態を維持（gr.update() で何も変えない）
        no_change_audios = [gr.update() for _ in range(_MAX_HISTORY)]
        yield (*no_change_audios, "Generate Forever が終了しました。", gr.update(), history_paths, gr.update(visible=False), None)


def build_ui() -> gr.Blocks:
    """
    Gradio UI を構築して返す。

    本家 build_ui() との主な差分:
    - 候補グリッド（32枠）を廃止し、直近5件の履歴表示に置き換え
    - autoplay トグルを追加
    - Generate Forever / Cancel Forever ボタンで連続生成を制御
      （旧 Forever チェックボックス + Stop ボタンを廃止）
    - Generate Forever 中にスピナーアイコンを表示
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
        # Why: EasyReforge 風に Generate / Generate Forever / Cancel Forever の
        #      ボタン3つで制御する。旧 Forever チェックボックス + Stop ボタンを廃止。
        #      Generate Forever 中はスピナーアイコンを表示して稼働中であることを示す。
        with gr.Row():
            generate_btn = gr.Button("Generate", variant="primary", scale=3)
            generate_forever_btn = gr.Button("Generate Forever", variant="secondary", scale=2)
            # autoplay: 最新の1件を自動再生するかの切り替え
            autoplay = gr.Checkbox(label="Autoplay", value=True, scale=1)
            cancel_forever_btn = gr.Button("Cancel Forever", variant="stop", scale=1)

        # --- Generate Forever 稼働中のスピナー表示 ---
        # Why: Generate Forever が動いていることを視覚的に分かりやすくするため、
        #      生成ボタンの近くにアニメーション付きスピナーを配置する。
        #      初期状態では非表示で、Generate Forever 開始時に visible=True にする。
        forever_spinner = gr.HTML(
            value=_FOREVER_SPINNER_HTML,
            visible=False,
        )

        # --- forever フラグ用の固定値 State ---
        # Why: Generate ボタンと Generate Forever ボタンで同じ _run_generation 関数を
        #      使い回すため、forever パラメータを gr.State の固定値として渡す。
        #      Generate ボタン → forever=False（1回生成）
        #      Generate Forever ボタン → forever=True（連続生成）
        forever_false = gr.State(False)
        forever_true = gr.State(True)

        # --- キュー用 UI ---
        # Why: 独立した再生プレイヤーでキューを管理するため、コンテナごと表示する。
        #      直近の生成結果より上に配置することで、ユーザーの目に留まりやすくする。
        gr.HTML("""
        <div id="queue-player-container" style="display:none; padding: 10px; background: #f3f4f6; border-radius: 8px; border: 1px solid #e5e7eb; margin-bottom: 15px;">
            <div style="font-size:14px; font-weight:bold; margin-bottom:5px; color: #374151;">
                ▶️ 連続再生プレイヤー <span id="queue-count-badge" style="background:#7c3aed; color:white; border-radius:10px; padding:2px 8px; font-size:12px; margin-left:5px; display:none;">0</span>
            </div>
            <audio id="queue-audio" controls style="width: 100%;" 
                onended="if(window.playNextInQueue) window.playNextInQueue()"
                onplay="window._isQueuePlaying = true; window._queueForcePaused = false; if(window.updateQueueUI) window.updateQueueUI()"
                onpause="if(!this.ended){ window._queueForcePaused = true; window._isQueuePlaying = false; if(window.updateQueueUI) window.updateQueueUI(); }"
            ></audio>
        </div>
        """)
        
        # --- キュー処理用隠し File ---
        # 生成完了のたびにこのコンポーネントに音声パスが渡され、JS(enqueueAudio)にURL(Token付)が発火する
        queue_new_item = gr.File(visible=False, elem_id="queue-new-item")
        queue_new_item.change(
            fn=None,
            inputs=[queue_new_item],
            js="""
            function(fileObj) {
                if (fileObj && fileObj.url && typeof window.enqueueAudio === 'function') {
                    window.enqueueAudio(fileObj.url);
                }
            }
            """
        )

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

        # --- ログ出力 ---
        out_log = gr.Textbox(label="Run Log", lines=6)
        out_timing = gr.Textbox(label="Timing", lines=6)

        # --- 共通の入力リスト ---
        # Why: Generate ボタンと Generate Forever ボタンで共通する入力パラメータを
        #      まとめて定義し、コードの重複を避ける。
        #      forever パラメータだけがボタンごとに異なる。
        def _make_inputs(forever_state: gr.State) -> list:
            """
            ボタンごとに異なる forever State を含む入力リストを生成する。

            Args:
                forever_state: gr.State(False) または gr.State(True)

            Returns:
                list: _run_generation に渡す入力コンポーネントのリスト
            """
            return [
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
                forever_state,
                history_state,
            ]

        # 出力リスト（Audio×5 + ログ + タイミング + 履歴State + スピナー + 新規キューパス）
        gen_outputs = [*out_audios, out_log, out_timing, history_state, forever_spinner, queue_new_item]

        # --- イベントバインド ---

        # Generate ボタン: 1回だけ生成（forever=False）
        # Why: _run_generation はジェネレータ関数なので、Gradio は yield ごとに
        #      UI を逐次更新する。forever=False なら1回で終了する。
        generate_btn.click(
            _run_generation,
            inputs=_make_inputs(forever_false),
            outputs=gen_outputs,
        )

        # Generate Forever ボタン: 連続生成（forever=True）
        # Why: forever=True の固定値を渡すことで、ジェネレータが停止要求まで
        #      ループし続ける。スピナーは _run_generation 内で制御される。
        generate_forever_btn.click(
            _run_generation,
            inputs=_make_inputs(forever_true),
            outputs=gen_outputs,
        )

        def _handle_stop(req: gr.Request):
            """
            停止フラグを立てて現在の処理が終わり次第ループを抜ける。
            Cancel Forever ボタンから呼ばれる。
            """
            sid = req.session_hash if req else "default"
            _session_stop_flags[sid] = True
            return "※停止要求を受け付けました。現在の生成が完了すると停止します。"

        # Cancel Forever ボタン: Generate Forever のジェネレータループを中断する
        # Why: queue=False にすることで順次処理キューをバイパスし、即座にフラグを立てる。
        #      cancels=[] を使うと UI 全体がエラー表示になってしまう問題を回避するため。
        cancel_forever_btn.click(fn=_handle_stop, inputs=[], outputs=[out_log], queue=False)

        def _handle_autoplay_change(value: bool, req: gr.Request):
            """
            autoplay チェックボックスの変更をセッション変数に反映する。

            Why: Generate Forever ループ中に autoplay を OFF にした場合、
                 次の生成から autoplay 属性を付与しないようにするため。
                 ジェネレータの inputs は起動時に一度だけ評価されるので、
                 ループ中の変更はこのイベントハンドラ経由でしか取得できない。
            """
            sid = req.session_hash if req else "default"
            _session_autoplay_flags[sid] = value
            stdout_msg = "ON" if value else "OFF"
            print(f"[my-gen] autoplay changed to {stdout_msg} (session: {sid})", flush=True)

        # autoplay チェックボックスの変更イベント
        # Why: queue=False で即座に反映し、Generate Forever ループ中でも
        #      次の生成から autoplay の ON/OFF が反映されるようにする。
        autoplay.change(
            fn=_handle_autoplay_change,
            inputs=[autoplay],
            outputs=[],
            queue=False,
        )

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
        allowed_paths=[str(_OUTPUT_DIR)],
    )


if __name__ == "__main__":
    main()
