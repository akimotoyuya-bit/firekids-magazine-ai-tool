import type { ArticleContent, ValidationIssue, ValidationResult } from "./types";

// FK番号パターン: FK + 6桁数字
const FK_NUMBER_RE = /FK\d{6}/g;

// 価格表現パターン（円・万円・ドル・ユーロ等）
const PRICE_RE =
  /[\d,，]+\s*(?:円|万円|ドル|USD|EUR|万|千円)|(?:約|定価|相場|参考価格|販売価格|中古価格|買取価格).{0,20}(?:円|万)/g;

// 個別商品URLパターン（/products/detail や /products/{id} など）
const INDIVIDUAL_URL_RE =
  /https?:\/\/(?:firekids\.jp|m\.firekids\.jp)\/products\/(?:detail|[^l][^\s"'>]*)/g;

// UTMパラメータ不足チェック（CTAリンクにUTMがない）
const CTA_URL_RE =
  /https?:\/\/firekids\.jp\/products\/list\?category_id=\d+([^\s"'>]*)/g;

// 擬似エピソード表現
const AI_EPISODE_PATTERNS = [
  /時計売り場で.{0,30}声を聞く/,
  /店頭で.{0,20}相談/,
  /店員から.{0,20}聞かれる/,
  /お客様によく質問/,
  /時計に興味を持ち始めた方からよく聞かれる/,
  /時計屋として/,
  /時計屋の目線で/,
  /時計屋にいると/,
];

// 外部サイト言及
const EXTERNAL_SOURCE_PATTERNS = [
  /Wikipedia/i,
  /Ranfft/i,
  /Watchpedia/i,
  /CHRONOBLE/i,
  /ジャックロード/,
  /GINZA RASIN/i,
  /ゼンマイのここ東京/,
  /セイコーミュージアム/,
];

// 禁止語気
const FORBIDDEN_TONE_PATTERNS = [
  { re: /断言します|断言できます/, label: "強い断定調（断言します）" },
  { re: /はっきり言って/, label: "強い断定調（はっきり言って）" },
  { re: /正直に言います|本音で言えば|本音です/, label: "権威づけ表現" },
  { re: /避けるべきです|選ぶべきです/, label: "命令調「べき」" },
  { re: /絶対に.{0,10}ません/, label: "過度な強調（絶対に〜ません）" },
  {
    re: /この記事にたどり着いた方|検索してこの記事を読んでいる方/,
    label: "検索行動言及",
  },
  {
    re: /「.{2,20}」で検索している方/,
    label: "検索クエリ言及",
  },
];

function extractLines(content: string): string[] {
  return content.split("\n");
}

function findIssues(content: string, fileType: "txt" | "html"): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const lines = extractLines(content);

  // FK番号チェック
  lines.forEach((line, i) => {
    const matches = line.match(FK_NUMBER_RE);
    if (matches) {
      issues.push({
        type: "fk_number",
        severity: "error",
        message: `FK番号が含まれています: ${matches.join(", ")}`,
        line: i + 1,
        excerpt: line.trim().slice(0, 100),
      });
    }
  });

  // 価格表現チェック
  lines.forEach((line, i) => {
    const matches = line.match(PRICE_RE);
    if (matches) {
      issues.push({
        type: "price",
        severity: "error",
        message: `価格表現が含まれています: ${matches.join(", ")}`,
        line: i + 1,
        excerpt: line.trim().slice(0, 100),
      });
    }
  });

  // 個別商品URLチェック
  lines.forEach((line, i) => {
    const matches = line.match(INDIVIDUAL_URL_RE);
    if (matches) {
      issues.push({
        type: "individual_url",
        severity: "error",
        message: `個別商品URLが含まれています: ${matches.join(", ")}`,
        line: i + 1,
        excerpt: line.trim().slice(0, 100),
      });
    }
  });

  // CTAリンクのUTM不足チェック
  lines.forEach((line, i) => {
    let m: RegExpExecArray | null;
    const re = new RegExp(CTA_URL_RE.source, "g");
    while ((m = re.exec(line)) !== null) {
      const params = m[1] || "";
      if (!params.includes("utm_source")) {
        issues.push({
          type: "missing_utm",
          severity: "warning",
          message: `CTAリンクにUTMパラメータがありません: ${m[0].slice(0, 60)}`,
          line: i + 1,
          excerpt: line.trim().slice(0, 100),
        });
      }
    }
  });

  // 擬似エピソード表現チェック
  lines.forEach((line, i) => {
    for (const pattern of AI_EPISODE_PATTERNS) {
      if (pattern.test(line)) {
        issues.push({
          type: "ai_episode",
          severity: "error",
          message: `擬似エピソード表現が含まれています`,
          line: i + 1,
          excerpt: line.trim().slice(0, 100),
        });
        break;
      }
    }
  });

  // 外部ソース言及チェック
  lines.forEach((line, i) => {
    for (const pattern of EXTERNAL_SOURCE_PATTERNS) {
      if (pattern.test(line)) {
        issues.push({
          type: "external_source",
          severity: "warning",
          message: `外部ソースへの言及があります（本文事実への採用は禁止）`,
          line: i + 1,
          excerpt: line.trim().slice(0, 100),
        });
        break;
      }
    }
  });

  // 禁止語気チェック
  lines.forEach((line, i) => {
    for (const { re, label } of FORBIDDEN_TONE_PATTERNS) {
      if (re.test(line)) {
        issues.push({
          type: "ai_episode",
          severity: "warning",
          message: `禁止語気: ${label}`,
          line: i + 1,
          excerpt: line.trim().slice(0, 100),
        });
        break;
      }
    }
  });

  // HTMLの場合: CTAボタンの存在チェック
  if (fileType === "html") {
    const hasCtaButton = content.includes("wp-block-button");
    if (!hasCtaButton) {
      issues.push({
        type: "missing_cta",
        severity: "warning",
        message: "CTAボタン（wp-block-button）が見つかりません",
      });
    }

    // JSON-LD の存在チェック
    if (!content.includes("application/ld+json")) {
      issues.push({
        type: "missing_cta",
        severity: "warning",
        message: "JSON-LD構造化データが見つかりません",
      });
    }
  }

  return issues;
}

export function validateArticle(article: ArticleContent): ValidationResult {
  const issues: ValidationIssue[] = [];

  if (article.txt) {
    issues.push(...findIssues(article.txt, "txt"));
  }
  if (article.html) {
    // HTML は TXT よりルールが厳しいため追加チェック
    const htmlIssues = findIssues(article.html, "html");
    // TXTと重複する行番号ベースのチェックは統合せず全部追加
    issues.push(...htmlIssues);
  }
  if (article.xPost) {
    // X投稿のUTMチェック: x UTM は utm_source=x
    const xLines = extractLines(article.xPost);
    xLines.forEach((line, i) => {
      const xCtaRe = /https?:\/\/firekids\.jp[^\s]*/g;
      let m: RegExpExecArray | null;
      while ((m = xCtaRe.exec(line)) !== null) {
        if (!m[0].includes("utm_source=x")) {
          issues.push({
            type: "missing_utm",
            severity: "warning",
            message: `X投稿のCTAリンクにUTMパラメータ(utm_source=x)がありません: ${m[0].slice(0, 60)}`,
            line: i + 1,
            excerpt: line.trim().slice(0, 100),
          });
        }
      }
    });
  }

  const errorCount = issues.filter((i) => i.severity === "error").length;
  const warningCount = issues.filter((i) => i.severity === "warning").length;

  // チェック項目数（主要8項目）
  const checkCount = 8;
  const passCount = Math.max(0, checkCount - errorCount);

  return {
    articleMeta: article.meta,
    issues,
    passCount,
    errorCount,
    warningCount,
  };
}
