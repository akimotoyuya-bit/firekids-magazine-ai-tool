"use client";

import Link from "next/link";
import { useState, useMemo } from "react";
import type { ValidationResult } from "@/lib/types";
import { BRAND_LABELS } from "@/lib/types";

type StatusFilter = "all" | "error" | "warning" | "clean";

export default function ValidationTable({
  results,
  totalErrors,
  totalWarnings,
  cleanCount,
}: {
  results: ValidationResult[];
  totalErrors: number;
  totalWarnings: number;
  cleanCount: number;
}) {
  const [filter, setFilter] = useState<StatusFilter>("all");

  const filtered = useMemo(() => {
    // デフォルトはエラーの多い順
    const sorted = [...results].sort((a, b) => {
      if (a.errorCount !== b.errorCount) return b.errorCount - a.errorCount;
      return b.warningCount - a.warningCount;
    });

    if (filter === "error")   return sorted.filter((r) => r.errorCount > 0);
    if (filter === "warning") return sorted.filter((r) => r.warningCount > 0 && r.errorCount === 0);
    if (filter === "clean")   return sorted.filter((r) => r.errorCount === 0 && r.warningCount === 0);
    return sorted;
  }, [results, filter]);

  return (
    <>
      {/* ─ サマリーカード（クリックでフィルタ） ─ */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <SummaryCard
          label="エラー"
          value={totalErrors}
          active={filter === "error"}
          colorClass="text-[#DC2626]"
          bgClass="bg-[#FEF2F2]"
          borderColor="rgba(220,38,38,.18)"
          icon="✕"
          onClick={() => setFilter((f) => f === "error" ? "all" : "error")}
        />
        <SummaryCard
          label="警告"
          value={totalWarnings}
          active={filter === "warning"}
          colorClass="text-[#B45309]"
          bgClass="bg-[#FFFBEB]"
          borderColor="rgba(180,83,9,.18)"
          icon="!"
          onClick={() => setFilter((f) => f === "warning" ? "all" : "warning")}
        />
        <SummaryCard
          label="クリーン"
          value={cleanCount}
          active={filter === "clean"}
          colorClass="text-[#16A34A]"
          bgClass="bg-[#F0FDF4]"
          borderColor="rgba(21,128,61,.18)"
          icon="✓"
          onClick={() => setFilter((f) => f === "clean" ? "all" : "clean")}
        />
      </div>

      {/* アクティブフィルター表示 */}
      {filter !== "all" && (
        <div className="flex items-center gap-2 mb-4 text-sm">
          <span className={`badge ${filter === "error" ? "badge-error" : filter === "warning" ? "badge-warning" : "badge-published"}`}>
            {filter === "error" ? "エラーのみ" : filter === "warning" ? "警告のみ" : "クリーンのみ"}
          </span>
          <span className="text-[var(--text-muted)]">{filtered.length} 件</span>
          <button
            onClick={() => setFilter("all")}
            className="text-xs text-[#DC2626] hover:underline ml-1"
          >
            クリア
          </button>
        </div>
      )}

      {/* ─ テーブル ─ */}
      <div className="fk-table-wrap">
        {filtered.length > 0 ? (
          <table className="w-full text-sm">
            <thead className="fk-thead">
              <tr>
                <th className="text-left">ブランド</th>
                <th className="text-left">スラッグ</th>
                <th className="text-center" style={{ width: 80 }}>エラー</th>
                <th className="text-center" style={{ width: 80 }}>警告</th>
                <th className="text-right"  style={{ width: 100 }}>ステータス</th>
                <th style={{ width: 100 }}></th>
              </tr>
            </thead>
            <tbody className="fk-tbody">
              {filtered.map((result) => {
                if (!result) return null;
                const { articleMeta, errorCount, warningCount } = result;
                const ok = errorCount === 0 && warningCount === 0;
                return (
                  <tr
                    key={`${articleMeta.brand}_${articleMeta.filename}`}
                    className={
                      errorCount > 0
                        ? "!bg-[rgba(220,38,38,.03)]"
                        : warningCount > 0
                        ? "!bg-[rgba(245,158,11,.03)]"
                        : ""
                    }
                  >
                    <td className="px-4 py-2.5 text-xs text-[var(--text-muted)]">
                      {BRAND_LABELS[articleMeta.brand]}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-[var(--text-sub)] max-w-[280px] truncate">
                      {articleMeta.number}_{articleMeta.slug}
                    </td>
                    <td className="px-3 py-2.5 text-center">
                      {errorCount > 0 ? (
                        <span className="badge badge-error">{errorCount}</span>
                      ) : (
                        <span className="text-[var(--text-muted)] text-xs">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-center">
                      {warningCount > 0 ? (
                        <span className="badge badge-warning">{warningCount}</span>
                      ) : (
                        <span className="text-[var(--text-muted)] text-xs">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      {ok ? (
                        <span className="badge badge-published">クリーン</span>
                      ) : errorCount > 0 ? (
                        <span className="badge badge-error">要修正</span>
                      ) : (
                        <span className="badge badge-warning">確認推奨</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      {!ok ? (
                        <Link
                          href={`/validation?brand=${articleMeta.brand}&slug=${articleMeta.number}_${articleMeta.slug}`}
                          className="text-xs font-semibold text-[#DC2626] hover:underline inline-flex items-center gap-1"
                        >
                          詳細
                          <svg width="10" height="10" viewBox="0 0 12 12" fill="none" aria-hidden>
                            <path d="M1 1h10v10M11 1L1 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                          </svg>
                        </Link>
                      ) : (
                        <span className="text-xs text-[var(--text-muted)]">OK</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div className="empty-state">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
              <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
            </svg>
            <p className="text-sm font-medium text-[var(--text-sub)]">該当する記事がありません</p>
            <button
              onClick={() => setFilter("all")}
              className="text-xs text-[#DC2626] hover:underline mt-1"
            >
              フィルターをクリア
            </button>
          </div>
        )}
      </div>
    </>
  );
}

function SummaryCard({
  label, value, active, colorClass, bgClass, borderColor, icon, onClick,
}: {
  label: string; value: number; active: boolean;
  colorClass: string; bgClass: string; borderColor: string;
  icon: string; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`fk-card p-5 text-center w-full transition-all ${
        active ? "ring-2 ring-offset-1" : "hover:scale-[1.01]"
      }`}
      style={{
        outline: active ? "2px solid #DC2626" : undefined,
        outlineOffset: active ? "2px" : undefined,
      }}
      aria-pressed={active}
    >
      <div className={`w-8 h-8 rounded-full ${bgClass} flex items-center justify-center mx-auto mb-2`}
           style={{ boxShadow: `0 0 0 1px ${borderColor}` }}>
        <span className={`text-sm font-bold ${colorClass}`}>{icon}</span>
      </div>
      <div className={`text-2xl font-bold ${colorClass}`}>{value}</div>
      <div className="text-xs text-[var(--text-muted)] mt-0.5">{label}</div>
      {active && (
        <div className="text-[10px] text-[#DC2626] font-medium mt-1">絞り込み中 ×</div>
      )}
    </button>
  );
}
