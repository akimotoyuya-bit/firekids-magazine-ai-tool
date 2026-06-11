import Link from "next/link";
import type { Brand, ValidationIssue, ValidationResult } from "@/lib/types";

const TYPE_LABELS: Record<string, string> = {
  fk_number: "FK番号",
  price: "価格表現",
  individual_url: "個別商品URL",
  missing_utm: "UTMパラメータ不足",
  missing_cta: "CTA不足",
  ai_episode: "擬似エピソード・禁止語気",
  lifestyle_link: "ライフスタイル紐付け",
  external_source: "外部ソース言及",
};

/**
 * 1記事分の検証詳細表示（validation ページから抽出）。
 */
export default function DetailValidation({
  brand,
  slug,
  result,
}: {
  brand: Brand;
  slug: string;
  result: ValidationResult;
}) {
  const issuesByType = result.issues.reduce<Record<string, ValidationIssue[]>>(
    (acc, issue) => {
      if (!acc[issue.type]) acc[issue.type] = [];
      acc[issue.type].push(issue);
      return acc;
    },
    {}
  );

  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <Link
          href={`/validation?brand=${brand}`}
          className="text-sm text-[#5a5248] hover:underline"
        >
          ← 検証一覧
        </Link>
        <h1 className="text-lg font-bold text-[#1a1a1a]">
          {slug} — 検証詳細
        </h1>
        <Link
          href={`/articles/${brand}/${slug}`}
          className="text-[#E67E22] text-xs hover:underline ml-auto"
        >
          記事プレビュー →
        </Link>
      </div>

      {result.issues.length === 0 ? (
        <div className="p-4 bg-green-50 border border-green-300 rounded text-green-700 text-sm font-medium">
          ✓ ルール違反が検出されませんでした
        </div>
      ) : (
        <div className="space-y-4">
          {Object.entries(issuesByType).map(([type, issues]) => (
            <div key={type} className="glass-strong overflow-hidden">
              <div className="fk-thead px-4 py-2.5 text-sm font-medium flex items-center gap-2">
                {TYPE_LABELS[type] ?? type}
                <span className="ml-auto text-xs">
                  {issues.filter((i) => i.severity === "error").length > 0 && (
                    <span className="text-red-300 mr-2">
                      エラー {issues.filter((i) => i.severity === "error").length}
                    </span>
                  )}
                  {issues.filter((i) => i.severity === "warning").length > 0 && (
                    <span className="text-yellow-300">
                      警告 {issues.filter((i) => i.severity === "warning").length}
                    </span>
                  )}
                </span>
              </div>
              <div className="divide-y divide-[#e8e4de]">
                {issues.map((issue, i) => (
                  <div
                    key={i}
                    className={`px-4 py-3 text-sm ${
                      issue.severity === "error"
                        ? "bg-red-50"
                        : "bg-yellow-50"
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <span
                        className={`text-xs font-bold mt-0.5 ${
                          issue.severity === "error"
                            ? "text-red-700"
                            : "text-yellow-700"
                        }`}
                      >
                        {issue.severity === "error" ? "ERROR" : "WARN"}
                      </span>
                      <div>
                        <div className="font-medium text-[#1a1a1a]">
                          {issue.message}
                        </div>
                        {issue.line && (
                          <div className="text-xs text-gray-500 mt-0.5">
                            行 {issue.line}
                          </div>
                        )}
                        {issue.excerpt && (
                          <pre className="mt-1 text-xs bg-white border border-[#e8e4de] rounded px-2 py-1 font-mono text-gray-700 whitespace-pre-wrap">
                            {issue.excerpt}
                          </pre>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
