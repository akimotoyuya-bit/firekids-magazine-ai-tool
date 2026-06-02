import Link from "next/link";
import { notFound } from "next/navigation";
import { getArticleList } from "@/lib/articles";
import { BRANDS, BRAND_LABELS, type Brand } from "@/lib/types";

interface Props {
  params: { brand: string };
}

export function generateStaticParams() {
  return BRANDS.map((b) => ({ brand: b }));
}

export default function BrandArticlesPage({ params }: Props) {
  const brand = params.brand.toUpperCase() as Brand;
  if (!BRANDS.includes(brand)) return notFound();

  const articles = getArticleList(brand);

  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <Link href="/articles" className="text-sm text-[#5a5248] hover:underline">
          ← 記事一覧
        </Link>
        <h1 className="text-xl font-bold text-[#1a1a1a]">
          {BRAND_LABELS[brand]}
          <span className="ml-2 text-sm font-normal text-gray-400">
            ({articles.length}件)
          </span>
        </h1>
      </div>

      <div className="border border-[#e8e4de] rounded overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-[#1a1a1a] text-white">
            <tr>
              <th className="text-left px-4 py-2 w-16">No.</th>
              <th className="text-left px-4 py-2">スラッグ</th>
              <th className="text-center px-3 py-2 w-14">TXT</th>
              <th className="text-center px-3 py-2 w-14">HTML</th>
              <th className="text-center px-3 py-2 w-14">X投稿</th>
              <th className="text-center px-3 py-2 w-14">X画像</th>
              <th className="px-4 py-2 w-24"></th>
            </tr>
          </thead>
          <tbody>
            {articles.map((article, i) => (
              <tr
                key={article.filename}
                className={i % 2 === 0 ? "bg-white" : "bg-[#faf6ee]"}
              >
                <td className="px-4 py-2 text-gray-500 font-mono text-xs">
                  {article.number}
                </td>
                <td className="px-4 py-2 font-mono text-xs">
                  {article.slug}
                </td>
                <td className="px-3 py-2 text-center">
                  <StatusBadge ok={article.hasTxt} />
                </td>
                <td className="px-3 py-2 text-center">
                  <StatusBadge ok={article.hasHtml} />
                </td>
                <td className="px-3 py-2 text-center">
                  <StatusBadge ok={article.hasXPost} />
                </td>
                <td className="px-3 py-2 text-center">
                  <StatusBadge ok={article.hasXImage} />
                </td>
                <td className="px-4 py-2 text-right">
                  <Link
                    href={`/articles/${brand}/${article.number}_${article.slug}`}
                    className="text-[#E67E22] text-xs hover:underline"
                  >
                    プレビュー →
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

function StatusBadge({ ok }: { ok: boolean }) {
  return ok ? (
    <span className="inline-block w-4 h-4 rounded-full bg-green-500" title="あり" />
  ) : (
    <span className="inline-block w-4 h-4 rounded-full bg-gray-200" title="なし" />
  );
}
