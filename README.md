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
