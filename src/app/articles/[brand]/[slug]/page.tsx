import Link from "next/link";
import { notFound } from "next/navigation";
import { getArticleContent } from "@/lib/articles";
import { validateArticle } from "@/lib/validation";
import { BRANDS, BRAND_LABELS, type Brand } from "@/lib/types";

interface Props {
  params: { brand: string; slug: string };
}

export default function ArticlePreviewPage({ params }: Props) {
  const brand = params.brand.toUpperCase() as Brand;
  if (!BRANDS.includes(brand)) return notFound();

  // slug は "014_submariner_5512_5513" のような形式
  const slugParam = params.slug;
  const m = slugParam.match(/^(\d+)_(.+)$/);
  if (!m) return notFound();

  const [, number, slug] = m;
  const content = getArticleContent(brand, number, slug);
  if (!content) return notFound();

  const validation = validateArticle(content);

  return (
    <div>
      {/* ヘッダー */}
      <div className="mb-4 flex items-center gap-3 flex-wrap">
        <Link
          href={`/articles/${brand}`}
          className="text-sm text-[#5a5248] hover:underline"
        >
          ← {BRAND_LABELS[brand]}
        </Link>
        <h1 className="text-lg font-bold text-[#1a1a1a]">
          {number} — {slug}
        </h1>
        {content.meta.isPosted && (
          <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded">
            投稿済み
          </span>
        )}
      </div>

      {/* 検証サマリー */}
      <ValidationSummaryBar
        errorCount={validation.errorCount}
        warningCount={validation.warningCount}
        slug={`${number}_${slug}`}
        brand={brand}
      />

      {/* タブ形式のプレビュー */}
      <div className="mt-6">
        <PreviewTabs content={content} />
      </div>
    </div>
  );
}

function ValidationSummaryBar({
  errorCount,
  warningCount,
  slug,
  brand,
}: {
  errorCount: number;
  warningCount: number;
  slug: string;
  brand: string;
}) {
  const ok = errorCount === 0 && warningCount === 0;
  return (
    <div
      className={`border rounded p-3 flex items-center gap-4 text-sm ${
        ok
          ? "border-green-300 bg-green-50"
          : errorCount > 0
          ? "border-red-300 bg-red-50"
          : "border-yellow-300 bg-yellow-50"
      }`}
    >
      {ok ? (
        <span className="text-green-700 font-medium">✓ ルール違反なし</span>
      ) : (
        <>
          {errorCount > 0 && (
            <span className="text-red-700 font-medium">
              エラー {errorCount}件
            </span>
          )}
          {warningCount > 0 && (
            <span className="text-yellow-700 font-medium">
              警告 {warningCount}件
            </span>
          )}
        </>
      )}
      <Link
        href={`/validation?brand=${brand}&slug=${slug}`}
        className="ml-auto text-[#E67E22] hover:underline text-xs"
      >
        詳細を確認 →
      </Link>
    </div>
  );
}

function PreviewTabs({ content }: { content: { txt?: string; html?: string; xPost?: string } }) {
  const tabs = [
    { id: "txt", label: "TXT（マスター）", available: !!content.txt },
    { id: "html", label: "HTML", available: !!content.html },
    { id: "xpost", label: "X投稿", available: !!content.xPost },
  ];

  return (
    <div>
      {/* TXT */}
      {content.txt && (
        <div className="mb-6">
          <h2 className="text-sm font-bold text-[#1a1a1a] mb-2 flex items-center gap-2">
            <span className="bg-green-600 text-white text-xs px-2 py-0.5 rounded">
              TXT マスター
            </span>
          </h2>
          <pre className="bg-white border border-[#e8e4de] rounded p-4 text-xs overflow-auto max-h-96 whitespace-pre-wrap font-mono leading-relaxed">
            {content.txt}
          </pre>
        </div>
      )}
      {!content.txt && (
        <div className="mb-4 p-3 bg-gray-50 border border-gray-200 rounded text-sm text-gray-500">
          TXTファイルなし
        </div>
      )}

      {/* HTML */}
      {content.html && (
        <div className="mb-6">
          <h2 className="text-sm font-bold text-[#1a1a1a] mb-2 flex items-center gap-2">
            <span className="bg-blue-600 text-white text-xs px-2 py-0.5 rounded">
              HTML 派生
            </span>
          </h2>
          <pre className="bg-white border border-[#e8e4de] rounded p-4 text-xs overflow-auto max-h-96 whitespace-pre-wrap font-mono leading-relaxed">
            {content.html}
          </pre>
        </div>
      )}
      {!content.html && (
        <div className="mb-4 p-3 bg-gray-50 border border-gray-200 rounded text-sm text-gray-500">
          HTMLファイルなし
        </div>
      )}

      {/* X投稿 */}
      {content.xPost && (
        <div className="mb-6">
          <h2 className="text-sm font-bold text-[#1a1a1a] mb-2 flex items-center gap-2">
            <span className="bg-purple-600 text-white text-xs px-2 py-0.5 rounded">
              X投稿 派生
            </span>
          </h2>
          <pre className="bg-white border border-[#e8e4de] rounded p-4 text-xs overflow-auto max-h-96 whitespace-pre-wrap font-mono leading-relaxed">
            {content.xPost}
          </pre>
        </div>
      )}
      {!content.xPost && (
        <div className="mb-4 p-3 bg-gray-50 border border-gray-200 rounded text-sm text-gray-500">
          X投稿ファイルなし
        </div>
      )}
    </div>
  );
}
