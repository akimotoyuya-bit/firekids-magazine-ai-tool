import Link from "next/link";
import { getArticleList } from "@/lib/articles";
import { BRANDS, BRAND_LABELS, type Brand } from "@/lib/types";

export default function BrandFilterTabs({
  basePath,
  brand,
}: {
  basePath: string;
  brand?: Brand;
}) {
  const activeBrands = BRANDS.filter((b) => getArticleList(b).length > 0);

  return (
    <div className="flex flex-wrap gap-2 mb-5" role="navigation" aria-label="ブランドフィルター">
      <Link
        href={basePath}
        className={`fk-chip ${!brand ? "fk-chip-active" : ""}`}
        aria-current={!brand ? "page" : undefined}
      >
        すべて
      </Link>
      {activeBrands.map((b) => (
        <Link
          key={b}
          href={`${basePath}?brand=${b}`}
          className={`fk-chip ${brand === b ? "fk-chip-active" : ""}`}
          aria-current={brand === b ? "page" : undefined}
        >
          {BRAND_LABELS[b]}
        </Link>
      ))}
    </div>
  );
}
