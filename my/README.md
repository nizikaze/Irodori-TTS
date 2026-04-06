# Irodori-TTS — Fork by nizikaze

本家リポジトリ [Aratako/Irodori-TTS](https://github.com/Aratako/Irodori-TTS) のフォークです。
本家の使い方・モデル情報はルートの [README.md](../README.md) を参照してください。

## このフォークについて

本家コードを壊さずに自分の実験・改造を重ねるため、独自コードはすべて `my/` ディレクトリ以下に置いています。

## ディレクトリ構成

```
my/
├── README.md        # このファイル
├── scripts/         # 自作スクリプト（推論・バッチ処理など）
├── gradio/          # 本家UIを改造したGradioアプリ
├── configs/         # 自分用の設定ファイル
└── docs/            # 運用メモ・設計メモ
    └── fork-workflow.md
```

## 運用方針

- 本家ファイルは原則変更しない
- 本家の関数を使いたい場合は `my/` 側でimportしてラップする
- 本家の更新取り込みは `git fetch upstream && git rebase upstream/main`

詳細は [my/docs/fork-workflow.md](docs/fork-workflow.md) を参照。

## 独自の変更・追加機能

<!-- 独自機能を追加したらここに記録する -->

| 機能 | 概要 | ファイル |
|------|------|------|
| （未追加） | | |
