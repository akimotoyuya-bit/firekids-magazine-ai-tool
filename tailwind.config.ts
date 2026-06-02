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
        "fk-dark": "#1a1a1a",
        "fk-brown": "#5a5248",
        "fk-warm": "#8b6f47",
        "fk-accent": "#E67E22",
        "fk-bg": "#faf6ee",
        "fk-border": "#e8e4de",
      },
    },
  },
  plugins: [],
};
export default config;
