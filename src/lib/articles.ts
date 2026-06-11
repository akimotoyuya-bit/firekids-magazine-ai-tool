import fs from "fs";
import path from "path";
import type { ArticleContent, ArticleMeta, Brand } from "./types";
import { BRANDS } from "./types";

const REPO_ROOT = process.cwd();
const ARTICLES_DIR = path.join(REPO_ROOT, "articles");
const X_POSTS_DIR = path.join(REPO_ROOT, "x_posts");

/** 記事ファイル名のプレフィックス（`014_article_xxx.txt` の "article" 部分） */
const ARTICLE_PREFIX = "article";
/** X 投稿ファイル名のプレフィックス（`014_x_xxx.md` の "x" 部分） */
const X_POST_PREFIX = "x";
/** 記事関連ファイルとして認識する拡張子 */
const KNOWN_EXTENSIONS = ["txt", "html", "md", "jpg"] as const;

/** `_posted` フォルダ名（投稿済みマーカー） */
const POSTED_DIR_NAME = "_posted";

/** ファイル名から抽出した連番とスラッグ */
export interface ParsedFilename {
  number: string;
  slug: string;
}

// 例: 014_article_submariner_5512_5513.txt / 014_x_submariner_5512_5513.md
const FILENAME_RE = new RegExp(
  `^(\\d+)_(?:${ARTICLE_PREFIX}|${X_POST_PREFIX})_(.+)\\.(${KNOWN_EXTENSIONS.join("|")})$`
);

function parseFilename(filename: string): ParsedFilename | null {
  const m = filename.match(FILENAME_RE);
  if (!m) return null;
  return { number: m[1], slug: m[2] };
}

/**
 * URL クエリの `014_submariner_5512` 形式を連番とスラッグに分解する
 * （validation / wordpress ページ共通）。
 */
export function parseNumberSlug(value: string): ParsedFilename | null {
  const m = value.match(/^(\d+)_(.+)$/);
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

      // 最終更新日（txt/html の mtime の新しい方）
      if (file.endsWith(".txt") || file.endsWith(".html")) {
        try {
          const mtime = fs.statSync(path.join(brandDir, file)).mtime;
          const iso = mtime.toISOString();
          if (!entry.updatedAt || iso > entry.updatedAt) entry.updatedAt = iso;
        } catch {
          // stat 失敗時は無視
        }
      }
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
      const postedDir = path.join(xBrandDir, POSTED_DIR_NAME);
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
    const postedDir = path.join(brandDir, POSTED_DIR_NAME);
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
  const txtPath = path.join(brandDir, `${number}_${ARTICLE_PREFIX}_${slug}.txt`);
  const htmlPath = path.join(brandDir, `${number}_${ARTICLE_PREFIX}_${slug}.html`);

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
  const xPostPath = path.join(xBrandDir, `${number}_${X_POST_PREFIX}_${slug}.md`);
  const xImagePath = path.join(xBrandDir, `${number}_${X_POST_PREFIX}_${slug}.jpg`);
  if (fs.existsSync(xPostPath)) {
    xPost = fs.readFileSync(xPostPath, "utf-8");
    meta.hasXPost = true;
  }
  if (fs.existsSync(xImagePath)) {
    meta.hasXImage = true;
  }

  // _posted チェック
  const postedDir = path.join(brandDir, POSTED_DIR_NAME);
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
