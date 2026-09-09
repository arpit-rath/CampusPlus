import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#14181D",
        signal: "#C9711F",
        calm: "#1F7B6C",
        critical: "#B4402F",
      },
    },
  },
  plugins: [],
} satisfies Config;
