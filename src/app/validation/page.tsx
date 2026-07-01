import Link from "next/link";
import BrandFilterTabs from "@/components/BrandFilterTabs";
import DetailValidation from "@/components/DetailValidation";
import ValidationTable from "@/components/ValidationTable";
import { getArticleList, getArticleContent, parseNumberSlug } from "@/lib/articles";
import { validateArticle } from "@/lib/validation";
import { BRANDS, BRAND_LABELS, type Brand } from "@/lib/types";

interface Props {
  searchParams: { brand?: string; slug?: string };
}

export default function ValidationPage({ searchParams }: Props) {
  const selectedBrand = searchParams.brand?.toUpperCase() as Brand | undefined;
  const selectedSlug = searchParams.slug;

  // ─ 詳細表示 ─
  if (selectedBrand && selectedSlug && BRANDS.includes(selectedBrand)) {
    const parsed = parseNumberSlug(selectedSlug);
    if (parsed) {
      const content = getArticleContent(selectedBrand, parsed.number, parsed.slug);
      if (content) {
        const result = validateArticle(content);
        return <DetailValidation brand={selectedBrand} slug={selectedSlug} result={result} />;
      }
    }
  }

  // ─ 一覧 ─
  const brand    = selectedBrand && BRANDS.includes(selectedBrand) ? selectedBrand : undefined;
  const articles = getArticleList(brand);

  const results = articles
    .map((meta) => {
      const content = getArticleContent(meta.brand, meta.number, meta.slug);
      if (!content) return null;
      return validateArticle(content);
    })
    .filter((r): r is NonNullable<typeof r> => r !== null);

  const totalErrors   = results.reduce((s, r) => s + r.errorCount,   0);
  const totalWarnings = results.reduce((s, r) => s + r.warningCount,  0);
  const cleanCount    = results.filter((r) => r.errorCount === 0 && r.warningCount === 0).length;

  return (
    <div>
      {/* ヘッダー */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gradient tracking-tight mb-1.5">
          ルール検証
        </h1>
        <p className="text-sm text-[var(--text-muted)]">
          FK番号・価格・URL・UTM を一括チェックします。カードをクリックして絞り込み。
        </p>
      </div>

      <BrandFilterTabs basePath="/validation" brand={brand} />

      {/* サマリー + テーブル（Client Component） */}
      <ValidationTable
        results={results}
        totalErrors={totalErrors}
        totalWarnings={totalWarnings}
        cleanCount={cleanCount}
      />
    </div>
  );
}
