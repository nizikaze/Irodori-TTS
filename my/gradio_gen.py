"""
Irodori-TTS 独自生成UI（Gradio）。

本家 gradio_app_voicedesign.py をベースに、以下の変更を加えた生成画面:
- 候補グリッド（32枠）・num_candidates スライダーを廃止（常に1件生成）
- ファイル名規則を {YYYYMMDD_HHMMSS}_{seed}.wav に変更
- 直近5件の履歴表示（Audio×5）
- autoplay ON/OFF トグル
- generate_forever モード（チェックONで連続生成）
- 生成完了時に DB へ書き込み

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

# グローバルな停止フラグ管理用（session_hash -> 停止要求）
_session_stop_flags: dict[str, bool] = {}

# 生成した wav を保存するディレクトリ
_OUTPUT_DIR = Path(__file__).resolve().parent / "data" / "outputs"


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
        audio_updates: list[dict] = []
        for i in range(_MAX_HISTORY):
            if i < len(history_paths):
                # autoplay は最新の1件（i==0）かつ autoplay=True の場合のみ有効
                audio_updates.append(
                    gr.update(
                        value=history_paths[i],
                        visible=True,
                        autoplay=(autoplay and i == 0),
                    )
                )
            else:
                audio_updates.append(gr.update(value=None, visible=False))

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

    with gr.Blocks(title="Irodori-TTS My Generator") as demo:
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
            out_audios.append(
                gr.Audio(
                    label=f"#{i + 1}",
                    type="filepath",
                    interactive=False,
                    visible=(False),  # 初期状態では非表示（生成後に表示される）
                )
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
