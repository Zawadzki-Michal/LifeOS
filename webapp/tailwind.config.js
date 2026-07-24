/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        raised: "var(--surface-raised)",
        border: "var(--border)",
        "border-strong": "var(--border-strong)",
        ink: "var(--text-primary)",
        muted: "var(--text-secondary)",
        faint: "var(--text-muted)",
        accent: "rgb(var(--accent-rgb) / <alpha-value>)",
        "accent-strong": "var(--accent-strong)",
        danger: "rgb(var(--danger-rgb) / <alpha-value>)",
        "danger-bg": "var(--danger-bg)",
      },
    },
  },
  plugins: [],
};
