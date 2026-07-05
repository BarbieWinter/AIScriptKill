"use client";

import { useParams } from "next/navigation";

export default function ScriptDetailPage() {
  const params = useParams();
  const scriptId = params.id as string;

  return (
    <main className="min-h-screen bg-[var(--background)]">
      <div className="mx-auto max-w-4xl px-6 py-8">
        <a
          href="/library"
          className="mb-8 inline-flex items-center gap-2 text-sm text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
        >
          ← 返回剧本库
        </a>

        {/* 标题区 */}
        <section className="mb-12">
          <h1 className="mb-4 text-4xl font-bold">雪乡连环杀人事件</h1>
          <div className="mb-6 flex flex-wrap gap-4 text-sm text-[var(--muted-foreground)]">
            <span>★★★☆☆ 难度 3/5</span>
            <span>约 120 分钟</span>
            <span className="rounded-full border border-[var(--border)] px-3 py-1">悬疑</span>
            <span className="rounded-full border border-[var(--border)] px-3 py-1">推理</span>
            <span className="rounded-full border border-[var(--border)] px-3 py-1">惊悚</span>
          </div>
        </section>

        {/* 故事简介 */}
        <section className="mb-12">
          <h2 className="mb-4 text-xl font-bold">故事简介</h2>
          <p className="leading-relaxed text-[var(--muted-foreground)]">
            雪乡，一个被大雪覆盖的东北村庄。
            除夕夜，村民们正沉浸在节日的喜悦中，
            村口饭店的老板王大达热情地招待着客人们。
            但一桩离奇的命案打破了这份宁静——
            有人在雪地中发现了一具尸体。
            玩家将扮演六名游客之一，
            通过调查、对话、推理，揭开雪乡隐藏多年的秘密……
          </p>
        </section>

        {/* 角色预览 */}
        <section className="mb-12">
          <h2 className="mb-6 text-xl font-bold">角色预览</h2>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
            {["卓司元", "崔铠强", "李开心", "王琪", "萧萌", "陈吉"].map((name) => (
              <div
                key={name}
                className="group cursor-pointer rounded-xl border border-[var(--border)] p-4 text-center transition-all hover:border-[var(--theme-primary)]"
              >
                <div className="mx-auto mb-3 h-20 w-20 rounded-full bg-gradient-to-br from-[var(--theme-primary)]/30 to-[var(--theme-accent)]/30" />
                <p className="text-sm font-bold">{name}</p>
              </div>
            ))}
          </div>
        </section>

        {/* 开始按钮 */}
        <div className="text-center">
          <a
            href={`/play/${scriptId}/select`}
            className="inline-block rounded-xl bg-[var(--theme-primary)] px-12 py-4 text-lg font-bold transition-all hover:bg-[var(--theme-primary)]/80 hover:shadow-lg hover:shadow-[var(--theme-primary)]/30"
          >
            开始游戏
          </a>
        </div>
      </div>
    </main>
  );
}
