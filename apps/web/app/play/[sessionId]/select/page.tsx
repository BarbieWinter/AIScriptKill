"use client";

export default function CharacterSelectPage() {
  return (
    <main className="min-h-screen bg-[var(--background)]">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-center px-6 py-12">
        <h1 className="mb-2 text-3xl font-bold">选择你的身份</h1>
        <p className="mb-12 text-[var(--muted-foreground)]">
          你将扮演其中一名角色，在雪乡中寻找真相
        </p>

        {/* 角色选择 */}
        <div className="mb-12 flex gap-4 overflow-x-auto pb-4">
          {[
            { id: "zhuosiyuan", name: "卓司元", tagline: "我是个普通的游客……" },
            { id: "cuikaiqiang", name: "崔铠强", tagline: "这村子有问题。" },
            { id: "likaiin", name: "李开心", tagline: "大家冷静一下！" },
            { id: "wangqi", name: "王琪", tagline: "我昨晚看到了什么……" },
            { id: "xiaomeng", name: "萧萌", tagline: "别吓我啊！" },
            { id: "chenji", name: "陈吉", tagline: "呵呵，有意思。" },
          ].map((char) => (
            <button
              key={char.id}
              className="group flex min-w-[200px] flex-col items-center rounded-xl border border-[var(--border)] p-6 transition-all hover:border-[var(--theme-primary)] hover:shadow-lg hover:shadow-[var(--theme-primary)]/10"
            >
              <div className="mb-4 h-32 w-32 rounded-full bg-gradient-to-br from-[var(--theme-primary)]/30 to-[var(--theme-accent)]/30 transition-transform group-hover:scale-105" />
              <h3 className="mb-2 text-lg font-bold">{char.name}</h3>
              <p className="text-center text-sm italic text-[var(--muted-foreground)]">
                &ldquo;{char.tagline}&rdquo;
              </p>
            </button>
          ))}
        </div>

        <button className="rounded-xl bg-[var(--theme-primary)] px-12 py-4 text-lg font-bold transition-all hover:bg-[var(--theme-primary)]/80">
          确定选择
        </button>
      </div>
    </main>
  );
}
