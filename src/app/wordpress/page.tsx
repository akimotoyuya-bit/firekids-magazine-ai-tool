import Link from "next/link";
import BrandFilterTabs from "@/components/BrandFilterTabs";
import DryRunDetail from "@/components/DryRunDetail";
import { getArticleList, getArticleContent, parseNumberSlug } from "@/lib/articles";
import { BRANDS, BRAND_LABELS, type Brand } from "@/lib/types";

interface Props {
  searchParams: { brand?: string; slug?: string };
}

export default function WordPressDryRunPage({ searchParams }: Props) {
  const selectedBrand = searchParams.brand?.toUpperCase() as Brand | undefined;
  const selectedSlug = searchParams.slug;

  // ─ 詳細（dry-run 確認）画面 ─
  if (selectedBrand && selectedSlug && BRANDS.includes(selectedBrand)) {
    const parsed = parseNumberSlug(selectedSlug);
    if (parsed) {
      const content = getArticleContent(selectedBrand, parsed.number, parsed.slug);
      if (content) {
        return <DryRunDetail brand={selectedBrand} slug={selectedSlug} content={content} />;
      }
    }
  }

  // ─ 一覧画面 ─
  const brand    = selectedBrand && BRANDS.includes(selectedBrand) ? selectedBrand : undefined;
  const articles = getArticleList(brand).filter((a) => a.hasHtml || a.hasTxt);

  return (
    <div>
      {/* ヘッダー */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gradient tracking-tight mb-1.5">
          WordPress dry-run
        </h1>
        <p className="text-sm text-[var(--text-muted)]">
          投稿する記事を選択して内容を確認してください
        </p>
      </div>

      {/* ステップインジケータ */}
      <div className="fk-card p-5 mb-6 flex items-center gap-0">
        <Step number={1} label="記事を選択" active done={false} />
        <StepConnector />
        <Step number={2} label="dry-run 確認" active={false} done={false} />
        <StepConnector />
        <Step number={3} label="本番投稿" active={false} done={false} disabled />
      </div>

      {/* インフォバナー */}
      <div className="mb-5 flex items-start gap-3 px-4 py-3 rounded-[10px] text-sm"
           style={{ background: "#EFF6FF", boxShadow: "0 0 0 1px rgba(37,99,235,.15)" }}>
        <svg width="16" height="16" viewBox="0 0 20 20" fill="none" className="text-[#2563EB] mt-0.5 flex-shrink-0" aria-hidden>
          <circle cx="10" cy="10" r="8.5" stroke="currentColor" strokeWidth="1.5"/>
          <path d="M10 9v5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          <circle cx="10" cy="6.5" r="0.75" fill="currentColor"/>
        </svg>
        <p className="text-[#1D4ED8]">
          このページは <strong>dry-run（確認専用）</strong> です。
          ステップ③「本番投稿」は現在準備中です。確認後は別途 WP 管理画面から投稿してください。
        </p>
      </div>

      <BrandFilterTabs basePath="/wordpress" brand={brand} />

      {/* テーブル */}
      <div className="fk-table-wrap">
        {articles.length > 0 ? (
          <table className="w-full text-sm">
            <thead className="fk-thead">
              <tr>
                <th className="text-left">ブランド</th>
                <th className="text-left">スラッグ</th>
                <th className="text-center" style={{ width: 90 }}>TXT</th>
                <th className="text-center" style={{ width: 90 }}>HTML</th>
                <th className="text-right"  style={{ width: 130 }}>アクション</th>
              </tr>
            </thead>
            <tbody className="fk-tbody">
              {articles.map((article) => (
                <tr key={article.filename}>
                  <td className="px-4 py-2.5 text-xs text-[var(--text-muted)]">
                    {BRAND_LABELS[article.brand]}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs text-[var(--text-sub)] max-w-[280px] truncate">
                    {article.number}_{article.slug}
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    {article.hasTxt ? (
                      <span className="badge badge-published">生成済</span>
                    ) : (
                      <span className="badge badge-draft">未生成</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    {article.hasHtml ? (
                      <span className="badge badge-info">生成済</span>
                    ) : (
                      <span className="badge badge-draft">未生成</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Link
                        href={`/wordpress?brand=${article.brand}&slug=${article.number}_${article.slug}`}
                        className="text-xs font-semibold text-[#DC2626] hover:underline inline-flex items-center gap-1"
                      >
                        dry-run 確認
                        <svg width="10" height="10" viewBox="0 0 12 12" fill="none" aria-hidden>
                          <path d="M2 6h8M7 3l3 3-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                      </Link>
                      {/* 本番投稿（準備中） */}
                      <button
                        disabled
                        title="準備中 — dry-run 確認後に実装予定"
                        className="text-xs font-semibold text-[var(--text-muted)] cursor-not-allowed opacity-40 inline-flex items-center gap-1"
                        aria-disabled
                      >
                        本番投稿
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="empty-state">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
              <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
            </svg>
            <p className="text-sm font-medium text-[var(--text-sub)]">記事が見つかりません</p>
            <p className="text-xs text-[var(--text-muted)]">TXTまたはHTMLが生成された記事が表示されます</p>
          </div>
        )}
      </div>
    </div>
  );
}

function Step({ number, label, active, done, disabled }: { number: number; label: string; active: boolean; done: boolean; disabled?: boolean }) {
  return (
    <div className={`flex items-center gap-2.5 flex-1 justify-center ${disabled ? "opacity-40" : ""}`}>
      <div
        className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 transition-all ${
          done    ? "text-white"
          : active ? "text-[#DC2626]"
          : "text-[var(--text-muted)]"
        }`}
        style={{
          background: done    ? "linear-gradient(135deg,#DC2626 0%,#EF4444 100%)"
                    : active  ? "#FEF2F2"
                    : "#F1F5F9",
          boxShadow: done    ? "0 2px 8px rgba(220,38,38,.22)"
                   : active  ? "0 0 0 2px #DC2626"
                   : "none",
        }}
      >
        {done ? "✓" : number}
      </div>
      <div className="text-left">
        <div className={`text-xs font-semibold ${active ? "text-[#DC2626]" : done ? "text-[var(--text)]" : "text-[var(--text-muted)]"}`}>
          ステップ {number}
        </div>
        <div className="text-xs text-[var(--text-muted)]">{label}</div>
      </div>
      {disabled && (
        <span className="ml-1 badge badge-draft text-[10px]">準備中</span>
      )}
    </div>
  );
}

function StepConnector() {
  return <div className="w-10 h-px bg-[rgba(15,23,42,.10)] flex-shrink-0 mx-1" />;
}
