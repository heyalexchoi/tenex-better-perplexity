/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          900: "#0f1417",
          800: "#172026",
          700: "#23313a",
          100: "#e8eef2",
        },
        fog: {
          50: "#f7f8f8",
          100: "#eef1f2",
          200: "#d7dee2",
          400: "#9fb0b8",
        },
        accent: {
          500: "#1f8aa6",
          600: "#14748e",
        },
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(31,138,166,0.3), 0 10px 30px rgba(15,20,23,0.2)",
      },
      fontFamily: {
        display: ["\"DM Serif Display\"", "serif"],
        body: ["\"Space Grotesk\"", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
}
