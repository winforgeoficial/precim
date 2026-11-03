/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { display: ["Fredoka", "system-ui", "sans-serif"], sans: ["Nunito", "system-ui", "sans-serif"] },
      colors: {
        cream: "#fff8ee", ink: "#3b2a2a", pig: "#ff9db1", pigdark: "#e8738c",
        mint: "#2fbf8f", gold: "#ffc53d", sky: "#6cb8ff",
      },
      boxShadow: { pop: "0 4px 0 0 rgba(59,42,42,.9)" },
      keyframes: {
        bob: { "0%,100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-6px)" } },
        sniff: { "0%,100%": { transform: "scale(1)" }, "50%": { transform: "scale(1.12)" } },
        zzz: { "0%": { opacity: "0", transform: "translate(0,0)" }, "50%": { opacity: "1" }, "100%": { opacity: "0", transform: "translate(8px,-14px)" } },
        sparkle: { "0%,100%": { opacity: "0.2", transform: "scale(.6)" }, "50%": { opacity: "1", transform: "scale(1.1)" } },
      },
      animation: { bob: "bob 1.2s ease-in-out infinite", sniff: "sniff .7s ease-in-out infinite", zzz: "zzz 2.4s ease-in-out infinite", sparkle: "sparkle 1s ease-in-out infinite" },
    },
  },
  plugins: [],
};
