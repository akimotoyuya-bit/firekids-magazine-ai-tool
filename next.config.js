/** @type {import('next').NextConfig} */
const nextConfig = {
  // 既存の articles/, x_posts/, data/ ディレクトリはそのまま保持し、
  // Next.js サーバーサイドから fs 経由でアクセスする
  experimental: {
    serverComponentsExternalPackages: [],
  },
};

module.exports = nextConfig;
