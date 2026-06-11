# FirekidsMagazine リファクタリング指示設計書（Cursor用）

このドキュメントは、本リポジトリのリファクタリングをAI（Cursor）に依頼するための指示書です。
**フェーズごとに1チャットで依頼し、フェーズ完了ごとにgit commitしてください。**

---

## 0. 目的とスコープ

- 目的: 外部から見た挙動（UI・UX・API・生成物）を**一切変えずに**、コードの内部構造を改善し、保守性・可読性・AIによる修正精度を高める。
- スコープ外: 新機能追加、デザイン変更、ライブラリのメジャーアップデート、パフォーマンスチューニング。

## 1. 絶対遵守の制約（全フェーズ共通）

1. **挙動を変えない。** Flaskの全ルートのURL・メソッド・リクエスト/レスポンスのJSON形式・ステータスコードを維持する。
2. **生成物のフォーマットを変えない。** 記事HTML（Gutenbergブロック形式）、保存ファイルの命名規則（`014_article_xxx.txt` 等）、S3キー構造はバイト単位の互換性を保つ。
3. **Next.js側のレンダリング結果を変えない。** ページのHTML出力・ルーティング（`/articles/[brand]/[slug]` 等）を維持する。
4. **依存を増やさない。** 新規パッケージ追加は原則禁止（テスト用の pytest を除く）。
5. **`.env` の読み込み順序・環境変数名を変えない。** デプロイ（App Runner / Vercel / Lambda / GAS）への影響を出さない。
6. **1コミット = 1つの論理的変更。** リネームと内容変更を同一コミットに混ぜない。
7. 自信がない変更・仕様判断が必要な変更は実施せず、`REFACTORING_NOTES.md` に「要確認」として記録して先へ進む。

## 2. 現状のコードマップ（調査済み）

| 領域 | パス | 規模 | 主な問題 |
|---|---|---|---|
| 記事生成Webアプリ (Flask) | `scripts/article_generator/app.py` | **2,200行** | ゴッドファイル。ルーティング・Bedrock呼び出し・Embedding・被り判定・プロンプト構築・MD→HTML変換・S3ドラフト管理・ジョブ管理が1ファイルに混在 |
| WP投稿ツール (Flask) | `scripts/wp_uploader_local/app.py` | 544行 | WordPress APIクライアント処理とルートが混在 |
| WP非公開ツール (Flask) | `scripts/wp_unpublisher_local/app.py` | - | uploaderとWP認証・APIアクセス処理が重複している可能性 |
| 記事ビューア (Next.js 14) | `src/` | 小規模 | `validation/page.tsx`(301行)・`wordpress/page.tsx`(281行) がやや肥大 |
| HTML一括生成 | `generate_html_batch.py`(ルート直下352行) / `scripts/generate_seiko_html.py`(693行) | - | 役割が重複している疑い。ルート直下にスクリプトが置かれている |
| GAS | `gas/firekids-inquiry-pipeline/Code.gs`(428行) / `Code.v2.gs`(1,598行) | - | 新旧2バージョンが併存 |
| デプロイ | `deploy/`, `infra/`, `lambda/` | 小規模 | 対象外（触らない） |
| その他 | `commit_msg.txt` 等のゴミファイル | - | 削除候補 |

## 3. フェーズ計画

### Phase 0: 安全網の構築（リファクタリング前に必須）

リファクタリングは「壊れていないことを確認できる状態」を作ってから行う。

- [ ] `npm run build` と `npm run lint` が現状で通ることを確認し、結果を記録する。
- [ ] `scripts/article_generator/app.py` の全ルート一覧（URL・メソッド）を抽出し、`tests/route_inventory.md` として保存する（リファクタ後の照合用）。
- [ ] 純粋関数（外部API・I/Oに依存しない関数）に対する最小限のpytestを作成する。対象: `title_to_slug` / `markdown_to_wp_html` / `strip_tags` / `extract_h2_sections` / `cosine` / `check_ngram_overlap` / `src/lib/articles.ts` の `parseFilename` 相当ロジック。**現状の出力をそのまま正解とするスナップショットテスト**でよい（仕様の正しさは問わない）。
- [ ] テストを `tests/` 配下に置き、`pytest` が全件パスすることを確認してコミット。

**完了条件: pytest グリーン + next build 成功 + ルート一覧が保存されている。**

### Phase 1: 低リスクな整理（削除・移動のみ、ロジック変更なし）

- [ ] `commit_msg.txt` 等、明らかな一時ファイルを削除する（`.gitignore` への追記も検討）。
- [ ] `generate_html_batch.py`（ルート直下）と `scripts/generate_seiko_html.py` の差分を分析し、重複していれば共通部分の特定結果を `REFACTORING_NOTES.md` に記録する。**この段階では統合しない。**
- [ ] `gas/` の `Code.gs` と `Code.v2.gs` について、v2が現行版であることをコメント・履歴から確認できれば、旧版を `gas/firekids-inquiry-pipeline/archive/` へ移動する。確認できなければ触らずノートに記録。
- [ ] 各Pythonファイルの未使用import・到達不能コード・コメントアウトされた死にコードを削除する（ツール: `ruff check --select F401,F841`）。

**完了条件: Phase 0 のテストが全てパス。git diff が削除・移動のみであること。**

### Phase 2: `scripts/article_generator/app.py`（2,200行）の分割 ★本丸

責務ごとにモジュール分割する。**関数の中身は変更せず、移動とimport調整のみ**を原則とする。

提案する分割構成（同ディレクトリ内に作成）:

```
scripts/article_generator/
├── app.py              ← Flaskルート定義のみ残す（目標: 400行以下）
├── auth.py             ← _require_login
├── bedrock_client.py   ← get_bedrock_client, invoke_claude, invoke_claude_stream
├── embeddings.py       ← bedrock_embed, cosine, reset_embed_state, embedding_degraded
├── overlap.py          ← check_overlap, check_ngram_overlap, sample_past_titles
├── wp_scanner.py       ← scan_wordpress_posts, extract_h2_sections, strip_tags,
│                          ensure_cache_fresh, _run_scan_locked, _parse_modified
├── article_pipeline.py ← propose_structure, revise_structure, build_article_prompt,
│                          generate_article, load_rules_context
├── formatting.py       ← markdown_to_wp_html, title_to_slug
├── storage.py          ← save_article, _next_article_number, S3ドラフト系
│                          (_s3_client_simple, _restore_drafts_from_s3)
└── jobs.py             ← ジョブ管理 (_cleanup_jobs とジョブ辞書)
```

注意事項:

- 既存の `sys.path.insert` ハック（本番のgunicorn/wsgi読み込み互換のためのもの）は**そのまま維持**する。ファイル冒頭のコメントにある通り、これを壊すと本番デプロイが silent fail する。
- モジュール間の循環import が発生する場合は、共有状態（ジョブ辞書・キャッシュ）を `state.py` 等に切り出して解決する。
- 1モジュール切り出すごとにアプリを起動（`python app.py`）して全ルートが応答することを確認し、コミットする。**一度に全部やらない。**

**完了条件: pytest グリーン + ルート一覧が Phase 0 の記録と完全一致 + `python app.py` でローカル起動し主要ルート（`/`, `/health`, `/inventory-items`, `/drafts`）が応答する。**

### Phase 3: WP系ツールの重複解消

- [ ] `wp_uploader_local/app.py` と `wp_unpublisher_local/app.py` で重複しているWordPress REST API処理（認証、`get_auth`、タグ/カテゴリ取得など）を `scripts/wp_common/` に抽出し、両アプリから参照する。
- [ ] `.env` の読み込みパスは変更しない。
- [ ] 両アプリをローカル起動し、`/ping` `/health` `/wp-config` が従来通り応答することを確認。

### Phase 4: Next.js (`src/`) の整理

- [ ] `src/app/validation/page.tsx`（301行）と `src/app/wordpress/page.tsx`（281行）から、表示用コンポーネント・ロジックを `src/components/` / `src/lib/` へ抽出する。
- [ ] `src/lib/articles.ts` のファイル名パース処理に型を明確化し、マジックストリング（拡張子・プレフィックス）を定数化する。
- [ ] `npm run build` の出力（生成されるルート一覧）がリファクタ前と一致することを確認。

### Phase 5: 最終検証

- [ ] pytest 全件パス。
- [ ] `npm run build` 成功、生成ルート一覧が初回記録と一致。
- [ ] `ruff check` / `npm run lint` で新規エラーゼロ。
- [ ] 全Flaskアプリのローカル起動確認。
- [ ] `REFACTORING_NOTES.md` に「要確認」として残した項目の一覧を人間がレビューする。

## 4. Cursorへの依頼テンプレート

各フェーズ開始時に以下を貼り付けて使う:

> `REFACTORING_PLAN.md` の Phase N を実施してください。
> セクション1「絶対遵守の制約」を必ず守ること。
> 完了条件を満たしたことを確認してから、変更内容の要約と「要確認」事項を報告してください。
> 確信が持てない変更はスキップして `REFACTORING_NOTES.md` に記録してください。

## 5. やってはいけないことリスト（再掲・Cursor向け）

- プロンプト文字列（`build_article_prompt` 等の中身）の「改善」 — 生成記事の品質が変わるため禁止
- 閾値（0.88 / 0.86 / n-gram n=8 等）の変更
- 関数の挙動を変える「ついでの修正」（バグに見えても挙動を保存し、ノートに記録）
- `.env` / デプロイ設定 / `infra/` / `lambda/` / `deploy/` への変更
- ファイル命名規則・ディレクトリ構造（`articles/`, `x_posts/` 等のデータディレクトリ）の変更
