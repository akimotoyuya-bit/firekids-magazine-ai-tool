import Link from "next/link";
import BrandFilterTabs from "@/components/BrandFilterTabs";
import DetailValidation from "@/components/DetailValidation";
import { getArticleList, getArticleContent, parseNumberSlug } from "@/lib/articles";
import { validateArticle } from "@/lib/validation";
import { BRANDS, BRAND_LABELS, type Brand } from "@/lib/types";

interface Props {
  searchParams: { brand?: string; slug?: string };
}

export default function ValidationPage({ searchParams }: Props) {
  const selectedBrand = searchParams.brand?.toUpperCase() as Brand | undefined;
  const selectedSlug = searchParams.slug;

  // 特定の記事の詳細検証
  if (selectedBrand && selectedSlug && BRANDS.includes(selectedBrand)) {
    const parsed = parseNumberSlug(selectedSlug);
    if (parsed) {
      const content = getArticleContent(selectedBrand, parsed.number, parsed.slug);
      if (content) {
        const result = validateArticle(content);
        return (
          <DetailValidation
            brand={selectedBrand}
            slug={selectedSlug}
            result={result}
          />
        );
      }
    }
  }

  // ブランド別一括検証
  const brand = selectedBrand && BRANDS.includes(selectedBrand) ? selectedBrand : undefined;
  const articles = getArticleList(brand);

  const results = articles.map((meta) => {
    const content = getArticleContent(meta.brand, meta.number, meta.slug);
    if (!content) return null;
    return validateArticle(content);
  }).filter(Boolean);

  const totalErrors = results.reduce((s, r) => s + (r?.errorCount ?? 0), 0);
  const totalWarnings = results.reduce((s, r) => s + (r?.warningCount ?? 0), 0);
  const cleanCount = results.filter(
    (r) => r?.errorCount === 0 && r?.warningCount === 0
  ).length;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
          ルール検証
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          FK番号・価格・URL・UTM を一括チェックします
        </p>
      </div>

      {/* サマリーバー */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        <div className="bg-red-50 border border-red-200 rounded-lg px-6 py-4 text-center">
          <div className="text-2xl font-bold text-red-600">{totalErrors}</div>
          <div className="text-xs text-gray-500 mt-1">❌ エラー（件）</div>
        </div>
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-6 py-4 text-center">
          <div className="text-2xl font-bold text-amber-600">
            {totalWarnings}
          </div>
          <div className="text-xs text-gray-500 mt-1">⚠️ 警告（件）</div>
        </div>
        <div className="bg-green-50 border border-green-200 rounded-lg px-6 py-4 text-center">
          <div className="text-2xl font-bold text-green-600">{cleanCount}</div>
          <div className="text-xs text-gray-500 mt-1">✓ クリーン（件）</div>
        </div>
      </div>

      <BrandFilterTabs basePath="/validation" brand={brand} />

      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs font-medium text-gray-500 uppercase tracking-wider">
            <tr>
              <th className="text-left px-4 py-3">ブランド</th>
              <th className="text-left px-4 py-3">スラッグ</th>
              <th className="text-center px-3 py-3 w-20">エラー</th>
              <th className="text-center px-3 py-3 w-20">警告</th>
              <th className="px-4 py-3 w-28 text-right">アクション</th>
            </tr>
          </thead>
          <tbody>
            {results.map((result) => {
              if (!result) return null;
              const { articleMeta, errorCount, warningCount } = result;
              const ok = errorCount === 0 && warningCount === 0;
              const rowBg =
                errorCount > 0
                  ? "bg-red-50"
                  : warningCount > 0
                  ? "bg-amber-50"
                  : "";
              return (
                <tr
                  key={`${articleMeta.brand}_${articleMeta.filename}`}
                  className={`border-b border-gray-100 hover:bg-gray-50 ${rowBg}`}
                >
                  <td className="px-4 py-2.5 text-xs text-gray-500">
                    {BRAND_LABELS[articleMeta.brand]}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs text-gray-600">
                    {articleMeta.number}_{articleMeta.slug}
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    {errorCount > 0 ? (
                      <span className="text-sm font-semibold text-red-600">
                        {errorCount}
                      </span>
                    ) : (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    {warningCount > 0 ? (
                      <span className="text-sm font-semibold text-amber-600">
                        {warningCount}
                      </span>
                    ) : (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    {!ok ? (
                      <Link
                        href={`/validation?brand=${articleMeta.brand}&slug=${articleMeta.number}_${articleMeta.slug}`}
                        className="text-xs text-blue-600 hover:underline"
                      >
                        詳細を見る
                      </Link>
                    ) : (
                      <span className="text-green-600 text-xs">✓ OK</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {results.length === 0 && (
          <div className="text-center py-8 text-gray-400 text-sm">
            記事が見つかりません
          </div>
        )}
      </div>
    </div>
  );
}
