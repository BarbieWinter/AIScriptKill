"use client";

export default function ReviewPage() {
  return (
    <main className="min-h-screen bg-[var(--background)]">
      <div className="mx-auto max-w-3xl px-6 py-12">
        <h1 className="mb-2 text-3xl font-bold">案件复盘</h1>
        <p className="mb-12 text-[var(--muted-foreground)]">你的推理历程回顾</p>

        {/* 评分总览 */}
        <section className="mb-8 rounded-xl border border-[var(--border)] p-8 text-center">
          <div className="mb-2 text-5xl font-bold text-[var(--theme-primary)]">85</div>
          <div className="mb-4 text-lg text-[var(--muted-foreground)]">推理评分 · S 级</div>
          <div className="text-sm text-[var(--muted-foreground)]">用时 68 分钟</div>
        </section>

        {/* 正确/错误 */}
        <div className="mb-8 grid grid-cols-2 gap-4">
          <section className="rounded-xl border border-[var(--border)] p-6">
            <h3 className="mb-3 text-sm font-bold text-[var(--success)]">✓ 正确</h3>
            <p className="mb-2 text-sm">真凶: 程俊</p>
            <p className="text-sm">动机: 复仇</p>
          </section>
          <section className="rounded-xl border border-[var(--border)] p-6">
            <h3 className="mb-3 text-sm font-bold text-[var(--warning)]">○ 遗漏</h3>
            <p className="text-sm text-[var(--muted-foreground)]">关键线索: 隐藏的信</p>
          </section>
        </div>

        {/* 真相摘要 */}
        <section className="mb-8 rounded-xl border border-[var(--border)] p-6">
          <h3 className="mb-4 text-lg font-bold">真相摘要</h3>
          <p className="leading-relaxed text-[var(--muted-foreground)]">
            程俊为了多年前的冤案，化名王大达潜伏在雪乡……
          </p>
        </section>

        <div className="flex justify-center gap-4">
          <button className="rounded-xl border border-[var(--border)] px-8 py-3 transition-colors hover:bg-[var(--accent)]">
            再来一次
          </button>
          <button className="rounded-xl bg-[var(--theme-primary)] px-8 py-3 font-bold transition-colors hover:bg-[var(--theme-primary)]/80">
            分享结果
          </button>
        </div>
      </div>
    </main>
  );
}
