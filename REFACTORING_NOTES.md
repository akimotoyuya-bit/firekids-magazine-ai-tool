# リファクタリング作業ノート

`REFACTORING_PLAN.md` に基づく作業の記録。「要確認」事項は人間がレビューすること。

## Phase 0: 安全網の構築

- `npm run build`: **成功**（22 ページ生成。ルート: `/`, `/_not-found`, `/articles`, `/articles/[brand]`, `/articles/[brand]/[slug]`, `/validation`, `/wordpress`）
- `npm run lint`: **実行不可（要確認）** — ESLint が未設定で対話プロンプトが出る状態。`.eslintrc` が存在しないため `next lint` が初期設定を要求する。設定追加は挙動変更にあたるため Phase 0 ではスキップ。
- ルート一覧: `tests/route_inventory.md` に 19 ルートを記録。
- pytest: `tests/test_pure_functions.py` 12 件グリーン。
  - 対象: `title_to_slug` / `markdown_to_wp_html` / `strip_tags` / `extract_h2_sections` / `cosine` / `check_ngram_overlap`
  - スナップショット値は `tests/_snapshots.json`（現状の出力を正解とする）。
  - `check_ngram_overlap` は `_prioritized_cached_records` を monkeypatch して純粋部分のみ検証。
- **要確認**: `src/lib/articles.ts` の `parseFilename` 相当ロジックは TypeScript のため pytest 対象外とした。JS テストランナー（vitest 等）の導入は「依存を増やさない」制約に抵触するためスキップ。

## Phase 1: 低リスクな整理

- `commit_msg.txt` を削除し `.gitignore` に追記（デプロイ作業時の一時ファイル）。
- **GAS（要確認）**: `Code.v2.gs` ヘッダーに「v1のCode.gsと共存させる（本ファイルを追加するだけ）」と明記されており、v2 は v1 を**置換しない設計**。よって `Code.gs` の archive 移動は実施しない。
- **HTML一括生成の重複分析**: `generate_html_batch.py`（ルート直下・352行・多ブランド対応）と `scripts/generate_seiko_html.py`（693行・SEIKO特化・JSON-LD/メタコメント付き）は、`make_slug` / `extract_title` / インライン MD→HTML 変換 / テーブル変換が概念的に重複。ただし実装・出力フォーマットは異なる（seiko 版は meta コメント + JSON-LD を出力）。統合する場合は出力のバイト互換を壊すため、**統合せず現状維持を推奨**。
- ruff `F401`（未使用 import）7 件を自動修正:
  - `scripts/article_generator/app.py`: `flask.send_from_directory`
  - `scripts/article_generator/inventory.py`: `typing.Optional`
  - `scripts/make_x_image.py`: `json`
  - `scripts/review_diff.py`: `os`
  - `scripts/review_generate.py`: `os`
  - `scripts/wp_unpublisher_local/app.py`: `re`
  - `scripts/wp_uploader_local/app.py`: `json`
- ruff `F841` 1 件: `scripts/generate_seiko_html.py` の `in_faq`（代入のみで未読の死に変数）を削除。
  - **要確認（潜在バグ記録）**: `in_faq` は FAQ セクション判定フラグとして用意されたが一度も参照されていない。FAQ 抽出が「`---` でセクション終了」を考慮しない動作のまま稼働している。挙動は従来と同一（変数削除は無影響）。

## Phase 2: app.py 分割

`scripts/article_generator/app.py`（2,260行）を計画どおり責務別に分割。関数本体は行単位でそのままコピーし、変更はヘッダー（docstring・import）のみ。

| モジュール | 内容 | 行数 |
|---|---|---|
| `app.py` | Flask ルート定義のみ | 762 |
| `state.py` | 定数（閾値・BRANDS等）・.env読み込み・ロギング・`_brand_records`/`_prioritized_cached_records` | 141 |
| `auth.py` | `_require_login`（app.py が `app.before_request()` で登録） | 15 |
| `jobs.py` | `JOBS` / `_JOB_LOCK` / `_cleanup_jobs` | 22 |
| `bedrock_client.py` | `get_bedrock_client` / `invoke_claude` / `invoke_claude_stream` | 74 |
| `embeddings.py` | `bedrock_embed` / `cosine` / embed 劣化状態 | 55 |
| `formatting.py` | `title_to_slug` / `markdown_to_wp_html` | 118 |
| `wp_scanner.py` | `scan_wordpress_posts` / `ensure_cache_fresh` / `strip_tags` / `extract_h2_sections` / `_SCAN_STATE` | 292 |
| `overlap.py` | `check_overlap` / `check_ngram_overlap` / `sample_past_titles` | 137 |
| `article_pipeline.py` | `propose_structure` / `revise_structure` / `build_article_prompt` / `generate_article` / `load_rules_context` | 560 |
| `storage.py` | `save_article` / `_s3_client_simple` / `_restore_drafts_from_s3` / posts_log 永続化 | 115 |

計画からの軽微な逸脱（理由付き）:
- `_parse_modified` は計画では wp_scanner 行きだったが、`_prioritized_cached_records`（state）と wp_scanner の両方が使うため **state.py に配置**（循環 import 回避）。
- `state.py` は計画の「共有状態は state.py 等に切り出す」に基づき、定数 + .env 読み込み + 共有レコードヘルパーを集約。
- app.py は 762 行（目標 400 行以下に未達）。残りは全てルート関数本体（save_draft / drafts / patch_categories 等が大きい）。ルート本体のさらなる分離は挙動リスクがあるため見送り。
- モジュールごとの個別コミットではなく、分割全体を 1 コミットとした（行範囲ベースの機械的コピーで一括生成し、分割後に pytest 16件 + ルート一覧照合 + `python app.py` 起動 + 認証付きスモーク（/, /ping, /inventory-items, /drafts, /scan-status, /posts-log 全て200）で検証済みのため）。

互換性の保全:
- `.env` 読み込み順序は維持（vector_store / inventory import → dotenv → 定数読み込み。state.py の import 時に分割前と同タイミングで実行）。
- `sys.path.insert` ハックは app.py に維持（`deploy/wsgi.py` の `from article_generator.app import app` 経路を検証済み）。
- `embed_all.py` が `from app import ArticleVectorStore, EMBED_MODEL_ID, bedrock_embed, extract_h2_sections, strip_tags` するため、app.py に再エクスポートを維持。
- テストの monkeypatch 対象を `app._prioritized_cached_records` → `overlap._prioritized_cached_records` に変更（実体の移動に伴う調整。挙動は不変）。
- ルート一覧照合テスト（`tests/test_routes.py`）を追加し Phase 0 記録と完全一致を機械検証。

## Phase 3: WP系ツールの重複解消

- `scripts/wp_common/wp_client.py` を新設し、WordPress REST API 共通処理を抽出:
  - `WP_HEADERS`（XSERVER WAF 対策のブラウザ UA）
  - `build_auth`（Application Password のスペース除去）
  - `fetch_me`（/users/me 認証確認。headers/timeout をパラメータ化し各アプリの従来リクエスト形状を維持）
  - `get_or_create_tag` / `get_category_id_by_name` / `find_user_id_by_keyword` / `upload_media_from_url`（base_url/auth/headers をパラメータ化）
- `wp_uploader_local/app.py`: 上記を import し、既存関数は同シグネチャのラッパーとして残した（ルート側のコードは無変更）。
- `wp_unpublisher_local/app.py`: `/health` の users/me 呼び出しを `fetch_me` に置換（timeout=10・ヘッダー無しの従来形状を維持）。
- 両アプリに `sys.path.insert(0, scripts/)` を追加（ローカル実行と wsgi パッケージ読み込みの両対応。article_generator と同方式）。
- `.env` の読み込みパス・順序は両アプリとも無変更。
- 動作確認: 両アプリの全ルート維持を確認。uploader をローカル起動し `/ping`（200, pong:true）`/health`（200, ok:true, writer_user_found:true ← 実WPへの認証・ユーザー検索成功）`/wp-config`（200）を確認。unpublisher も `/health` が ok:true。
- **要確認（潜在的な非一貫性の記録）**: unpublisher の `auth()` は Application Password のスペースを除去しない（uploader は除去する）。現在の .env のパスワードにスペースが無いため動作している。挙動保存のため統一はしていない。

## Phase 4: Next.js 整理

- `src/components/` へ表示用コンポーネントを抽出（JSX は無変更のまま移動）:
  - `BrandFilterTabs.tsx` — validation / wordpress 両ページで重複していたブランドフィルタータブを共通化（`basePath` プロップで遷移先を切替）
  - `DetailValidation.tsx` — validation ページの詳細検証表示（`TYPE_LABELS` 含む）
  - `DryRunDetail.tsx` — wordpress ページの dry-run 詳細表示（`InfoCard` 含む）
- `src/lib/articles.ts`:
  - `ParsedFilename` インターフェースを export し `parseFilename` の戻り値型を明確化
  - マジックストリングを定数化: `ARTICLE_PREFIX` / `X_POST_PREFIX` / `KNOWN_EXTENSIONS` / `POSTED_DIR_NAME`（正規表現・パス構築は定数から組み立て。パターン自体は従来と同一）
  - `parseNumberSlug()` を新設（両ページで重複していた `^(\d+)_(.+)$` パースを共通化）
- 検証: `npm run build` 成功。生成ルート一覧（7 ルート + SSG 15 ブランドパス）・チャンクサイズとも Phase 0 の記録と完全一致。
- コンポーネントの型は `ReturnType<typeof validateArticle>` → `ValidationResult`、`ReturnType<typeof getArticleContent>` → `ArticleContent | null` に明示化（同一型のエイリアス解決のみ）。
