"""
TTS生成履歴の閲覧・編集UI（Streamlit版）。

DBに保存された生成データをカード形式で一覧表示し、
フィルター・ソート・編集（レーティング/お気に入り/メモ）機能を提供する。

起動方法:
    streamlit run my/streamlit_history.py

Why Streamlit:
    Gradioは生成UIに向いているが、一覧表示・フィルタリング・編集のような
    CRUD的な操作にはStreamlitの方がレイアウトの自由度が高い。
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

# my/ 配下のモジュールをインポートするため、プロジェクトルートからの相対パスで指定
# streamlit run my/streamlit_history.py で起動する想定
from my.db import init_db, select_generations, update_generation

# --------------------------------------------------------------------------- #
#  定数
# --------------------------------------------------------------------------- #

# ソート順の表示名とDB側のorder_byキーの対応
_SORT_OPTIONS: dict[str, str] = {
    "新しい順": "created_at_desc",
    "古い順": "created_at_asc",
    "レーティング順": "rating_desc",
    "お気に入り優先": "favorite_desc",
}

# レーティングの選択肢（0=未評価、1〜5=評価値）
_RATING_OPTIONS: list[str] = ["未評価", "★1", "★2", "★3", "★4", "★5"]


# --------------------------------------------------------------------------- #
#  ページ設定
#  - Streamlitの最初の呼び出しは set_page_config でなければならない
# --------------------------------------------------------------------------- #

st.set_page_config(
    page_title="TTS生成履歴",
    page_icon="🎵",
    layout="wide",
)

# --------------------------------------------------------------------------- #
#  カスタムCSS
#  - Streamlitのデフォルトスタイルに加え、カード形式の見た目を整える
#  - st.markdown(unsafe_allow_html=True) で注入する
# --------------------------------------------------------------------------- #

st.markdown(
    """
    <style>
    /* カードコンテナ: 各生成レコードを囲むボックス */
    .gen-card {
        border: 1px solid rgba(128, 128, 128, 0.3);
        border-radius: 12px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        background: rgba(255, 255, 255, 0.02);
        transition: box-shadow 0.2s ease;
    }
    .gen-card:hover {
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
    }

    /* メタ情報のラベルスタイル */
    .meta-label {
        font-size: 0.75rem;
        color: rgba(128, 128, 128, 0.8);
        margin-bottom: 0.1rem;
    }
    .meta-value {
        font-size: 0.9rem;
        margin-bottom: 0.5rem;
    }

    /* テキスト表示を見やすく */
    .gen-text {
        font-size: 1.0rem;
        font-weight: 600;
        margin-bottom: 0.3rem;
    }
    .gen-caption {
        font-size: 0.85rem;
        color: rgba(128, 128, 128, 0.9);
        font-style: italic;
        margin-bottom: 0.5rem;
    }

    /* お気に入りバッジ */
    .fav-badge {
        display: inline-block;
        background: linear-gradient(135deg, #ff6b6b, #ee5a24);
        color: white;
        padding: 0.15rem 0.5rem;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-left: 0.5rem;
    }

    /* ファイルなし警告 */
    .file-missing {
        color: #e74c3c;
        font-size: 0.85rem;
        padding: 0.3rem 0;
    }

    /* カード内のセパレーター */
    .card-divider {
        border-top: 1px solid rgba(128, 128, 128, 0.15);
        margin: 0.8rem 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
#  DB初期化
#  - テーブルが未作成の場合に備えて起動時に1回だけ呼ぶ
# --------------------------------------------------------------------------- #

init_db()


# --------------------------------------------------------------------------- #
#  サイドバー: フィルター・検索・ソート
# --------------------------------------------------------------------------- #

st.sidebar.title("🔍 フィルター")

# キーワード検索
# text / caption のどちらかに部分一致すれば表示する
keyword = st.sidebar.text_input(
    "キーワード検索",
    value="",
    placeholder="text / caption で検索...",
    help="生成テキストまたはキャプション（スタイルプロンプト）を部分一致で検索します。",
)

# お気に入りのみ表示
favorite_only = st.sidebar.checkbox(
    "⭐ お気に入りのみ表示",
    value=False,
)

# ソート順
sort_label = st.sidebar.selectbox(
    "📊 ソート順",
    options=list(_SORT_OPTIONS.keys()),
    index=0,  # デフォルト: 新しい順
)
# 表示ラベルからDB側のキーに変換
sort_key = _SORT_OPTIONS[sort_label]

st.sidebar.markdown("---")
st.sidebar.caption("TTS生成履歴ブラウザ v1.0")


# --------------------------------------------------------------------------- #
#  データ取得
#  - select_generations() でDB検索し結果をリストで取得
# --------------------------------------------------------------------------- #

rows = select_generations(
    keyword=keyword if keyword else None,
    favorite_only=favorite_only,
    order_by=sort_key,
)


# --------------------------------------------------------------------------- #
#  メインエリア: ヘッダー
# --------------------------------------------------------------------------- #

st.title("🎵 TTS生成履歴")
st.caption(f"全 {len(rows)} 件")

if not rows:
    st.info("条件に一致するデータがありません。")
    st.stop()


# --------------------------------------------------------------------------- #
#  ヘルパー関数
# --------------------------------------------------------------------------- #


def _format_checkpoint(checkpoint: str | None) -> str:
    """
    チェックポイント名を短縮表示する。

    長いHuggingFaceのrepo IDやローカルパスを省略して見やすくする。
    例: "Aratako/Irodori-TTS-500M-v2-VoiceDesign" → "Irodori-TTS-500M-v2-VoiceDesign"
    """
    if not checkpoint:
        return "不明"
    # '/' が含まれていれば最後の部分だけ表示（HF repo IDの場合）
    if "/" in checkpoint:
        return checkpoint.rsplit("/", 1)[-1]
    # ローカルパスの場合はファイル名部分のみ
    return Path(checkpoint).stem if "\\" in checkpoint or "/" in checkpoint else checkpoint


def _format_datetime(iso_str: str | None) -> str:
    """
    ISO 8601形式の文字列を人間が読みやすい形式に変換する。

    例: "2026-04-06T19:00:00+09:00" → "2026/04/06 19:00:00"
    """
    if not iso_str:
        return "不明"
    # ISO 8601のパース（タイムゾーン付きに対応）
    try:
        # 'T'を空白に置換し、タイムゾーン部分を除去して簡易表示
        return iso_str.replace("T", " ").rsplit("+", 1)[0].rsplit("-", 1)[0][:19]
    except Exception:
        return iso_str


def _rating_to_index(rating: int | None) -> int:
    """
    DB上のレーティング値（None / 1〜5）を、
    _RATING_OPTIONS リストのインデックス（0〜5）に変換する。

    None（未評価）→ 0, 1 → 1, ..., 5 → 5
    """
    if rating is None or rating == 0:
        return 0
    return rating


def _index_to_rating(index: int) -> int | None:
    """
    _RATING_OPTIONS のインデックスをDB上のレーティング値に変換する。

    0（未評価）→ None, 1 → 1, ..., 5 → 5
    """
    if index == 0:
        return None
    return index


# --------------------------------------------------------------------------- #
#  メインエリア: カード一覧表示
#  - 各レコードを1枚のカードとして表示
#  - 音声再生、情報表示、編集機能を含む
# --------------------------------------------------------------------------- #

for row in rows:
    gen_id: int = row["id"]
    file_path_str: str = row["file_path"]
    file_path = Path(file_path_str)

    # ---------- カード開始 ----------
    # st.container で1レコード分をグルーピング
    with st.container():
        st.markdown('<div class="gen-card">', unsafe_allow_html=True)

        # --- 上段: テキスト + お気に入りバッジ ---
        fav_badge = (
            '<span class="fav-badge">⭐ お気に入り</span>'
            if row["favorite"]
            else ""
        )
        st.markdown(
            f'<div class="gen-text">{row["text"]}{fav_badge}</div>',
            unsafe_allow_html=True,
        )

        # キャプション（スタイルプロンプト）
        if row["caption"]:
            st.markdown(
                f'<div class="gen-caption">🎨 {row["caption"]}</div>',
                unsafe_allow_html=True,
            )

        # --- 音声再生 ---
        if file_path.exists():
            st.audio(str(file_path))
        else:
            st.markdown(
                '<div class="file-missing">⚠️ 音声ファイルが見つかりません</div>',
                unsafe_allow_html=True,
            )

        # --- メタ情報（横並び表示） ---
        # st.columns で5つの情報を横に並べる
        meta_cols = st.columns(5)
        with meta_cols[0]:
            st.markdown('<div class="meta-label">🌱 Seed</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="meta-value">{row["seed"] if row["seed"] is not None else "—"}</div>',
                unsafe_allow_html=True,
            )
        with meta_cols[1]:
            st.markdown('<div class="meta-label">🔄 Steps</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="meta-value">{row["num_steps"] if row["num_steps"] is not None else "—"}</div>',
                unsafe_allow_html=True,
            )
        with meta_cols[2]:
            st.markdown('<div class="meta-label">🏷️ Checkpoint</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="meta-value">{_format_checkpoint(row["checkpoint"])}</div>',
                unsafe_allow_html=True,
            )
        with meta_cols[3]:
            st.markdown('<div class="meta-label">📅 生成日時</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="meta-value">{_format_datetime(row["created_at"])}</div>',
                unsafe_allow_html=True,
            )
        with meta_cols[4]:
            st.markdown('<div class="meta-label">⭐ レーティング</div>', unsafe_allow_html=True)
            current_rating = row["rating"]
            if current_rating is not None:
                st.markdown(
                    f'<div class="meta-value">{"★" * current_rating}{"☆" * (5 - current_rating)}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div class="meta-value">未評価</div>',
                    unsafe_allow_html=True,
                )

        # --- 区切り線 ---
        st.markdown('<div class="card-divider"></div>', unsafe_allow_html=True)

        # --- 編集エリア ---
        # st.expander で折りたたみにして、通常時はすっきり表示
        with st.expander("✏️ 編集", expanded=False):
            edit_cols = st.columns([1, 1, 2])

            # レーティング（1〜5, 未評価=0）
            with edit_cols[0]:
                new_rating_idx = st.selectbox(
                    "レーティング",
                    options=range(len(_RATING_OPTIONS)),
                    format_func=lambda i: _RATING_OPTIONS[i],
                    index=_rating_to_index(row["rating"]),
                    key=f"rating_{gen_id}",
                )
                new_rating = _index_to_rating(new_rating_idx)

            # お気に入りトグル
            with edit_cols[1]:
                new_favorite = st.checkbox(
                    "⭐ お気に入り",
                    value=bool(row["favorite"]),
                    key=f"fav_{gen_id}",
                )

            # メモ入力
            with edit_cols[2]:
                new_note = st.text_area(
                    "メモ",
                    value=row["note"] or "",
                    height=80,
                    key=f"note_{gen_id}",
                    placeholder="自由にメモを記入...",
                )

            # 保存ボタン
            # ボタン押下時にDB更新し、画面をリロードして反映する
            if st.button("💾 保存", key=f"save_{gen_id}"):
                try:
                    update_generation(
                        gen_id,
                        favorite=1 if new_favorite else 0,
                        rating=new_rating,
                        note=new_note if new_note else None,
                    )
                    st.success("保存しました！")
                    # st.rerun() で画面を再描画し、更新内容を反映する
                    # Why rerun: Streamlitは上から下に1回実行するモデルのため、
                    # DB更新後に表示を最新化するには再実行が必要
                    st.rerun()
                except ValueError as e:
                    st.error(f"保存に失敗しました: {e}")

        # カード終了タグ
        st.markdown("</div>", unsafe_allow_html=True)
