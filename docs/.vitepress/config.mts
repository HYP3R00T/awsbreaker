import { defineConfig } from "vitepress";

// https://vitepress.dev/reference/site-config
export default defineConfig({
  title: "AWS Breaker",
  description: "A kill-switch for AWS",
  themeConfig: {
    // https://vitepress.dev/reference/default-theme-config
    nav: [
      { text: "Home", link: "/" },
      { text: "Guide", link: "/guide/what-is-costcutter" },
    ],

    sidebar: [
      {
        text: "Introduction",
        items: [
          { text: "What is CostCutter?", link: "/guide/what-is-costcutter" },
          { text: "Getting Started", link: "/guide/getting-started" },
          { text: "Usage (CLI)", link: "/usage-cli" },
        ],
      },
      {
        text: "Reference",
        items: [{ text: "Config Reference", link: "/guide/config-reference" }],
      },
    ],

    socialLinks: [
      { icon: "github", link: "https://github.com/HYP3R00T/costcutter" },
    ],
  },
});
