import PublishedAnalytics from "@/components/PublishedAnalytics";
import { getPublishedPosts } from "@/lib/published-posts";

const GENERATOR_URL =
  process.env.NEXT_PUBLIC_GENERATOR_URL ??
  "https://s5d6hqidtk.us-east-1.awsapprunner.com/generator/";

export const revalidate = 900;
// firekids は nginx で国外 IP を遮断するため、WordPress 取得を東京リージョンから行う。
export const preferredRegion = "hnd1";
// ビルド（米国）ではなく、リクエスト時に東京リージョンのサーバーで取得させる。
export const dynamic = "force-dynamic";

export default async function HomePage() {
  const published = await getPublishedPosts();

  return (
    <div>
      {/* 最重要の操作をページ最上部に固定 */}
      <a
        href={GENERATOR_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="fk-card fk-card-hover block p-6 mb-8 relative overflow-hidden"
        aria-label="記事生成ツールを開く（別ウィンドウ）"
      >
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: "linear-gradient(110deg, rgba(220,38,38,.08) 0%, rgba(239,68,68,.035) 55%, transparent 100%)",
          }}
        />
        <div className="relative flex items-center gap-4">
          <div className="w-11 h-11 rounded-xl bg-[var(--accent)] text-white flex items-center justify-center shrink-0 shadow-md">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className="font-bold text-xl text-[var(--text)]">記事を生成する</span>
              <span className="badge badge-info">AWS Bedrock</span>
            </div>
            <p className="text-sm text-[var(--text-muted)]">
              商品またはテーマ条件を選んで記事を生成・保存します（別ウィンドウで開きます）
            </p>
          </div>
          <span className="text-[#DC2626] font-semibold text-sm whitespace-nowrap hidden sm:flex items-center gap-1">
            生成ツールを開く
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
              <path d="M2 2h10v10M12 2L2 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </span>
        </div>
      </a>

      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gradient mb-2 tracking-tight">
          FIRE KIDS Magazine 投稿ダッシュボード
        </h1>
        <p className="text-sm text-[var(--text-muted)]">
          WordPressの記事を、投稿元・公開状態・時計テーマごとに確認できます。
        </p>
      </div>

      <PublishedAnalytics
        posts={published.posts}
        appClassificationAvailable={published.appClassificationAvailable}
        errors={published.errors}
        fetchedAt={published.fetchedAt}
      />
    </div>
  );
}
