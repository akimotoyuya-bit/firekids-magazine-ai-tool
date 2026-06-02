import fs from "fs";
import path from "path";
import type { ArticleContent, ArticleMeta, Brand } from "./types";
import { BRANDS } from "./types";

const REPO_ROOT = process.cwd();
const ARTICLES_DIR = path.join(REPO_ROOT, "articles");
const X_POSTS_DIR = path.join(REPO_ROOT, "x_posts");

function parseFilename(filename: string): {
  number: string;
  slug: string;
} | null {
  // 例: 014_article_submariner_5512_5513.txt
  //     014_x_submariner_5512_5513.md
  const m = filename.match(/^(\d+)_(?:article|x)_(.+)\.(txt|html|md|jpg)$/);
  if (!m) return null;
  return { number: m[1], slug: m[2] };
}

export function getArticleList(brand?: Brand): ArticleMeta[] {
  const brands = brand ? [brand] : BRANDS;
  const result: ArticleMeta[] = [];

  for (const b of brands) {
    const brandDir = path.join(ARTICLES_DIR, b);
    if (!fs.existsSync(brandDir)) continue;

    const files = fs.readdirSync(brandDir);
    const slugMap = new Map<string, Partial<ArticleMeta>>();

    for (const file of files) {
      if (file.startsWith("_")) continue;
      const parsed = parseFilename(file);
      if (!parsed) continue;
      const key = `${parsed.number}_${parsed.slug}`;

      if (!slugMap.has(key)) {
        slugMap.set(key, {
          brand: b,
          slug: parsed.slug,
          number: parsed.number,
          filename: key,
          hasTxt: false,
          hasHtml: false,
          hasXPost: false,
          hasXImage: false,
          isPosted: false,
        });
      }
      const entry = slugMap.get(key)!;
      if (file.endsWith(".txt")) entry.hasTxt = true;
      if (file.endsWith(".html")) entry.hasHtml = true;
    }

    // x_posts から対応するファイルを確認
    const xBrandDir = path.join(X_POSTS_DIR, b);
    if (fs.existsSync(xBrandDir)) {
      const xFiles = fs.readdirSync(xBrandDir);
      for (const file of xFiles) {
        const parsed = parseFilename(file);
        if (!parsed) continue;
        const key = `${parsed.number}_${parsed.slug}`;
        if (!slugMap.has(key)) continue;
        const entry = slugMap.get(key)!;
        if (file.endsWith(".md")) entry.hasXPost = true;
        if (file.endsWith(".jpg")) entry.hasXImage = true;
      }

      // _posted フォルダにあるものをチェック
      const postedDir = path.join(xBrandDir, "_posted");
      if (fs.existsSync(postedDir)) {
        const postedFiles = fs.readdirSync(postedDir);
        for (const file of postedFiles) {
          const parsed = parseFilename(file);
          if (!parsed) continue;
          const key = `${parsed.number}_${parsed.slug}`;
          if (slugMap.has(key)) {
            slugMap.get(key)!.isPosted = true;
          }
        }
      }
    }

    // _posted フォルダ (articles) のチェック
    const postedDir = path.join(brandDir, "_posted");
    if (fs.existsSync(postedDir)) {
      const postedFiles = fs.readdirSync(postedDir);
      for (const file of postedFiles) {
        const parsed = parseFilename(file);
        if (!parsed) continue;
        const key = `${parsed.number}_${parsed.slug}`;
        if (slugMap.has(key)) {
          slugMap.get(key)!.isPosted = true;
        }
      }
    }

    const brandArticles = Array.from(slugMap.values()) as ArticleMeta[];
    brandArticles.sort((a, b) => Number(a.number) - Number(b.number));
    result.push(...brandArticles);
  }

  return result;
}

export function getArticleContent(
  brand: Brand,
  number: string,
  slug: string
): ArticleContent | null {
  const key = `${number}_${slug}`;
  const meta: ArticleMeta = {
    brand,
    slug,
    number,
    filename: key,
    hasTxt: false,
    hasHtml: false,
    hasXPost: false,
    hasXImage: false,
    isPosted: false,
  };

  const brandDir = path.join(ARTICLES_DIR, brand);
  const txtPath = path.join(brandDir, `${number}_article_${slug}.txt`);
  const htmlPath = path.join(brandDir, `${number}_article_${slug}.html`);

  let txt: string | undefined;
  let html: string | undefined;
  let xPost: string | undefined;

  if (fs.existsSync(txtPath)) {
    txt = fs.readFileSync(txtPath, "utf-8");
    meta.hasTxt = true;
  }
  if (fs.existsSync(htmlPath)) {
    html = fs.readFileSync(htmlPath, "utf-8");
    meta.hasHtml = true;
  }

  const xBrandDir = path.join(X_POSTS_DIR, brand);
  const xPostPath = path.join(xBrandDir, `${number}_x_${slug}.md`);
  const xImagePath = path.join(xBrandDir, `${number}_x_${slug}.jpg`);
  if (fs.existsSync(xPostPath)) {
    xPost = fs.readFileSync(xPostPath, "utf-8");
    meta.hasXPost = true;
  }
  if (fs.existsSync(xImagePath)) {
    meta.hasXImage = true;
  }

  // _posted チェック
  const postedDir = path.join(brandDir, "_posted");
  if (fs.existsSync(postedDir)) {
    const postedFiles = fs.readdirSync(postedDir);
    if (postedFiles.some((f) => f.includes(key))) meta.isPosted = true;
  }

  if (!txt && !html) return null;

  return { meta, txt, html, xPost };
}

export function getBrandStats(): Record<
  Brand,
  { total: number; hasTxt: number; hasHtml: number; hasXPost: number }
> {
  const stats: Record<
    Brand,
    { total: number; hasTxt: number; hasHtml: number; hasXPost: number }
  > = {} as never;

  for (const brand of BRANDS) {
    const articles = getArticleList(brand);
    stats[brand] = {
      total: articles.length,
      hasTxt: articles.filter((a) => a.hasTxt).length,
      hasHtml: articles.filter((a) => a.hasHtml).length,
      hasXPost: articles.filter((a) => a.hasXPost).length,
    };
  }
  return stats;
}
