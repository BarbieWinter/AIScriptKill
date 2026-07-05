"use client";

import type { Metadata } from "next";
import "./globals.css";
import { Toaster } from "sonner";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, useEffect } from "react";

// export const metadata: Metadata = {
//   title: "AI 沉浸式悬疑互动剧",
//   description: "基于固定精品剧本的 AI 沉浸式悬疑互动游戏",
// };

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <html lang="zh-CN" className="dark">
      <body className="min-h-screen bg-[var(--background)] text-[var(--foreground)] antialiased">
        <QueryClientProvider client={queryClient}>
          {children}
          <Toaster
            position="bottom-right"
            toastOptions={{
              style: {
                background: "var(--accent)",
                color: "var(--foreground)",
                border: "1px solid var(--border)",
              },
            }}
          />
        </QueryClientProvider>
      </body>
    </html>
  );
}
