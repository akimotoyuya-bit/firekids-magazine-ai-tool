import Link from "next/link";
import { notFound } from "next/navigation";
import { getArticleList } from "@/lib/articles";
import { BRANDS, BRAND_LABELS, type Brand } from "@/lib/types";
import ArticleTable from "@/components/ArticleTable";

interface Props {
  params: { brand: string };
}

export default function BrandArticlesPage({ params }: Props) {
  const brand = params.brand.toUpperCase() as Brand;
  if (!BRANDS.includes(brand)) notFound();

  const articles = getArticleList(brand);
  if (articles.length === 0) notFound();

  const hasHtml  = articles.filter((a) => a.hasHtml).length;
  const hasXPost = articles.filter((a) => a.hasXPost).length;
  const posted   = articles.filter((a) => a.isPosted).length;

  // 最終更新日
  const latestDate = articles
    .map((a) => a.updatedAt)
    .filter(Boolean)
    .sort()
    .at(-1);

  return (
    <div>
      {/* パンくず */}
      <nav className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] mb-6" aria-label="パンくずリスト">
        <Link href="/"        className="hover:text-[var(--text)] transition">ホーム</Link>
        <span>/</span>
        <Link href="/articles" className="hover:text-[var(--text)] transition">記事一覧</Link>
        <span>/</span>
        <span className="text-[var(--text)] font-medium">{BRAND_LABELS[brand]}</span>
      </nav>

      {/* ヘッダー */}
      <div className="flex items-start justify-between mb-6 gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gradient tracking-tight mb-1">
            {BRAND_LABELS[brand]}
          </h1>
          <p className="text-sm text-[var(--text-muted)]">
            {articles.length} 件の記事
            {latestDate && (
              <span className="ml-2">
                · 最終更新{" "}
                {new Date(latestDate).toLocaleDateString("ja-JP", {
                  year: "numeric", month: "2-digit", day: "2-digit",
                })}
              </span>
            )}
          </p>
        </div>

        {/* ミニ KPI */}
        <div className="flex gap-3 flex-shrink-0">
          {[
            { label: "HTML", value: hasHtml,  total: articles.length, color: "#2563EB" },
            { label: "X",    value: hasXPost, total: articles.length, color: "#DC2626" },
            { label: "投稿済", value: posted, total: articles.length, color: "#16A34A" },
          ].map(({ label, value, total, color }) => (
            <div key={label} className="fk-card px-4 py-2.5 text-center">
              <div className="text-lg font-bold" style={{ color }}>{value}</div>
              <div className="text-[10px] text-[var(--text-muted)] mt-0.5">
                {label} <span className="font-semibold" style={{ color }}>
                  {total > 0 ? Math.round(value / total * 100) : 0}%
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* テーブル（Client Component） */}
      <ArticleTable articles={articles} brand={brand} />
    </div>
  );
}
