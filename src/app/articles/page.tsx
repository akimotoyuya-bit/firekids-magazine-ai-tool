import Link from "next/link";
import { getBrandStats } from "@/lib/articles";
import { BRANDS, BRAND_LABELS } from "@/lib/types";

export default function ArticlesPage() {
  const stats = getBrandStats();
  const activeBrands = BRANDS.filter((b) => stats[b].total > 0);

  const totalAll  = activeBrands.reduce((s, b) => s + stats[b].total,   0);
  const totalHtml = activeBrands.reduce((s, b) => s + stats[b].hasHtml, 0);
  const totalX    = activeBrands.reduce((s, b) => s + stats[b].hasXPost, 0);

  return (
    <div>
      {/* ヘッダー */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gradient tracking-tight mb-1.5">
          記事一覧
        </h1>
        <p className="text-sm text-[var(--text-muted)]">
          ブランドを選択して記事を検索・フィルタリングします
        </p>
      </div>

      {/* KPI バー */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        {[
          { label: "総記事数",    value: totalAll,  sub: null },
          { label: "HTML生成済", value: totalHtml,  sub: totalAll > 0 ? `${Math.round(totalHtml / totalAll * 100)}%` : "—" },
          { label: "X投稿あり",  value: totalX,     sub: totalAll > 0 ? `${Math.round(totalX  / totalAll * 100)}%` : "—" },
        ].map(({ label, value, sub }) => (
          <div key={label} className="fk-card p-5">
            <div className="text-3xl font-bold stat-accent">{value}</div>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-sm text-[var(--text-muted)]">{label}</span>
              {sub && <span className="text-xs font-semibold text-[#DC2626]">{sub}</span>}
            </div>
          </div>
        ))}
      </div>

      {/* ブランドカードグリッド */}
      <h2 className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-widest mb-4">
        ブランド別
      </h2>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
        {activeBrands.map((brand) => {
          const s = stats[brand];
          const htmlPct = s.total > 0 ? Math.round(s.hasHtml  / s.total * 100) : 0;
          const xPct    = s.total > 0 ? Math.round(s.hasXPost / s.total * 100) : 0;
          const txtPct  = s.total > 0 ? Math.round(s.hasTxt   / s.total * 100) : 0;
          return (
            <Link
              key={brand}
              href={`/articles/${brand}`}
              className="fk-card fk-card-hover p-5 block"
              aria-label={`${BRAND_LABELS[brand]} の記事一覧へ`}
            >
              <div className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1">
                {brand}
              </div>
              <div className="text-xl font-bold text-[var(--text)] mb-3">
                {BRAND_LABELS[brand]}
              </div>
              <div className="text-2xl font-bold stat-accent mb-3">{s.total}</div>

              {/* プログレスバー 3本 */}
              <div className="space-y-2">
                <ProgressBar label="TXT"  value={s.hasTxt}   total={s.total} pct={txtPct}  color="#16A34A" />
                <ProgressBar label="HTML" value={s.hasHtml}  total={s.total} pct={htmlPct} color="#2563EB" />
                <ProgressBar label="X"    value={s.hasXPost} total={s.total} pct={xPct}    color="#DC2626" />
              </div>
            </Link>
          );
        })}
      </div>

      {activeBrands.length === 0 && (
        <div className="empty-state fk-card">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-[var(--text-muted)]">
            <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
          </svg>
          <p className="text-sm font-medium">記事がまだありません</p>
          <p className="text-xs">生成ツールで記事を作成すると自動的に表示されます</p>
        </div>
      )}
    </div>
  );
}

function ProgressBar({
  label, value, total, pct, color,
}: {
  label: string; value: number; total: number; pct: number; color: string;
}) {
  return (
    <div>
      <div className="flex justify-between items-center mb-0.5">
        <span className="text-[10px] font-semibold text-[var(--text-muted)] uppercase">{label}</span>
        <span className="text-[10px] text-[var(--text-muted)]">{value}/{total} <span className="font-semibold" style={{ color }}>{pct}%</span></span>
      </div>
      <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
    </div>
  );
}
