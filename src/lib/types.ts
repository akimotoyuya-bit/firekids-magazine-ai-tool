export type Brand =
  | "BREITLING"
  | "CARTIER"
  | "CITIZEN"
  | "IWC"
  | "JLC"
  | "LONGINES"
  | "OMEGA"
  | "ORIENT"
  | "OTHER"
  | "ROLEX"
  | "SEIKO"
  | "THEME"
  | "TUDOR"
  | "UNIVERSAL"
  | "VACHERON";

export const BRANDS: Brand[] = [
  "ROLEX",
  "OMEGA",
  "SEIKO",
  "CITIZEN",
  "IWC",
  "JLC",
  "LONGINES",
  "TUDOR",
  "BREITLING",
  "CARTIER",
  "ORIENT",
  "UNIVERSAL",
  "VACHERON",
  "THEME",
  "OTHER",
];

export const BRAND_LABELS: Record<Brand, string> = {
  ROLEX: "ロレックス",
  OMEGA: "オメガ",
  SEIKO: "セイコー",
  CITIZEN: "シチズン",
  IWC: "IWC",
  JLC: "ジャガー・ルクルト",
  LONGINES: "ロンジン",
  TUDOR: "チューダー",
  BREITLING: "ブライトリング",
  CARTIER: "カルティエ",
  ORIENT: "オリエント",
  UNIVERSAL: "ユニバーサルジュネーブ",
  VACHERON: "ヴァシュロン・コンスタンタン",
  THEME: "テーマ記事",
  OTHER: "その他",
};

export interface ArticleMeta {
  brand: Brand;
  slug: string;
  number: string;
  filename: string;
  hasTxt: boolean;
  hasHtml: boolean;
  hasXPost: boolean;
  hasXImage: boolean;
  isPosted: boolean;
}

export interface ArticleContent {
  meta: ArticleMeta;
  txt?: string;
  html?: string;
  xPost?: string;
}

export interface ValidationIssue {
  type:
    | "fk_number"
    | "price"
    | "individual_url"
    | "missing_utm"
    | "missing_cta"
    | "missing_canonical_note"
    | "ai_episode"
    | "lifestyle_link"
    | "external_source";
  severity: "error" | "warning";
  message: string;
  line?: number;
  excerpt?: string;
}

export interface ValidationResult {
  articleMeta: ArticleMeta;
  issues: ValidationIssue[];
  passCount: number;
  errorCount: number;
  warningCount: number;
}

export interface WPDryRunPayload {
  title: string;
  content: string;
  status: "draft" | "publish" | "future";
  date?: string;
  categories?: string[];
  tags?: string[];
  slug?: string;
}
