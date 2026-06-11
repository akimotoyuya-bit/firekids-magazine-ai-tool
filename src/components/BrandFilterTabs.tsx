import Link from "next/link";
import { getArticleList } from "@/lib/articles";
import { BRANDS, BRAND_LABELS, type Brand } from "@/lib/types";

/**
 * ブランドフィルタータブ（validation / wordpress ページ共通）。
 */
export default function BrandFilterTabs({
  basePath,
  brand,
}: {
  basePath: string;
  brand?: Brand;
}) {
  return (
    <div className="inline-flex flex-wrap gap-1 bg-white border border-gray-200 rounded-lg p-1 mb-4">
      <Link
        href={basePath}
        className={`text-sm px-3 py-1.5 rounded-md transition ${
          !brand
            ? "font-medium text-gray-900 bg-gray-100"
            : "text-gray-500 hover:bg-gray-100"
        }`}
      >
        すべて
      </Link>
      {BRANDS.filter((b) => getArticleList(b).length > 0).map((b) => (
        <Link
          key={b}
          href={`${basePath}?brand=${b}`}
          className={`text-sm px-3 py-1.5 rounded-md transition ${
            brand === b
              ? "font-medium text-gray-900 bg-gray-100"
              : "text-gray-500 hover:bg-gray-100"
          }`}
        >
          {BRAND_LABELS[b]}
        </Link>
      ))}
    </div>
  );
}
