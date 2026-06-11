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

  // 記事が選択されている場合 dry-run 詳細を表示
  if (selectedBrand && selectedSlug && BRANDS.includes(selectedBrand)) {
    const parsed = parseNumberSlug(selectedSlug);
    if (parsed) {
      const content = getArticleContent(selectedBrand, parsed.number, parsed.slug);
      if (content) {
        return (
          <DryRunDetail
            brand={selectedBrand}
            slug={selectedSlug}
            content={content}
          />
        );
      }
    }
  }

  // 記事選択画面
  const brand = selectedBrand && BRANDS.includes(selectedBrand) ? selectedBrand : undefined;
  const articles = getArticleList(brand).filter((a) => a.hasHtml || a.hasTxt);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
          WordPress dry-run
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          投稿する記事を選択して内容を確認してください。本番投稿はdry-run確認後のみ行います。
        </p>
      </div>

      <div className="mb-4 bg-blue-50 border-l-4 border-blue-400 px-4 py-3 rounded-r-md flex items-start gap-2">
        <span className="text-blue-400">ℹ️</span>
        <p className="text-sm text-blue-700">
          このページは <strong>dry-run（確認専用）</strong>{" "}
          です。「本番投稿」ボタンは現在未実装です。WordPress投稿は確認後に別途実施してください。
        </p>
      </div>

      <BrandFilterTabs basePath="/wordpress" brand={brand} />

      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs font-medium text-gray-500 uppercase tracking-wider">
            <tr>
              <th className="text-left px-4 py-3">ブランド</th>
              <th className="text-left px-4 py-3">スラッグ</th>
              <th className="text-center px-3 py-3 w-14">TXT</th>
              <th className="text-center px-3 py-3 w-14">HTML</th>
              <th className="px-4 py-3 w-32 text-right">アクション</th>
            </tr>
          </thead>
          <tbody>
            {articles.map((article) => (
              <tr
                key={article.filename}
                className="border-b border-gray-100 hover:bg-gray-50"
              >
                <td className="px-4 py-2.5 text-xs text-gray-500">
                  {BRAND_LABELS[article.brand]}
                </td>
                <td className="px-4 py-2.5 font-mono text-xs text-gray-600">
                  {article.number}_{article.slug}
                </td>
                <td className="px-3 py-2.5 text-center text-xs">
                  {article.hasTxt ? (
                    <span className="text-green-600">✓</span>
                  ) : (
                    <span className="text-gray-300">—</span>
                  )}
                </td>
                <td className="px-3 py-2.5 text-center text-xs">
                  {article.hasHtml ? (
                    <span className="text-blue-600">✓</span>
                  ) : (
                    <span className="text-gray-300">—</span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-right">
                  <Link
                    href={`/wordpress?brand=${article.brand}&slug=${article.number}_${article.slug}`}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    dry-run確認
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {articles.length === 0 && (
          <div className="text-center py-8 text-gray-400 text-sm">
            記事が見つかりません
          </div>
        )}
      </div>
    </div>
  );
}
