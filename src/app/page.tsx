import Link from "next/link";
import { getBrandStats, getArticleList } from "@/lib/articles";
import { BRANDS, BRAND_LABELS } from "@/lib/types";

const GENERATOR_URL =
  process.env.NEXT_PUBLIC_GENERATOR_URL ??
  "https://s5d6hqidtk.us-east-1.awsapprunner.com/generator/";

export default function HomePage() {
  const stats = getBrandStats();
  const activeBrands = BRANDS.filter((b) => stats[b].total > 0);

  const totalArticles = activeBrands.reduce((s, b) => s + stats[b].total,   0);
  const totalHtml     = activeBrands.reduce((s, b) => s + stats[b].hasHtml, 0);
  const totalXPost    = activeBrands.reduce((s, b) => s + stats[b].hasXPost, 0);

  const htmlPct  = totalArticles > 0 ? Math.round(totalHtml  / totalArticles * 100) : 0;
  const xPct     = totalArticles > 0 ? Math.round(totalXPost / totalArticles * 100) : 0;

  // 最終更新日を全記事から集計
  const allArticles  = getArticleList();
  const latestUpdate = allArticles
    .map((a) => a.updatedAt)
    .filter(Boolean)
    .sort()
    .at(-1);

  const latestDateStr = latestUpdate
    ? new Date(latestUpdate).toLocaleDateString("ja-JP", { year: "numeric", month: "2-digit", day: "2-digit" })
    : null;

  return (
    <div>
      {/* ─ ページヘッダー ─ */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gradient mb-2 tracking-tight">
          FIRE KIDS Magazine 管理ツール
        </h1>
        <div className="flex items-center gap-3 flex-wrap">
          <p className="text-sm text-[var(--text-muted)]">
            記事ブラウザ・ルール検証・HTML/X変換補助・WordPress投稿 dry-run
          </p>
          {/* 稼働中バッジ */}
          <div className="flex items-center gap-1.5 text-xs font-medium text-[#16A34A] bg-[#F0FDF4] px-3 py-1 rounded-full" style={{ boxShadow: "0 0 0 1px rgba(21,128,61,.15)" }}>
            <span className="w-1.5 h-1.5 rounded-full bg-[#16A34A] inline-block animate-pulse" />
            稼働中
            {latestDateStr && <span className="text-[#94A3B8] font-normal ml-1">· 最終更新 {latestDateStr}</span>}
          </div>
        </div>
      </div>

      {/* ─ KPI カード ─ */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <KpiCard label="総記事数" value={totalArticles} sub={null} color={undefined} />
        <KpiCard label="HTML生成済み" value={totalHtml}  sub={`${htmlPct}%`} color="#2563EB" />
        <KpiCard label="X投稿あり"    value={totalXPost} sub={`${xPct}%`}    color="#DC2626" />
      </div>

      {/* ─ 記事生成CTA ─ */}
      <a
        href={GENERATOR_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="fk-card fk-card-hover block p-6 mb-6 relative overflow-hidden"
        aria-label="記事生成ツールを開く（別ウィンドウ）"
      >
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: "linear-gradient(110deg, rgba(220,38,38,.06) 0%, rgba(239,68,68,.03) 50%, transparent 100%)",
          }}
        />
        <div className="relative flex items-center gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-bold text-lg text-[var(--text)]">記事を生成する</span>
              <span className="badge badge-info">AWS Bedrock</span>
            </div>
            <p className="text-sm text-[var(--text-muted)]">
              テーマを入力してAIでSEO記事を生成・保存します（別ウィンドウで開きます）
            </p>
          </div>
          <span className="text-[#DC2626] font-semibold text-sm whitespace-nowrap flex items-center gap-1">
            生成ツールを開く
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
              <path d="M2 2h10v10M12 2L2 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </span>
        </div>
      </a>

      {/* ─ クイックアクション ─ */}
      <div className="grid grid-cols-3 gap-4 mb-10">
        <QuickLink href="/articles"   title="記事一覧"   desc="ブランド別に記事を検索・フィルタリング" icon="doc" />
        <QuickLink href="/validation" title="ルール検証" desc="FK番号・価格・URL・UTMを一括チェック"    icon="check" />
        <QuickLink href="/wordpress"  title="WP dry-run" desc="WordPress投稿前の内容確認"              icon="upload" />
      </div>

      {/* ─ ブランド別概要 ─ */}
      <h2 className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-widest mb-3">
        ブランド別概要
      </h2>
      <div className="fk-table-wrap">
        <table className="w-full text-sm">
          <thead className="fk-thead">
            <tr>
              <th className="text-left">ブランド</th>
              <th className="text-right" style={{ width: 64 }}>記事</th>
              <th className="text-right" style={{ width: 64 }}>TXT</th>
              <th className="text-right" style={{ width: 80 }}>HTML</th>
              <th className="text-right" style={{ width: 80 }}>X投稿</th>
              <th style={{ width: 64 }}></th>
            </tr>
          </thead>
          <tbody className="fk-tbody">
            {activeBrands.map((brand) => {
              const s = stats[brand];
              return (
                <tr key={brand}>
                  <td className="px-4 py-2.5 font-medium text-[var(--text)]">
                    {BRAND_LABELS[brand]}
                    <span className="ml-2 text-[10px] text-[var(--text-muted)] font-normal">{brand}</span>
                  </td>
                  <td className="px-4 py-2.5 text-right font-medium">{s.total}</td>
                  <td className="px-4 py-2.5 text-right text-[#16A34A] font-medium">{s.hasTxt}</td>
                  <td className="px-4 py-2.5 text-right">
                    <span className="font-medium text-[#2563EB]">{s.hasHtml}</span>
                    {s.total > 0 && (
                      <span className="text-[10px] text-[var(--text-muted)] ml-1">
                        {Math.round(s.hasHtml / s.total * 100)}%
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <span className="font-medium text-[#DC2626]">{s.hasXPost}</span>
                    {s.total > 0 && (
                      <span className="text-[10px] text-[var(--text-muted)] ml-1">
                        {Math.round(s.hasXPost / s.total * 100)}%
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <Link
                      href={`/articles/${brand}`}
                      className="text-xs font-semibold text-[#DC2626] hover:underline"
                    >
                      一覧 →
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {activeBrands.length === 0 && (
          <div className="empty-state">
            <p className="text-sm">記事がまだありません</p>
          </div>
        )}
      </div>
    </div>
  );
}

function KpiCard({ label, value, sub, color }: { label: string; value: number; sub: string | null; color?: string }) {
  return (
    <div className="fk-card p-5">
      <div className="text-3xl font-bold stat-accent">{value}</div>
      <div className="flex items-baseline gap-2 mt-1">
        <span className="text-sm text-[var(--text-muted)]">{label}</span>
        {sub && <span className="text-xs font-bold" style={{ color: color ?? "#DC2626" }}>{sub}</span>}
      </div>
    </div>
  );
}

function QuickLink({ href, title, desc, icon }: { href: string; title: string; desc: string; icon: "doc" | "check" | "upload" }) {
  const icons: Record<typeof icon, React.ReactNode> = {
    doc: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-[#DC2626]">
        <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
      </svg>
    ),
    check: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-[#DC2626]">
        <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
      </svg>
    ),
    upload: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-[#DC2626]">
        <path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/>
      </svg>
    ),
  };
  return (
    <Link href={href} className="fk-card fk-card-hover p-5 block">
      <div className="mb-3">{icons[icon]}</div>
      <div className="font-semibold text-[var(--text)] mb-1">{title}</div>
      <div className="text-xs text-[var(--text-muted)] leading-relaxed">{desc}</div>
    </Link>
  );
}
