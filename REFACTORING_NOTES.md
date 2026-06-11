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

（作業時に追記）

## Phase 2: app.py 分割

（作業時に追記）

## Phase 3: WP系ツールの重複解消

（作業時に追記）

## Phase 4: Next.js 整理

（作業時に追記）
