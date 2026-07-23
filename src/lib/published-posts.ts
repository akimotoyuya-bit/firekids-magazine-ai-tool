import "server-only";

const GENERATOR_BASE = (
  process.env.GENERATOR_API_BASE ??
  process.env.NEXT_PUBLIC_GENERATOR_URL ??
  "https://s5d6hqidtk.us-east-1.awsapprunner.com/generator/"
).replace(/\/+$/, "");

const WP_API_BASE = (
  process.env.WP_PUBLIC_API_BASE ??
  "https://m.firekids.jp/wp-json/wp/v2"
).replace(/\/+$/, "");

const REVALIDATE_SECONDS = 900;

export type PostOrigin = "app" | "existing";

export interface PublishedPost {
  id: number;
  title: string;
  link: string;
  date: string;
  categories: string[];
  brands: string[];
  models: string[];
  origin: PostOrigin;
  status: "publish" | "draft" | "future";
}

export interface PublishedPostsResult {
  posts: PublishedPost[];
  appClassificationAvailable: boolean;
  errors: string[];
  fetchedAt: string;
}

const BRAND_ALIASES: Array<{ label: string; patterns: string[] }> = [
  { label: "ロレックス", patterns: ["ロレックス", "ROLEX"] },
  { label: "オメガ", patterns: ["オメガ", "OMEGA"] },
  { label: "セイコー", patterns: ["セイコー", "SEIKO"] },
  { label: "グランドセイコー", patterns: ["グランドセイコー", "GRAND SEIKO"] },
  { label: "シチズン", patterns: ["シチズン", "CITIZEN"] },
  { label: "IWC", patterns: ["IWC"] },
  { label: "チューダー", patterns: ["チューダー", "TUDOR"] },
  { label: "オリエント", patterns: ["オリエント", "ORIENT"] },
  { label: "ロンジン", patterns: ["ロンジン", "LONGINES"] },
  { label: "ジャガー・ルクルト", patterns: ["ジャガー・ルクルト", "ジャガールクルト", "JAEGER"] },
  { label: "カルティエ", patterns: ["カルティエ", "CARTIER"] },
  { label: "ユニバーサルジュネーブ", patterns: ["ユニバーサルジュネーブ", "ユニバーサル ジュネーブ", "UNIVERSAL"] },
  { label: "ブライトリング", patterns: ["ブライトリング", "BREITLING"] },
  { label: "ヴァシュロン・コンスタンタン", patterns: ["ヴァシュロン", "VACHERON"] },
  { label: "パテック・フィリップ", patterns: ["パテック", "PATEK"] },
  { label: "オーデマ・ピゲ", patterns: ["オーデマ", "AUDEMARS"] },
  { label: "タグ・ホイヤー", patterns: ["タグ・ホイヤー", "タグホイヤー", "TAG HEUER"] },
  { label: "ゼニス", patterns: ["ゼニス", "ZENITH"] },
  { label: "ハミルトン", patterns: ["ハミルトン", "HAMILTON"] },
  { label: "ブレゲ", patterns: ["ブレゲ", "BREGUET"] },
  { label: "エルメス", patterns: ["エルメス", "HERMES"] },
];

const MODEL_ALIASES: Array<{ label: string; patterns: string[] }> = [
  { label: "デイトジャスト", patterns: ["デイトジャスト", "DATEJUST"] },
  { label: "サブマリーナー", patterns: ["サブマリーナー", "サブマリーナ", "SUBMARINER"] },
  { label: "エクスプローラー", patterns: ["エクスプローラー", "EXPLORER"] },
  { label: "デイトナ", patterns: ["デイトナ", "DAYTONA"] },
  { label: "GMTマスター", patterns: ["GMTマスター", "GMT MASTER"] },
  { label: "ミルガウス", patterns: ["ミルガウス", "MILGAUSS"] },
  { label: "シードゥエラー", patterns: ["シードゥエラー", "SEA-DWELLER", "SEA DWELLER"] },
  { label: "エアキング", patterns: ["エアキング", "AIR-KING", "AIR KING"] },
  { label: "シーマスター", patterns: ["シーマスター", "SEAMASTER"] },
  { label: "スピードマスター", patterns: ["スピードマスター", "SPEEDMASTER"] },
  { label: "コンステレーション", patterns: ["コンステレーション", "CONSTELLATION"] },
  { label: "デ・ヴィル", patterns: ["デ・ヴィル", "デヴィル", "DE VILLE"] },
  { label: "セイコー5", patterns: ["セイコー5", "セイコー 5", "SEIKO 5"] },
  { label: "キングセイコー", patterns: ["キングセイコー", "KING SEIKO"] },
  { label: "グランドセイコー", patterns: ["グランドセイコー", "GRAND SEIKO"] },
  { label: "ロードマーベル", patterns: ["ロードマーベル", "LORD MARVEL"] },
  { label: "セイコーマチック", patterns: ["セイコーマチック", "SEIKOMATIC"] },
  { label: "アストロン", patterns: ["アストロン", "ASTRON"] },
  { label: "ナビタイマー", patterns: ["ナビタイマー", "NAVITIMER"] },
  { label: "クロノマット", patterns: ["クロノマット", "CHRONOMAT"] },
  { label: "ポルトフィーノ", patterns: ["ポルトフィーノ", "PORTOFINO"] },
  { label: "インヂュニア", patterns: ["インヂュニア", "インジュニア", "INGENIEUR"] },
  { label: "アクアタイマー", patterns: ["アクアタイマー", "AQUATIMER"] },
  { label: "タンク", patterns: ["カルティエ タンク", "CARTIER TANK", "タンク ルイ", "タンク マスト"] },
  { label: "サントス", patterns: ["サントス", "SANTOS"] },
  { label: "パシャ", patterns: ["パシャ", "PASHA"] },
  { label: "レベルソ", patterns: ["レベルソ", "REVERSO"] },
  { label: "マスター・コントロール", patterns: ["マスター・コントロール", "マスターコントロール", "MASTER CONTROL"] },
  { label: "ブラックベイ", patterns: ["ブラックベイ", "BLACK BAY"] },
  { label: "プリンス", patterns: ["チューダー プリンス", "TUDOR PRINCE"] },
  { label: "コンクエスト", patterns: ["コンクエスト", "CONQUEST"] },
  { label: "フラッグシップ", patterns: ["フラッグシップ", "FLAGSHIP"] },
  { label: "ナインティーンシックスティ", patterns: ["NINETEEN SIXTY", "ナインティーンシックスティ"] },
];

function decodeHtml(value: string): string {
  const named: Record<string, string> = {
    "&amp;": "&",
    "&quot;": '"',
    "&#039;": "'",
    "&apos;": "'",
    "&lt;": "<",
    "&gt;": ">",
    "&nbsp;": " ",
    "&#8211;": "–",
    "&#8212;": "—",
    "&#038;": "&",
  };
  return value
    .replace(/&(amp|quot|apos|lt|gt|nbsp);|&#0?39;|&#8211;|&#8212;|&#0?38;/g, (m) => named[m] ?? m)
    .replace(/&#(\d+);/g, (_, code: string) => String.fromCodePoint(Number(code)))
    .replace(/<[^>]+>/g, "")
    .trim();
}

function includesPattern(text: string, pattern: string): boolean {
  return text.toLocaleUpperCase("ja-JP").includes(pattern.toLocaleUpperCase("ja-JP"));
}

export function classifyBrands(title: string, tags: string[]): string[] {
  const source = [...tags, title].join(" ");
  return BRAND_ALIASES
    .filter(({ patterns }) => patterns.some((pattern) => includesPattern(source, pattern)))
    .map(({ label }) => label);
}

export function classifyModels(title: string): string[] {
  return MODEL_ALIASES
    .filter(({ patterns }) => patterns.some((pattern) => includesPattern(title, pattern)))
    .map(({ label }) => label);
}

/** App Runner /dashboard-analytics が返す正規化済み投稿。 */
interface AnalyticsPost {
  id: number;
  date: string;
  link: string;
  title: string;
  categories: string[];
  tags: string[];
  status: "publish" | "draft" | "future";
  origin: PostOrigin;
  brand: string;
}

interface RawWPRendered { rendered: string }
interface RawWPPost {
  id: number;
  date: string;
  link: string;
  title: RawWPRendered;
  categories: number[];
  tags: number[];
}
interface RawWPTerm { id: number; name: string }

interface AppPost {
  id: number;
  date: string;
  link: string;
  title: RawWPRendered;
  categories: number[];
  tags: number[];
  status: "publish" | "draft" | "future";
  brand?: string;
}

async function wpFetch<T>(url: string): Promise<{ data: T; headers: Headers }> {
  const response = await fetch(url, {
    next: { revalidate: REVALIDATE_SECONDS },
    // firekids は nginx で国外 IP を遮断するため、東京リージョン実行前提で直接取得する。
    headers: { Accept: "application/json", "User-Agent": "FireKidsDashboard/1.0" },
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return { data: await response.json() as T, headers: response.headers };
}

async function fetchWpTermMap(endpoint: "categories" | "tags"): Promise<Map<number, string>> {
  const map = new Map<number, string>();
  for (let page = 1; page <= 10; page += 1) {
    const { data, headers } = await wpFetch<RawWPTerm[]>(
      `${WP_API_BASE}/${endpoint}?per_page=100&page=${page}&_fields=id,name`,
    );
    data.forEach((term) => map.set(term.id, decodeHtml(term.name)));
    if (page >= Math.max(1, Number(headers.get("X-WP-TotalPages") ?? "1"))) break;
  }
  return map;
}

async function fetchWpPublishedPosts(): Promise<RawWPPost[]> {
  const fields = "id,date,link,title,categories,tags";
  const first = await wpFetch<RawWPPost[]>(
    `${WP_API_BASE}/posts?per_page=100&page=1&status=publish&_fields=${fields}`,
  );
  const totalPages = Math.max(1, Number(first.headers.get("X-WP-TotalPages") ?? "1"));
  const rest = await Promise.all(
    Array.from({ length: totalPages - 1 }, (_, i) =>
      wpFetch<RawWPPost[]>(`${WP_API_BASE}/posts?per_page=100&page=${i + 2}&status=publish&_fields=${fields}`)
        .then((r) => r.data),
    ),
  );
  return first.data.concat(...rest);
}

/** App Runner から、このアプリが投稿した記事（draft/future 含む）を取得する。 */
async function fetchAppPosts(): Promise<AppPost[]> {
  const token = process.env.DASHBOARD_API_TOKEN;
  if (!token) throw new Error("DASHBOARD_API_TOKEN が未設定です");
  const response = await fetch(`${GENERATOR_BASE}/dashboard-posts`, {
    next: { revalidate: REVALIDATE_SECONDS },
    headers: { Accept: "application/json", "X-Dashboard-Token": token },
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  const body = await response.json() as { posts?: AppPost[] };
  return (body.posts ?? []).filter((post) => Number.isInteger(post.id));
}

/** App Runner の集計エンドポイント（フォールバック用）。 */
async function fetchAnalyticsFallback(): Promise<AnalyticsPost[]> {
  const token = process.env.DASHBOARD_API_TOKEN;
  if (!token) throw new Error("DASHBOARD_API_TOKEN が未設定です");
  const response = await fetch(`${GENERATOR_BASE}/dashboard-analytics`, {
    next: { revalidate: REVALIDATE_SECONDS },
    headers: { Accept: "application/json", "X-Dashboard-Token": token },
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  const body = await response.json() as { posts?: AnalyticsPost[] };
  return (body.posts ?? []).filter((post) => Number.isInteger(post.id));
}

function toPublishedPost(params: {
  id: number;
  title: string;
  link: string;
  date: string;
  categoryNames: string[];
  tagNames: string[];
  origin: PostOrigin;
  status: "publish" | "draft" | "future";
}): PublishedPost {
  const models = classifyModels(params.title);
  return {
    id: params.id,
    title: params.title,
    link: params.link,
    date: (params.date ?? "").replace(/\./g, "-"),
    categories: params.categoryNames.filter(Boolean),
    brands: classifyBrands(params.title, params.tagNames),
    models: models.length > 0 ? models : ["その他"],
    origin: params.origin,
    status: params.status,
  };
}

export async function getPublishedPosts(): Promise<PublishedPostsResult> {
  const errors: string[] = [];

  // 主経路: 東京リージョン実行から WordPress を直接取得（国外 IP 遮断を回避）。
  try {
    const [wpPosts, categoryMap, tagMap, appResult] = await Promise.all([
      fetchWpPublishedPosts(),
      fetchWpTermMap("categories"),
      fetchWpTermMap("tags"),
      fetchAppPosts()
        .then((posts) => ({ posts, available: true }))
        .catch((error: unknown) => {
          errors.push(`アプリ投稿の判定データを取得できませんでした: ${error instanceof Error ? error.message : String(error)}`);
          return { posts: [] as AppPost[], available: false };
        }),
    ]);

    const appIds = new Set(appResult.posts.map((post) => post.id));
    const merged = new Map<number, PublishedPost>();

    wpPosts.forEach((post) => {
      const tagNames = post.tags.map((id) => tagMap.get(id) ?? "").filter(Boolean);
      merged.set(post.id, toPublishedPost({
        id: post.id,
        title: decodeHtml(post.title.rendered),
        link: post.link,
        date: post.date,
        categoryNames: post.categories.map((id) => categoryMap.get(id) ?? ""),
        tagNames,
        origin: appIds.has(post.id) ? "app" : "existing",
        status: "publish",
      }));
    });

    // draft/future のアプリ投稿を追加・上書き
    appResult.posts.forEach((post) => {
      const tagNames = post.tags.map((id) => tagMap.get(id) ?? "").filter(Boolean);
      if (post.brand) tagNames.push(post.brand);
      merged.set(post.id, toPublishedPost({
        id: post.id,
        title: decodeHtml(post.title.rendered),
        link: post.link,
        date: post.date,
        categoryNames: post.categories.map((id) => categoryMap.get(id) ?? ""),
        tagNames,
        origin: "app",
        status: post.status ?? "draft",
      }));
    });

    const posts = [...merged.values()].sort((a, b) => b.date.localeCompare(a.date));
    return {
      posts,
      appClassificationAvailable: appResult.available,
      errors,
      fetchedAt: new Date().toISOString(),
    };
  } catch (primaryError) {
    // フォールバック: App Runner の集計 API（少なくともアプリ投稿は表示できる）。
    errors.push(`WordPressへ直接到達できませんでした: ${primaryError instanceof Error ? primaryError.message : String(primaryError)}`);
    try {
      const fallback = await fetchAnalyticsFallback();
      const posts = fallback.map((post) => toPublishedPost({
        id: post.id,
        title: decodeHtml(post.title),
        link: post.link,
        date: post.date,
        categoryNames: (post.categories ?? []).map((name) => decodeHtml(name)),
        tagNames: [...(post.tags ?? []).map((t) => decodeHtml(t)), post.brand].filter(Boolean) as string[],
        origin: post.origin === "app" ? "app" : "existing",
        status: post.status ?? "publish",
      })).sort((a, b) => b.date.localeCompare(a.date));
      return {
        posts,
        appClassificationAvailable: true,
        errors,
        fetchedAt: new Date().toISOString(),
      };
    } catch (fallbackError) {
      errors.push(`フォールバック取得にも失敗しました: ${fallbackError instanceof Error ? fallbackError.message : String(fallbackError)}`);
      return {
        posts: [],
        appClassificationAvailable: false,
        errors,
        fetchedAt: new Date().toISOString(),
      };
    }
  }
}
