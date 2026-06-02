import Link from "next/link";
import { getBrandStats } from "@/lib/articles";
import { BRANDS, BRAND_LABELS } from "@/lib/types";

export default function HomePage() {
  const stats = getBrandStats();
  const totalArticles = Object.values(stats).reduce(
    (s, b) => s + b.total,
    0
  );
  const totalHtml = Object.values(stats).reduce((s, b) => s + b.hasHtml, 0);
  const totalXPost = Object.values(stats).reduce(
    (s, b) => s + b.hasXPost,
    0
  );

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-[#1a1a1a] mb-1">
          FIRE KIDS Magazine 管理ツール
        </h1>
        <p className="text-sm text-[#5a5248]">
          記事ブラウザ・ルール検証・HTML/X変換補助・WordPress投稿dry-run
        </p>
      </div>

      {/* サマリーカード */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <SummaryCard label="総記事数" value={totalArticles} />
        <SummaryCard label="HTML生成済み" value={totalHtml} />
        <SummaryCard label="X投稿あり" value={totalXPost} />
      </div>

      {/* クイックアクション */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <QuickLink
          href="/articles"
          title="記事一覧"
          description="ブランド別に記事を一覧表示・検索"
        />
        <QuickLink
          href="/validation"
          title="ルール検証"
          description="FK番号・価格・URL・UTMを一括チェック"
        />
        <QuickLink
          href="/wordpress"
          title="WP dry-run"
          description="WordPress投稿前の内容確認"
        />
      </div>

      {/* ブランド別概要 */}
      <h2 className="text-lg font-bold mb-3 text-[#1a1a1a]">
        ブランド別概要
      </h2>
      <div className="border border-[#e8e4de] rounded overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-[#1a1a1a] text-white">
            <tr>
              <th className="text-left px-4 py-2">ブランド</th>
              <th className="text-right px-4 py-2">記事</th>
              <th className="text-right px-4 py-2">TXT</th>
              <th className="text-right px-4 py-2">HTML</th>
              <th className="text-right px-4 py-2">X投稿</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {BRANDS.filter((b) => stats[b].total > 0).map((brand, i) => (
              <tr
                key={brand}
                className={i % 2 === 0 ? "bg-white" : "bg-[#faf6ee]"}
              >
                <td className="px-4 py-2 font-medium">
                  {BRAND_LABELS[brand]}
                  <span className="ml-2 text-xs text-gray-400">{brand}</span>
                </td>
                <td className="px-4 py-2 text-right">{stats[brand].total}</td>
                <td className="px-4 py-2 text-right text-green-700">
                  {stats[brand].hasTxt}
                </td>
                <td className="px-4 py-2 text-right text-blue-700">
                  {stats[brand].hasHtml}
                </td>
                <td className="px-4 py-2 text-right text-purple-700">
                  {stats[brand].hasXPost}
                </td>
                <td className="px-4 py-2 text-right">
                  <Link
                    href={`/articles/${brand}`}
                    className="text-[#E67E22] text-xs hover:underline"
                  >
                    一覧 →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SummaryCard({
  label,
  value,
}: {
  label: string;
  value: number;
}) {
  return (
    <div className="border border-[#e8e4de] rounded p-4 bg-white">
      <div className="text-2xl font-bold text-[#1a1a1a]">{value}</div>
      <div className="text-sm text-[#5a5248] mt-1">{label}</div>
    </div>
  );
}

function QuickLink({
  href,
  title,
  description,
}: {
  href: string;
  title: string;
  description: string;
}) {
  return (
    <Link
      href={href}
      className="border border-[#e8e4de] rounded p-4 bg-white hover:border-[#E67E22] hover:shadow-sm transition block"
    >
      <div className="font-bold text-[#1a1a1a] mb-1">{title}</div>
      <div className="text-sm text-[#5a5248]">{description}</div>
    </Link>
  );
}
