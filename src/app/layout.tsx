import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { NavLink } from "@/components/NavLink";

export const metadata: Metadata = {
  title: "FIRE KIDS Magazine — 管理ツール",
  description: "FIRE KIDS Magazine 記事管理・検証・投稿補助ツール",
};

const GENERATOR_URL =
  process.env.NEXT_PUBLIC_GENERATOR_URL ??
  "https://s5d6hqidtk.us-east-1.awsapprunner.com/generator/";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+JP:wght@400;500;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen flex flex-col">
        <header
          className="glass-nav sticky top-0 z-50"
          style={{ height: "var(--header-h)" }}
        >
          <div className="max-w-7xl mx-auto px-5 h-full flex items-center gap-4">
            {/* ロゴ */}
            <Link href="/" className="flex items-center gap-2 hover:opacity-80 transition">
              <span
                className="text-white w-7 h-7 rounded-[7px] font-bold text-xs flex items-center justify-center flex-shrink-0"
                style={{
                  background: "linear-gradient(135deg,#DC2626 0%,#EF4444 45%,#F97373 100%)",
                  boxShadow: "0 2px 6px rgba(220,38,38,.28)",
                }}
              >
                FK
              </span>
              <span className="text-sm font-semibold text-[#0F172A] tracking-tight">
                FIRE KIDS Magazine
              </span>
            </Link>

            <div className="flex-1" />

            {/* ナビ */}
            <nav className="flex items-center gap-1">
              <NavLink href="/articles"   label="記事一覧" />
              <NavLink href="/validation" label="ルール検証" />
              <NavLink href="/wordpress"  label="WP dry-run" />
              <a
                href={GENERATOR_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-primary ml-3 text-xs"
                aria-label="記事生成ツールを開く（別ウィンドウ）"
              >
                <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden>
                  <path d="M2.5 12.5V10.25L9.5 3.25L11.75 5.5L4.75 12.5H2.5Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
                  <path d="M8.5 4.25L10.75 6.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
                記事を生成
              </a>
            </nav>
          </div>
        </header>

        <main className="flex-1 max-w-7xl mx-auto w-full px-5 py-8">
          {children}
        </main>

        <footer className="text-center py-4 text-xs text-[var(--text-muted)]">
          FIRE KIDS Magazine 管理ツール — 内部使用限定
        </footer>
      </body>
    </html>
  );
}
