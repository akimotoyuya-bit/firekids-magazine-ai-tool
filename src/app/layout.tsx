import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "FIRE KIDS Magazine — 管理ツール",
  description: "FIRE KIDS Magazine 記事管理・検証・投稿補助ツール",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body className="min-h-screen flex flex-col">
        <header className="bg-[#1a1a1a] text-white">
          <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-6">
            <Link
              href="/"
              className="font-bold text-lg tracking-wide hover:opacity-80 transition"
            >
              FIRE KIDS Magazine
              <span className="ml-2 text-sm font-normal text-gray-400">
                管理ツール
              </span>
            </Link>
            <nav className="flex gap-4 text-sm ml-auto">
              <Link
                href="/articles"
                className="hover:text-[#E67E22] transition text-gray-300"
              >
                記事一覧
              </Link>
              <Link
                href="/validation"
                className="hover:text-[#E67E22] transition text-gray-300"
              >
                ルール検証
              </Link>
              <Link
                href="/wordpress"
                className="hover:text-[#E67E22] transition text-gray-300"
              >
                WP dry-run
              </Link>
            </nav>
          </div>
        </header>
        <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-6">
          {children}
        </main>
        <footer className="bg-[#1a1a1a] text-gray-500 text-xs text-center py-3">
          FIRE KIDS Magazine 管理ツール — 内部使用限定
        </footer>
      </body>
    </html>
  );
}
