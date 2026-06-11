import Link from "next/link";
import { BRAND_LABELS, type ArticleContent, type Brand } from "@/lib/types";

/**
 * WordPress dry-run 詳細表示（wordpress ページから抽出）。
 */
export default function DryRunDetail({
  brand,
  slug,
  content,
}: {
  brand: Brand;
  slug: string;
  content: ArticleContent | null;
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

      <div className="mb-4 bg-blue-50 border-l-4 border-blue-400 px-4 py-3 rounded-r-md flex items-start gap-2">
        <span className="text-blue-400">ℹ️</span>
        <p className="text-sm text-blue-700">
          これは <strong>dry-run（確認専用）</strong>{" "}
          です。WordPressへの実際の投稿は行われません。
        </p>
      </div>

      {/* 投稿プレビューカード */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <InfoCard label="タイトル" value={title || "(不明)"} />
        <InfoCard label="ブランド" value={BRAND_LABELS[brand]} />
        <InfoCard label="文字数（概算）" value={`${wordCount.toLocaleString()}字`} />
        <InfoCard label="og:image" value={ogImage || "(なし)"} mono />
      </div>

      {metaDesc && (
        <div className="mb-4 glass p-4">
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
      <div className="glass-strong overflow-hidden mb-6">
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
            className="flex items-center gap-3 px-4 py-2.5 border-b border-white/40 last:border-0 text-sm"
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
      <pre className="glass p-4 text-xs overflow-auto max-h-80 whitespace-pre-wrap font-mono leading-relaxed">
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
    <div className="glass p-4">
      <div className="text-xs text-[#5a5248] mb-1">{label}</div>
      <div className={`text-sm text-[#1a1a1a] break-all ${mono ? "font-mono" : ""}`}>
        {value}
      </div>
    </div>
  );
}
