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

（作業時に追記）

## Phase 3: WP系ツールの重複解消

（作業時に追記）

## Phase 4: Next.js 整理

（作業時に追記）
