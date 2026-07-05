import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI 沉浸式悬疑互动剧",
  description: "基于固定精品剧本的 AI 沉浸式悬疑互动游戏",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" className="dark">
      <body className="min-h-screen bg-[var(--background)] text-[var(--foreground)] antialiased">
        {children}
      </body>
    </html>
  );
}
