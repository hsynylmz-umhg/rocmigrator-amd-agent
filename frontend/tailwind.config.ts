import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        background: "#230D11",
        foreground: "#DEE2E3",
        brand: {
          bordeaux: "#541823",
          taupe: "#836B69",
          khaki: "#B6A18C",
          mocha: "#523F38",
        },
      },
    },
  },
} satisfies Config;
