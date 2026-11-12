# Merge Queue 最小実験

Cloud Build + Python 標準ライブラリで「PR は個別に成功しても、組み合わせると失敗する」を試します。
依存パッケージやデプロイは不要です。GitHub Actions の既存 workflow は無効化しています。

## 仕組み

`config/feature_a.txt` と `config/feature_b.txt` の値は 0 または 1。
合計が **1 以下**なら成功、2 なら失敗します。別ファイルなので Git の競合ではなく論理的な不整合を再現できます。

| 変更 | A | B | 結果 |
|---|---:|---:|---|
| 初期状態 | 0 | 0 | 成功 |
| PR A のみ | 1 | 0 | 成功 |
| PR B のみ | 0 | 1 | 成功 |
| A + B | 1 | 1 | 失敗 |

ローカル実行（Python 3）:

```sh
python3 -m unittest discover -s tests -v
```

## 現在の Cloud Build 検証範囲

- 設定ファイルはリポジトリ直下の `cloudbuild.yaml` です。
- 同じリポジトリの `codex/` で始まるブランチへの push と、
  `gh-readonly-queue/main/` で始まる Merge Queue の一時ブランチへの push が対象です。
- 外部 fork の PR、その他の作業ブランチ、main への直接 push は対象外です。
  対象外の PR には必須チェックが出ないため、この限定環境ではマージできません。
- PR の head と Queue の組合せ SHA に、同じ **merge-queue-test (sandbox-hi)** チェックを返します。
- ビルドは承認待ちになり、Cloud Build 側で承認するまで実行されません。
  承認前に対象 SHA、コード、`cloudbuild.yaml` の変更を確認してください。
- 現在の設定は各5分、E2_STANDARD_2、ディスク100GB、Cloud Logging のみです。
  設定ファイルの変更はこの制限も変えられます。実行回数や請求総額の厳密な上限ではありません。

確認用 PR は open のまま内容とチェックを確認できます。Queue には自動投入しません。
実際に Queue に投入すると、組合せ SHA に別のビルドが作成されます。
そのビルドを承認して成功すると main へ自動マージされ得るため、投入・承認はマージしてよいと判断した場合だけ行います。

## Cloud Build と GitHub の連携設定

この節は上記の限定構成を再現するための設定です。`cloudbuild.yaml` を置くだけでは、
GitHub App の接続、トリガー、IAM、承認、GitHub の必須チェックは設定されません。
既存環境を変更する場合は、以下の値と現在の設定を比較し、トリガーを重複作成しないでください。

### 1. Google Cloud と GitHub App を準備する

1. 請求先を設定した Google Cloud プロジェクトを用意し、Cloud Build API を有効にします。
   リポジトリ接続用の Secret Manager API と、専用サービスアカウント作成用の IAM API も確認します。
   この環境のプロジェクトは `sandbox-hi` です。
2. GitHub リポジトリの管理権限と、Organization への App インストールを承認できる権限を用意します。
   Google Cloud 側にも接続・トリガー設定・必要な IAM を管理する権限が必要です。
   設定担当者の権限を、後述のビルド実行用サービスアカウントへ付けないでください。
3. Cloud Build の **Repositories → 1st gen → Connect repository** で
   **GitHub (Cloud Build GitHub App)** を選択します。
   GitHub で **Google Cloud Build** App を認証・インストールし、接続時の同意事項を確認します。
   Organization は `test-my-team-merge-queue`、リポジトリは `test` を選び、Cloud Build 側でも接続を完了します。
   この環境は第1世代の GitHub App 連携です。第2世代の connection / Developer Connect の手順と混ぜないでください。
4. App の Repository access は **Only select repositories** にし、必要な `test` だけを対象にします。
   App を入れただけでは Cloud Build 側の接続は完了しません。対象が表示されない場合は
   GitHub の **Organization Settings → GitHub Apps → Google Cloud Build → Configure** でアクセス対象を確認します。

2026-11-12 に GitHub API で確認した App のインストール権限は以下です。
App が提示する権限の確認用であり、個別の権限を任意に選択する設定ではありません。

| Repository permission | 確認した権限 |
|---|---|
| Checks / Commit statuses | Read and write（API: `checks: write`, `statuses: write`） |
| Contents / Metadata / Issues / Pull requests | Read-only |

インストール範囲は `selected`、App は **Google Cloud Build**（App ID `10529`）です。
選択されたリポジトリ一覧も設定画面で確認してください。App に新しい権限の承認待ちがある場合は内容を確認します。
チェックが報告されないときも、無条件に All repositories や追加権限へ広げないでください。
PAT、サービスアカウント鍵、認証トークンを README やリポジトリへ保存する必要はありません。

### 2. 実行用サービスアカウントと承認者を分ける

- ビルド実行用に `merge-queue-test-build@sandbox-hi.iam.gserviceaccount.com` を使用します。
  この Python テストではプロジェクト IAM の **Logs Writer**（`roles/logging.logWriter`）でログを書き込みます。
  デプロイ、Secret Manager の値の読取り、Editor / Owner などの広い権限は付けません。
- トリガーを作成・更新する担当者には、Cloud Build Editor などのトリガー管理権限と、
  実行用アカウントに対する `iam.serviceAccounts.actAs` が必要です。
  後者は対象サービスアカウントに限定した **Service Account User**（`roles/iam.serviceAccountUser`）などで付与します。
- ビルドを承認する担当者には **Cloud Build Approver**（`roles/cloudbuild.builds.approver`）などの承認権限が必要です。
  ログを確認するには別途 Cloud Logging の閲覧権限も必要です。
  Cloud Build の承認と、GitHub の PR レビュー承認は別のものです。
- Google 管理の Cloud Build service agent と、上記のビルド実行用アカウントは別です。
  接続用の権限を実行用アカウントへコピーしないでください。

### 3. Cloud Build トリガーを設定する

Cloud Build の **Triggers** で、既存の `merge-queue-test` を次の値に設定します。
別の環境に再現する場合はプロジェクト、リポジトリ、サービスアカウントを置き換えます。

| 項目 | この環境の設定 |
|---|---|
| Project / Region | `sandbox-hi` / `global` |
| Name | `merge-queue-test` |
| Source / Repository | 第1世代 GitHub App / `test-my-team-merge-queue/test` |
| Event | **Push to a branch**（Pull request ではない） |
| Branch（正規表現） | `^(codex/.+\|gh-readonly-queue/main/.+)$` |
| Included files / Ignored files | どちらも指定なし |
| Configuration / Location | Cloud Build configuration file / Repository |
| Configuration file path | `cloudbuild.yaml` |
| Approval | **Require approval before build executes** を有効化 |
| Service account | `merge-queue-test-build@sandbox-hi.iam.gserviceaccount.com` |
| Trigger | 有効 |

API では `github.push.branch`、`filename: cloudbuild.yaml`、
`approvalConfig.approvalRequired: true`、`serviceAccount` を確認します。
以前の inline 設定 `build` のままでは、リポジトリの YAML に変更しても反映されません。
トリガーによる実行では、サービスアカウントもトリガー側の指定が使われます。

`cloudbuild.yaml` は `python:3.12-slim` でテストを実行し、`source_sha=$COMMIT_SHA` をログへ出します。
現行値は `timeout: 300s`、`queueTtl: 600s`、`E2_STANDARD_2`、ディスク `100GB`、
`logging: CLOUD_LOGGING_ONLY` です。Cloud Logging を使うため、専用アカウントに Logs Writer が必要です。
`queueTtl` は Cloud Build のキュー設定で、GitHub Merge Queue のチェック待ち時間とは別です。
これらは1ビルドの設定であり、実行回数や請求総額の上限ではありません。

### 4. GitHub の必須チェックと Merge Queue を設定する

1. まず同じリポジトリの `codex/` ブランチで、対象 SHA の Cloud Build チェックが報告されることを確認します。
   必須チェック候補に出ない場合は、トリガーと App の権限・接続先を先に確認します。
2. **Settings → Rules → Rulesets** で `main` に適用する ruleset を有効にします。
   この環境の ruleset `test` は **Default branch** を対象にし、現在の default branch は `main` です。
3. **Require status checks to pass** に **`merge-queue-test (sandbox-hi)`** を設定し、
   Expected source を **Google Cloud Build**（API の `integration_id: 10529`）にします。
   名前はトリガー名やプロジェクトを変えると変わり得るため、実際のチェック名と一致させます。
4. **Require merge queue** を有効にします。この環境は Squash、Build concurrency `5`、
   Only merge non-failing pull requests 有効、Status check timeout `60分` です。
   Bypass はありません。Cloud Build の承認待ち中も GitHub 側の待ち時間に注意してください。
5. GitHub Actions の `Merge queue demo` は無効のままにします。
   旧チェック `compatibility` は現在の必須チェックに追加しません。

現在の ruleset には削除・force push の禁止もあります。必須 PR レビュー人数の設定はありません。
Cloud Build の push トリガーは PR を開く前でも対象ブランチへの push で動きます。
一方、外部 fork や `codex/` 以外の作業ブランチには対応していません。
対象範囲を広げる場合は、承認・実行権限・費用への影響を確認してから設定を変更してください。

### 5. head と Queue を別々に検証する

1. 対象ブランチの push 後、Cloud Build のビルドが承認待ちで作られることを確認します。
   承認前に repository / branch / commit SHA、テスト、`cloudbuild.yaml`、実行用アカウントを確認します。
2. 実行してよいビルドだけを Cloud Build で承認し、ログの `source_sha` とテスト結果、
   GitHub の同じ SHA の `merge-queue-test (sandbox-hi)` が成功していることを確認します。
3. **main へマージしてよい場合だけ** PR を Merge Queue に投入します。
   `gh-readonly-queue/main/...` の push により、PR head とは異なる組合せ SHA のビルドが作られることを確認します。
4. Queue 用のビルドも個別に確認して承認します。同じ必須チェックが **Queue の SHA** に成功を返し、
   他の条件も満たせば main へ自動マージされ得ます。PR head の成功だけを Queue の成功として扱わないでください。

**確認済みの範囲（2026-11-12）:**
[PR #12](https://github.com/test-my-team-merge-queue/test/pull/12) の head
`e348d3bf1bfa4502094e52d68c1dfe14a22ac9f8` は、承認後の Cloud Build と GitHub のチェックが成功しています。
さらに `gh-readonly-queue/main/pr-12-...` の組合せ SHA
`29001aca30d7fce3058dc29dfe90af9ed0aac9ef` に対する Cloud Build
[`b0828eb7-9f67-4fc4-bda9-b386b644fb7d`](https://console.cloud.google.com/cloud-build/builds/b0828eb7-9f67-4fc4-bda9-b386b644fb7d?project=1078480825370) と、
同じ SHA の[必須チェック](https://github.com/test-my-team-merge-queue/test/runs/131106980977)が
09:58:04 UTC に成功し、09:58:26 UTC に同じ SHA が main へマージされたことを確認しました。
head の成功だけでなく、Queue の組合せ SHA の成功と main へのマージまで確認済みです。
この README 追記の PR では、ビルド承認、Queue 投入、main へのマージは行いません。

チェックが出ない場合は App のリポジトリ選択・権限、トリガーの有効状態・正規表現・設定ファイルを確認します。
Cloud Build が成功しても Queue が待つ場合は、チェック名・App・報告先 SHA を確認します。
承認待ち、GitHub 側の60分タイムアウト、実行後のテスト失敗は区別してください。

設定はリポジトリ外にもあるため、運用前には最新状態を読み直してください。
Google Cloud CLI と GitHub CLI が利用できる場合の読取り専用確認例です。

```sh
gcloud builds triggers describe merge-queue-test \
  --project=sandbox-hi --region=global --format=json
gh api repos/test-my-team-merge-queue/test/rules/branches/main
COMMIT_SHA=e348d3bf1bfa4502094e52d68c1dfe14a22ac9f8 # 確認したい SHA に置き換える
gh api "repos/test-my-team-merge-queue/test/commits/${COMMIT_SHA}/check-runs"
```

関連する公式手順:

- [GitHub リポジトリの接続（第1世代）](https://docs.cloud.google.com/build/docs/automating-builds/github/connect-repo-github?generation=1st-gen)
- [トリガーの作成・設定](https://docs.cloud.google.com/build/docs/automating-builds/create-manage-triggers)
- [専用サービスアカウントとログ](https://docs.cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts)
- [トリガー管理者の実行権限](https://docs.cloud.google.com/build/docs/cloud-build-service-account#build_triggers)
- [ビルドを承認制にする](https://docs.cloud.google.com/build/docs/securing-builds/gate-builds-on-approval)
- [外部 CI と Merge Queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue#triggering-merge-group-checks-with-third-party-ci-providers)

以下は以前の GitHub Actions 実験の手順です。現在の Cloud Build 検証のために Actions を再有効化する必要はありません。

## 以前の GitHub Actions 実験

当時の CI の必須チェック名は **compatibility**。
`pull_request`、`push`（main）、`merge_group: checks_requested` のすべてで同じジョブを実行します。
checkout の ref を PR の head に固定しないため、キューでは GitHub が作った組み合わせのコミットを検査します。

## 1. この環境を準備する

1. このセットアップ PR の CI 成功を確認し、Draft を解除して main にマージします。
2. リポジトリの Settings で main に適用するブランチ保護または ruleset を設定します。
   - Require a pull request before merging
   - Require status checks to pass: **compatibility**（GitHub Actions）
   - Require merge queue
   - 実験でも bypass は使いません。単独作業で承認者がいない場合は必須レビュー人数を設定しないでください。
3. 設定を有効化します。これは **手動で行う次の操作**です。この PR 自体はリポジトリ設定を変更しません。

初期 PR のマージより先に必須キューを設定すると、main にまだ workflow がないため実験を始めにくくなります。
チェック候補に compatibility がなければ、この PR の Actions 実行完了を先に確認してください。
classic branch protection を使う場合、対象パターンはワイルドカードなしの `main` にします。

## 2. 後で実験 PR を 2 件作る

**このセットアップ PR には、以下の PR 作成・キュー投入・マージは含まれません。**

両方ともセットアップ後の **同じ main コミット**から分岐します。
A を先にマージしてから B を作らないでください。

- PR A: `config/feature_a.txt` だけを `0` → `1` に変更
- PR B: `config/feature_b.txt` だけを `0` → `1` に変更

両方の compatibility が緑になるまで待ちます。
両方を Ready for review にし、通常のマージではなく **Merge when ready / Add to merge queue** から A、B の順で投入します
（ボタン表記は UI により異なります）。

## 3. 観察する

- Actions のイベントが `merge_group` の実行を開きます。
- PR 単体とは異なる、一時ブランチ `gh-readonly-queue/main/...` のコミットが検査されます。
- A が先頭なら A は成功、A と B の組合せは capacity exceeded で失敗します。
- B はキューから外れ、PR のタイムラインに理由が表示されます。A は他の条件も満たせばマージされます。
- A が B の投入前にマージ済みでも、B は最新 main + B で失敗します。表示・順序は処理タイミングによって変わります。
- 二つの merge_group を同時に観察したければ Build concurrency を 2 以上にして続けて投入します。
  **Merge limits はビルドの組合せを指定する設定ではありません。**

確認したい結果は「両方の個別 CI が成功していても、不整合な組合せを main に入れない」ことです。
単に PR の head SHA の CI を再利用してはいけません。

再実験する場合は、マージ済みの 1 を 0 に戻す変更を通常の PR で通し、
main が 0/0 になったことを確認してから新しい 2 ブランチを作ります。force push は不要です。

## 公式ドキュメント

- [Merge Queue の管理・CI・利用条件](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue)
- [merge_group イベント](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#merge_group)

Organization 所有の公開リポジトリは利用対象です。外部 CI の場合は
`gh-readonly-queue/{base_branch}` で始まるブランチの push と、その組合せ SHA へのチェック報告が必要です。
この実験は GitHub Actions のため `merge_group` を使用します。
