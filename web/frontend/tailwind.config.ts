import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        cyan: { DEFAULT: "#00bfff" },
        green: { DEFAULT: "#00ff99" },
        bg: "#080808",
        surface: "#111111",
        border: "#1e1e1e",
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
