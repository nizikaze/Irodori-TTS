---
trigger: always_on
---

# Git Workflow Rules for AI Agent

## 基本原則

- **メインのクローンディレクトリでは絶対にコード変更しない**
- すべての作業は `git worktree` で作成した専用ディレクトリで行う
- 1タスク = 1ブランチ = 1 worktree
- 作業中のコードを未コミットのまま残さない（作業終了時に必ずコミットする）
- ターミナルで出力結果が長くなるコマンドを実行する場合は、直接ターミナルに出力させず、一度 > output.txt のようにファイルへリダイレクトし、そのファイルから内容を読み込んで確認するようにしてください

---

## ブランチ戦略

- デフォルトブランチは **main** を使用する（masterは使わない）
- Phase単位でブランチを切る

### ブランチ命名規則

| 種別 | 命名パターン | 例 |
|------|-------------|-----|
| Phase作業 | `phase/<番号>-<概要>` | `phase/1-initial-setup` |
| 新機能 | `feature/<簡潔な説明>` | `feature/add-oauth` |
| バグ修正 | `fix/<issue番号>-<説明>` | `fix/142-null-check` |
| リファクタ | `refactor/<説明>` | `refactor/extract-auth-service` |
| ドキュメント | `docs/<説明>` | `docs/api-reference` |

---

## 作業開始

1. メインディレクトリで最新の main を pull する

```bash
cd ~/project  # メインクローン
git checkout main
git pull origin main
```

2. worktree を作成して移動する

```bash
git worktree add ./worktrees/<branch-name> -b <branch-name>
cd ./worktrees/<branch-name>
```


> **注意:** `worktrees/` は `.gitignore` に追加済みであること（後述）

---

## コミット

- 作業が一区切りついたら必ずコミットする。未コミットの変更を残して作業を終えない
- コミットメッセージは Conventional Commits に従う
- 1つの論理的変更につき1コミット（巨大な1コミットにまとめない）

```
feat: OAuth認証を追加
fix(#142): ユーザー取得時のnullチェック追加
refactor: 認証ロジックをAuthServiceに分離
docs: API仕様書を更新
```

---

## コメント方針

このプロジェクトのコードは **日本語話者で、フロントエンドの知識がほとんどない人** が保守する可能性がある。
以下を徹底すること：

- コメントは日本語で書く
- 「なぜこの実装にしたか（Why）」を必ず書く。「何をしているか（What）」だけでは不十分
- フロントエンド特有の概念（状態管理、ライフサイクル、非同期処理、CSS設計など）には補足説明を入れる
- 略語・専門用語を使う場合は初出時に意味を添える
- 関数・コンポーネントの冒頭に、その役割・引数・戻り値の概要をJSDocまたはコメントブロックで記述する

### コメント例

```javascript
/**
 * ユーザー一覧を取得して表示するコンポーネント
 *
 * - APIから取得したデータを画面に表示する
 * - useEffect: 画面が表示されたタイミングで自動的に処理を実行するReactの仕組み
 * - useState: コンポーネント内でデータを保持・更新するReactの仕組み
 */
function UserList() {
  // users: 表示するユーザーデータの配列
  // setUsers: usersを更新するための関数（Reactの状態管理）
  const [users, setUsers] = useState([]);

  // 画面の初回表示時にAPIからユーザー一覧を取得する
  // 空配列 [] を渡すことで「初回のみ実行」という意味になる（Reactの仕様）
  useEffect(() => {
    fetchUsers().then((data) => setUsers(data));
  }, []);
}
```

---

## ドキュメント方針

- `docs_by_human/` フォルダ内のファイルは **指示されない限り絶対に編集しない**
- 人間が書いたドキュメントとエージェントが書いたドキュメントを混在させない

---

## PR作成

作業完了後、以下の手順でPRを作成する。

```bash
git push origin <branch-name>
gh pr create \
  --title "<type>: <変更内容を1行で>" \
  --body "$(cat <<'EOF'
## 概要
<!-- 何をなぜ変えたか -->

## 変更内容
<!-- 主な変更点を箇条書き -->

## 影響範囲
<!-- 影響するモジュール・機能 -->

## テスト
<!-- 実施したテスト・確認事項 -->
EOF
)" \
  --base main \
  --head <branch-name>
```

### 必須事項

- PRは通常のPRとして作成する（マージする準備ができていない場合のみ `--draft` を付ける）
- bodyの各セクションは具体的に書く（テンプレートのまま残さない）
- 作成後、PRのURLをArtifactまたはチャットで報告する

---

## 作業完了後のクリーンアップ

PRがマージされたことを確認したら：

```bash
git worktree remove ./worktrees/<branch-name>
git branch -d <branch-name>
```

定期的に不要な参照を掃除：

```bash
git worktree prune
git fetch --prune
```

---

## 並行作業時の注意

- 複数タスクを並行する場合、各エージェントに別々の worktree パスを指定する
- 同じファイルを複数ブランチで同時に編集している場合、マージ時にコンフリクトの可能性がある旨を報告する
- worktree 一覧の確認: `git worktree list`

---

## ディレクトリ構成イメージ

```
project/                              # リポジトリルート
├── .git/
├── .gitignore                        # /worktrees/ を除外済み
├── docs/
│   ├── docs_by_human/                     # 人間管理のドキュメント（編集禁止）
└── worktrees/                        # worktree 置き場（.gitignore で除外）
    ├── phase/1-initial-setup/
    ├── feature/add-oauth/
    └── fix/142-null-check/
```

---

## やってはいけないこと

- メインクローンで直接ブランチを切って作業する
- 未コミットの変更を残したまま作業を終了する
- worktree を削除せず放置する
- `--force` push する（事前に人間に確認を取ること）
- main ブランチに直接コミットする
- `docs_by_human/` 内のファイルを編集する
- コメントを英語で書く、またはコメントなしでコードを書く