/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Manrope Variable"', "Manrope", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
      colors: {
        pine: {
          50: "#eef6f4", 100: "#d6ebe6", 200: "#acd7cd", 300: "#7bbcae", 400: "#4c9d8d", 500: "#2a8170",
          600: "#1d6a5c", 700: "#17564b", 800: "#13443c", 900: "#0f3530", 950: "#0a2420",
        },
        ember: { 50: "#fdf3ee", 100: "#fae1d4", 500: "#d2612f", 600: "#b44f22", 700: "#8f3e1b" },
        status: { good: "#0ca30c", warning: "#fab219", serious: "#ec835a", critical: "#d03b3b" },
        series: { 1: "#2a78d6", 2: "#eb6834", 3: "#1baf7a" },
      },
      boxShadow: {
        card: "0 1px 2px rgba(16, 24, 22, 0.05), 0 0 0 1px rgba(16, 24, 22, 0.06)",
        pop: "0 10px 30px -10px rgba(16, 24, 22, 0.25), 0 0 0 1px rgba(16, 24, 22, 0.08)",
      },
      keyframes: {
        in: { from: { opacity: 0, transform: "translateY(4px)" }, to: { opacity: 1, transform: "none" } },
      },
      animation: { in: "in 160ms ease-out" },
    },
  },
  plugins: [],
};
