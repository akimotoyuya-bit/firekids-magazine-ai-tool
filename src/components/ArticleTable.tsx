"use client";

import Link from "next/link";
import { useState, useMemo } from "react";
import type { ArticleMeta } from "@/lib/types";
import { BRAND_LABELS } from "@/lib/types";

const PAGE_SIZE = 25;

type SortKey = "number" | "updatedAt" | "slug";
type SortDir = "asc" | "desc";
type StatusFilter = "all" | "published" | "draft";

export default function ArticleTable({
  articles,
  brand,
}: {
  articles: ArticleMeta[];
  brand: string;
}) {
  const [query,     setQuery]     = useState("");
  const [status,    setStatus]    = useState<StatusFilter>("all");
  const [sortKey,   setSortKey]   = useState<SortKey>("number");
  const [sortDir,   setSortDir]   = useState<SortDir>("asc");
  const [page,      setPage]      = useState(1);

  /* ─ フィルタ + 検索 ─ */
  const filtered = useMemo(() => {
    let list = articles;

    if (status === "published") list = list.filter((a) => a.isPosted);
    if (status === "draft")     list = list.filter((a) => !a.isPosted);

    if (query.trim()) {
      const q = query.trim().toLowerCase();
      list = list.filter(
        (a) =>
          a.slug.toLowerCase().includes(q) ||
          a.number.includes(q) ||
          `${a.number}_${a.slug}`.toLowerCase().includes(q)
      );
    }
    return list;
  }, [articles, query, status]);

  /* ─ 並べ替え ─ */
  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      let va: string | number, vb: string | number;
      if (sortKey === "number") { va = Number(a.number); vb = Number(b.number); }
      else if (sortKey === "updatedAt") { va = a.updatedAt ?? ""; vb = b.updatedAt ?? ""; }
      else { va = a.slug; vb = b.slug; }
      if (va < vb) return sortDir === "asc" ? -1 : 1;
      if (va > vb) return sortDir === "asc" ?  1 : -1;
      return 0;
    });
  }, [filtered, sortKey, sortDir]);

  /* ─ ページネーション ─ */
  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const paged      = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir("asc"); }
    setPage(1);
  }

  function handleQuery(v: string) { setQuery(v); setPage(1); }
  function handleStatus(v: StatusFilter) { setStatus(v); setPage(1); }

  const sortIcon = (key: SortKey) => {
    if (sortKey !== key) return <span className="opacity-20 ml-1">↕</span>;
    return <span className="ml-1 text-[#DC2626]">{sortDir === "asc" ? "↑" : "↓"}</span>;
  };

  return (
    <div>
      {/* ─ ツールバー ─ */}
      <div className="flex flex-col sm:flex-row gap-3 mb-5">
        {/* 検索 */}
        <div className="fk-search flex-1 max-w-sm">
          <svg width="15" height="15" viewBox="0 0 20 20" fill="none" className="text-[var(--text-muted)] flex-shrink-0" aria-hidden>
            <circle cx="8.5" cy="8.5" r="5.75" stroke="currentColor" strokeWidth="1.6"/>
            <path d="M13 13L17 17" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
          </svg>
          <input
            type="search"
            placeholder="タイトル・スラッグを検索…"
            value={query}
            onChange={(e) => handleQuery(e.target.value)}
            aria-label="記事を検索"
          />
          {query && (
            <button
              onClick={() => handleQuery("")}
              className="text-[var(--text-muted)] hover:text-[var(--text)] flex-shrink-0"
              aria-label="検索をクリア"
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M1 1l12 12M13 1L1 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
            </button>
          )}
        </div>

        {/* ステータス絞り込み */}
        <div className="flex gap-2 flex-shrink-0" role="group" aria-label="ステータス絞り込み">
          {(["all", "published", "draft"] as StatusFilter[]).map((s) => (
            <button
              key={s}
              onClick={() => handleStatus(s)}
              className={`fk-chip text-xs ${status === s ? "fk-chip-active" : ""}`}
            >
              {s === "all" ? "すべて" : s === "published" ? "投稿済" : "下書き"}
            </button>
          ))}
        </div>

        {/* 件数 */}
        <div className="text-sm text-[var(--text-muted)] self-center ml-auto flex-shrink-0">
          {filtered.length} 件
        </div>
      </div>

      {/* ─ テーブル ─ */}
      <div className="fk-table-wrap">
        {paged.length > 0 ? (
          <table className="w-full text-sm">
            <thead className="fk-thead">
              <tr>
                <th className="text-left" style={{ width: 56 }}>
                  <button onClick={() => toggleSort("number")} className="flex items-center hover:text-[var(--text)] transition">
                    # {sortIcon("number")}
                  </button>
                </th>
                <th className="text-left">
                  <button onClick={() => toggleSort("slug")} className="flex items-center hover:text-[var(--text)] transition">
                    スラッグ {sortIcon("slug")}
                  </button>
                </th>
                <th className="text-center" style={{ width: 80 }}>TXT</th>
                <th className="text-center" style={{ width: 80 }}>HTML</th>
                <th className="text-center" style={{ width: 80 }}>X投稿</th>
                <th className="text-center" style={{ width: 100 }}>ステータス</th>
                <th className="text-right" style={{ width: 110 }}>
                  <button onClick={() => toggleSort("updatedAt")} className="flex items-center ml-auto hover:text-[var(--text)] transition">
                    更新日 {sortIcon("updatedAt")}
                  </button>
                </th>
                <th style={{ width: 80 }}></th>
              </tr>
            </thead>
            <tbody className="fk-tbody">
              {paged.map((article) => (
                <tr key={article.filename}>
                  <td className="px-4 py-2.5 text-[var(--text-muted)] font-mono text-xs">
                    {article.number}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs text-[var(--text-sub)] max-w-[260px] truncate">
                    {article.slug}
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    <FileStatusPill ok={article.hasTxt} />
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    <FileStatusPill ok={article.hasHtml} />
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    <FileStatusPill ok={article.hasXPost} />
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    {article.isPosted ? (
                      <span className="badge badge-published">投稿済</span>
                    ) : (
                      <span className="badge badge-draft">下書き</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right text-xs text-[var(--text-muted)]">
                    {article.updatedAt
                      ? new Date(article.updatedAt).toLocaleDateString("ja-JP", { year:"numeric",month:"2-digit",day:"2-digit" })
                      : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <Link
                      href={`/articles/${brand}/${article.number}_${article.slug}`}
                      className="text-xs font-medium text-[#DC2626] hover:underline inline-flex items-center gap-1"
                      aria-label={`${article.slug} を開く（別タブ）`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      開く
                      <svg width="10" height="10" viewBox="0 0 12 12" fill="none" aria-hidden>
                        <path d="M2 2h8v8M10 2L2 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="empty-state">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
              <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
            </svg>
            <p className="text-sm font-medium text-[var(--text-sub)]">該当する記事がありません</p>
            {(query || status !== "all") && (
              <button
                onClick={() => { setQuery(""); setStatus("all"); setPage(1); }}
                className="text-xs text-[#DC2626] hover:underline mt-1"
              >
                検索条件をクリア
              </button>
            )}
          </div>
        )}
      </div>

      {/* ─ ページネーション ─ */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <p className="text-xs text-[var(--text-muted)]">
            {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, sorted.length)} / {sorted.length} 件
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="fk-chip text-xs disabled:opacity-30"
              aria-label="前のページ"
            >
              ← 前
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .filter((p) => p === 1 || p === totalPages || Math.abs(p - page) <= 1)
              .reduce<(number | "…")[]>((acc, p, i, arr) => {
                if (i > 0 && (p as number) - (arr[i - 1] as number) > 1) acc.push("…");
                acc.push(p);
                return acc;
              }, [])
              .map((p, i) =>
                p === "…" ? (
                  <span key={`ellipsis-${i}`} className="px-2 text-[var(--text-muted)] self-center text-xs">…</span>
                ) : (
                  <button
                    key={p}
                    onClick={() => setPage(p as number)}
                    className={`fk-chip text-xs ${page === p ? "fk-chip-active" : ""}`}
                    aria-label={`${p} ページ目`}
                    aria-current={page === p ? "page" : undefined}
                  >
                    {p}
                  </button>
                )
              )}
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="fk-chip text-xs disabled:opacity-30"
              aria-label="次のページ"
            >
              次 →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function FileStatusPill({ ok }: { ok: boolean }) {
  return ok ? (
    <span className="badge badge-published">生成済</span>
  ) : (
    <span className="badge badge-draft" style={{ color: "#CBD5E1", boxShadow: "none" }}>—</span>
  );
}
