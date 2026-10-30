/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { 50: "#EEF2FF", 100: "#E0E7FF", 200: "#C7D2FE", 300: "#A5B4FC", 400: "#818CF8", 500: "#6366F1",
                 600: "#4F46E5", 700: "#4338CA", 800: "#3730A3", 900: "#312E81" },
        surface: { DEFAULT: "#F8FAFC", card: "#FFFFFF", border: "#E2E8F0", subtle: "#F1F5F9" },
        sidebar: { DEFAULT: "#0B0F19", card: "#131B2E", border: "#1E293B", hover: "#182238" },
      },
      fontFamily: { sans: ["Inter", "sans-serif"], mono: ["JetBrains Mono", "monospace"] },
    },
  },
  plugins: [],
};
