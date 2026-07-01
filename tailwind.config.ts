import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        /* FIRE KIDS ブランドレッド */
        "fk-red":    "#DC2626",
        "fk-red-d":  "#B91C1C",
        "fk-red-bg": "#FEF2F2",
        /* テキスト */
        "fk-text":   "#0F172A",
        "fk-sub":    "#334155",
        "fk-muted":  "#94A3B8",
        /* 旧トークン（後方互換） */
        "fk-dark":   "#0F172A",
        "fk-brown":  "#5a5248",
        "fk-warm":   "#8b6f47",
        "fk-bg":     "#F8FAFC",
        "fk-border": "rgba(15,23,42,0.08)",
      },
      borderRadius: {
        "fk-sm":   "6px",
        "fk":      "10px",
        "fk-lg":   "18px",
        "fk-pill": "20px",
      },
      boxShadow: {
        "fk-card": "0 0 0 1px rgba(15,23,42,.08), 0 20px 50px rgba(15,23,42,.06)",
        "fk-hov":  "0 0 0 1px rgba(220,38,38,.12), 0 24px 56px rgba(15,23,42,.10)",
      },
    },
  },
  plugins: [],
};
export default config;
