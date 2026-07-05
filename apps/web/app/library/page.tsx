"use client";

import { useEffect, useState } from "react";

export default function LibraryPage() {
  const [packages, setPackages] = useState<any[]>([]);

  useEffect(() => {
    // TODO: 从后端获取剧本包列表
    // GET /api/v1/packages
    setPackages([
      {
        id: "snow-village",
        title: "雪乡连环杀人事件",
        description: "雪乡，一个被大雪覆盖的东北村庄。新年将至，村子里却接连发生命案……",
        difficulty: 3,
        duration_minutes: 120,
        genre: ["悬疑", "推理", "惊悚"],
      },
    ]);
  }, []);

  return (
    <main className="min-h-screen bg-[var(--background)]">
      {/* 顶部导航 */}
      <header className="sticky top-0 z-50 border-b border-[var(--border)] bg-[var(--background)]/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <h1 className="text-lg font-bold tracking-wider text-[var(--theme-primary)]">
            AI 剧本杀
          </h1>
        </div>
      </header>

      {/* 主视觉横幅 */}
      <section className="relative h-[60vh] min-h-[400px] overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-[var(--background)]" />
        <div className="absolute inset-0 flex flex-col items-center justify-center px-6 text-center">
          <h2 className="mb-4 text-4xl font-bold tracking-wider md:text-6xl">
            雪乡连环杀人事件
          </h2>
          <p className="mb-8 max-w-2xl text-lg text-[var(--muted-foreground)]">
            雪乡，一个被大雪覆盖的东北村庄。
            <br />
            新年将至，村子里却接连发生命案……
          </p>
          <div className="flex gap-4">
            <span className="rounded-full border border-[var(--border)] px-4 py-1 text-sm text-[var(--muted-foreground)]">
              悬疑
            </span>
            <span className="rounded-full border border-[var(--border)] px-4 py-1 text-sm text-[var(--muted-foreground)]">
              推理
            </span>
            <span className="rounded-full border border-[var(--border)] px-4 py-1 text-sm text-[var(--muted-foreground)]">
              惊悚
            </span>
          </div>
        </div>
      </section>

      {/* 剧本库网格 */}
      <section className="mx-auto max-w-7xl px-6 py-12">
        <div className="mb-8 flex items-center justify-between">
          <h3 className="text-xl font-bold">剧本库</h3>
          <div className="flex gap-2">
            <button className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm transition-colors hover:bg-[var(--accent)]">
              难度筛选
            </button>
            <button className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm transition-colors hover:bg-[var(--accent)]">
              类型筛选
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {packages.map((pkg) => (
            <a
              key={pkg.id}
              href={`/library/${pkg.id}`}
              className="group rounded-xl border border-[var(--border)] bg-[var(--accent)] p-6 transition-all duration-300 hover:border-[var(--theme-primary)] hover:shadow-lg hover:shadow-[var(--theme-primary)]/10"
            >
              <div className="mb-4 aspect-[3/4] rounded-lg bg-gradient-to-br from-[var(--theme-primary)]/20 to-[var(--theme-accent)]/20" />
              <h4 className="mb-2 text-lg font-bold group-hover:text-[var(--theme-primary)]">
                {pkg.title}
              </h4>
              <p className="mb-4 line-clamp-2 text-sm text-[var(--muted-foreground)]">
                {pkg.description}
              </p>
              <div className="flex items-center justify-between text-sm text-[var(--muted-foreground)]">
                <span>{'★'.repeat(pkg.difficulty)}{'☆'.repeat(5 - pkg.difficulty)}</span>
                <span>{pkg.duration_minutes}分钟</span>
              </div>
            </a>
          ))}
        </div>
      </section>
    </main>
  );
}
