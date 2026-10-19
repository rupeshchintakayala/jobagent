/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"] },
      colors: { brand: { 400: "#818cf8", 500: "#6366f1", 600: "#4f46e5" } },
      keyframes: { float: { "0%,100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-8px)" } },
                   shimmer: { "100%": { transform: "translateX(100%)" } } },
      animation: { float: "float 6s ease-in-out infinite" },
    },
  },
  plugins: [],
};
