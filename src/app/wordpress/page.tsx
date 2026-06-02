import Link from "next/link";
import { getArticleList, getArticleContent } from "@/lib/articles";
import { BRANDS, BRAND_LABELS, type Brand } from "@/lib/types";

interface Props {
  searchParams: { brand?: string; slug?: string };
}

export default function WordPressDryRunPage({ searchParams }: Props) {
  const selectedBrand = searchParams.brand?.toUpperCase() as Brand | undefined;
  const selectedSlug = searchParams.slug;

  // 記事が選択されている場合 dry-run 詳細を表示
  if (selectedBrand && selectedSlug && BRANDS.includes(selectedBrand)) {
    const m = selectedSlug.match(/^(\d+)_(.+)$/);
    if (m) {
      const [, number, slug] = m;
      const content = getArticleContent(selectedBrand, number, slug);
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
        <h1 className="text-xl font-bold text-[#1a1a1a]">WordPress dry-run</h1>
        <p className="text-sm text-[#5a5248] mt-1">
          投稿する記事を選択して内容を確認してください。本番投稿はdry-run確認後のみ行います。
        </p>
      </div>

      <div
        className="mb-4 p-3 border border-yellow-300 bg-yellow-50 rounded text-sm text-yellow-800"
      >
        ⚠ このページは dry-run（内容確認）専用です。「本番投稿」ボタンは現在未実装です。
        WordPress投稿は確認後に別途実施してください。
      </div>

      {/* ブランドフィルター */}
      <div className="flex gap-2 flex-wrap mb-4">
        <Link
          href="/wordpress"
          className={`text-xs px-3 py-1 rounded border transition ${
            !brand
              ? "bg-[#1a1a1a] text-white border-[#1a1a1a]"
              : "border-[#e8e4de] hover:border-[#1a1a1a]"
          }`}
        >
          すべて
        </Link>
        {BRANDS.filter((b) => getArticleList(b).length > 0).map((b) => (
          <Link
            key={b}
            href={`/wordpress?brand=${b}`}
            className={`text-xs px-3 py-1 rounded border transition ${
              brand === b
                ? "bg-[#1a1a1a] text-white border-[#1a1a1a]"
                : "border-[#e8e4de] hover:border-[#1a1a1a]"
            }`}
          >
            {BRAND_LABELS[b]}
          </Link>
        ))}
      </div>

      <div className="border border-[#e8e4de] rounded overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-[#1a1a1a] text-white">
            <tr>
              <th className="text-left px-4 py-2">ブランド</th>
              <th className="text-left px-4 py-2">スラッグ</th>
              <th className="text-center px-3 py-2 w-14">TXT</th>
              <th className="text-center px-3 py-2 w-14">HTML</th>
              <th className="px-4 py-2 w-32"></th>
            </tr>
          </thead>
          <tbody>
            {articles.map((article, i) => (
              <tr
                key={article.filename}
                className={i % 2 === 0 ? "bg-white" : "bg-[#faf6ee]"}
              >
                <td className="px-4 py-2 text-xs text-gray-500">
                  {BRAND_LABELS[article.brand]}
                </td>
                <td className="px-4 py-2 font-mono text-xs">
                  {article.number}_{article.slug}
                </td>
                <td className="px-3 py-2 text-center text-xs">
                  {article.hasTxt ? (
                    <span className="text-green-700">✓</span>
                  ) : (
                    <span className="text-gray-300">—</span>
                  )}
                </td>
                <td className="px-3 py-2 text-center text-xs">
                  {article.hasHtml ? (
                    <span className="text-blue-700">✓</span>
                  ) : (
                    <span className="text-gray-300">—</span>
                  )}
                </td>
                <td className="px-4 py-2 text-right">
                  <Link
                    href={`/wordpress?brand=${article.brand}&slug=${article.number}_${article.slug}`}
                    className="text-[#E67E22] text-xs hover:underline"
                  >
                    dry-run確認 →
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

function DryRunDetail({
  brand,
  slug,
  content,
}: {
  brand: Brand;
  slug: string;
  content: ReturnType<typeof getArticleContent>;
}) {
  if (!content) return null;

  // HTMLからタイトルを抽出
  let title = "";
  if (content.html) {
    const titleMatch = content.html.match(/title:\s*(.+)/);
    if (titleMatch) title = titleMatch[1].trim();
  }
  if (!title && content.txt) {
    const firstLine = content.txt.split("\n").find((l) => l.trim().startsWith("#"));
    if (firstLine) title = firstLine.replace(/^#+\s*/, "").trim();
  }

  // meta_description 抽出
  let metaDesc = "";
  if (content.html) {
    const m = content.html.match(/meta_description:\s*(.+)/);
    if (m) metaDesc = m[1].trim();
  }

  // og:image 抽出
  let ogImage = "";
  if (content.html) {
    const m = content.html.match(/og:image:\s*(https?:\/\/[^\s]+)/);
    if (m) ogImage = m[1].trim();
  }

  const htmlPreview = content.html ?? "(HTMLなし)";
  const wordCount = (content.txt ?? content.html ?? "").replace(
    /<[^>]*>/g,
    ""
  ).length;

  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <Link
          href="/wordpress"
          className="text-sm text-[#5a5248] hover:underline"
        >
          ← dry-run一覧
        </Link>
        <h1 className="text-lg font-bold text-[#1a1a1a]">
          dry-run確認: {slug}
        </h1>
      </div>

      <div className="mb-4 p-3 border border-yellow-300 bg-yellow-50 rounded text-sm text-yellow-800">
        ⚠ これはdry-runです。WordPressへの実際の投稿は行われません。
      </div>

      {/* 投稿プレビューカード */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <InfoCard label="タイトル" value={title || "(不明)"} />
        <InfoCard label="ブランド" value={BRAND_LABELS[brand]} />
        <InfoCard label="文字数（概算）" value={`${wordCount.toLocaleString()}字`} />
        <InfoCard label="og:image" value={ogImage || "(なし)"} mono />
      </div>

      {metaDesc && (
        <div className="mb-4 border border-[#e8e4de] rounded p-3 bg-white">
          <div className="text-xs font-bold text-[#5a5248] mb-1">
            meta_description
          </div>
          <div className="text-sm text-[#1a1a1a]">{metaDesc}</div>
          <div className="text-xs text-gray-400 mt-1">{metaDesc.length}字</div>
        </div>
      )}

      {/* チェックリスト */}
      <h2 className="text-sm font-bold mb-2 text-[#1a1a1a]">
        投稿前チェックリスト
      </h2>
      <div className="border border-[#e8e4de] rounded overflow-hidden mb-6">
        {[
          { label: "HTMLファイルが存在する", ok: content.meta.hasHtml },
          { label: "TXTマスターが存在する", ok: content.meta.hasTxt },
          { label: "X投稿ファイルが存在する", ok: content.meta.hasXPost },
          { label: "X投稿用画像が存在する", ok: content.meta.hasXImage },
          { label: "タイトルが取得できた", ok: !!title },
          { label: "meta_descriptionが取得できた", ok: !!metaDesc },
          { label: "og:imageが設定されている", ok: !!ogImage },
        ].map(({ label, ok }) => (
          <div
            key={label}
            className="flex items-center gap-3 px-4 py-2 border-b border-[#e8e4de] last:border-0 bg-white text-sm"
          >
            <span
              className={`font-bold ${ok ? "text-green-600" : "text-gray-300"}`}
            >
              {ok ? "✓" : "○"}
            </span>
            <span className={ok ? "text-[#1a1a1a]" : "text-gray-400"}>
              {label}
            </span>
          </div>
        ))}
      </div>

      {/* HTML本文プレビュー */}
      <h2 className="text-sm font-bold mb-2 text-[#1a1a1a]">
        HTML本文プレビュー（先頭2000字）
      </h2>
      <pre className="bg-white border border-[#e8e4de] rounded p-4 text-xs overflow-auto max-h-80 whitespace-pre-wrap font-mono leading-relaxed">
        {htmlPreview.slice(0, 2000)}
        {htmlPreview.length > 2000 && "\n\n... (以下省略)"}
      </pre>
    </div>
  );
}

function InfoCard({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="border border-[#e8e4de] rounded p-3 bg-white">
      <div className="text-xs text-[#5a5248] mb-1">{label}</div>
      <div className={`text-sm text-[#1a1a1a] break-all ${mono ? "font-mono" : ""}`}>
        {value}
      </div>
    </div>
  );
}
