"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, Check, UserRound } from "lucide-react";
import { toast } from "sonner";

import { api, type PlayableCharacter } from "@/lib/api";

const characterColors = [
  "#8fae98",
  "#b59b68",
  "#8b9fba",
  "#b18484",
  "#9e91b2",
  "#7fa6a1",
];

const characterPortraits: Record<string, string> = {
  zhuosiyuan: "/snow-village/characters/zhuosiyuan.png",
  xiaomeng: "/snow-village/characters/xiaomeng.png",
  wangqi: "/snow-village/characters/wangqi.png",
  likaixin: "/snow-village/characters/likaixin.png",
  cuikaiqiang: "/snow-village/characters/cuikaiqiang.png",
  chengjun: "/snow-village/characters/chengjun.png",
  chenji: "/snow-village/characters/chenji.png",
};

export default function CharacterSelectPage() {
  const router = useRouter();
  const params = useParams<{ sessionId: string }>();
  const scriptId = params.sessionId;
  const [characters, setCharacters] = useState<PlayableCharacter[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loadingCharacters, setLoadingCharacters] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [creatingCharacterId, setCreatingCharacterId] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    setLoadingCharacters(true);
    setLoadError(null);

    api
      .getPlayableCharacters(scriptId)
      .then(({ characters: playableCharacters }) => {
        if (!current) return;
        setCharacters(playableCharacters);
        setSelectedId(playableCharacters[0]?.id ?? null);
      })
      .catch((error) => {
        if (!current) return;
        console.error("[CharacterSelectPage] 加载可玩角色失败:", error);
        setLoadError("无法读取这个剧本的可选角色");
      })
      .finally(() => {
        if (current) setLoadingCharacters(false);
      });

    return () => {
      current = false;
    };
  }, [scriptId]);

  const selectedCharacter = useMemo(
    () => characters.find((character) => character.id === selectedId) ?? null,
    [characters, selectedId],
  );
  const selectedIndex = Math.max(
    0,
    characters.findIndex((character) => character.id === selectedId),
  );
  const selectedColor = characterColors[selectedIndex % characterColors.length];

  const handleSelect = async () => {
    if (!selectedCharacter || creatingCharacterId) return;

    setCreatingCharacterId(selectedCharacter.id);
    try {
      const session = await api.createSession(
        scriptId,
        selectedCharacter.id,
        selectedCharacter.name,
      );
      toast("身份已确认", {
        description: `你将以${selectedCharacter.name}的身份进入剧本`,
      });
      router.replace(
        `/play/${encodeURIComponent(session.script_id)}/${encodeURIComponent(session.session_id)}`,
      );
    } catch (error) {
      console.error("[CharacterSelectPage] 创建会话失败:", error);
      toast.error("无法创建游戏会话", {
        description: "请确认后端服务与当前剧本包已经就绪。",
      });
      setCreatingCharacterId(null);
    }
  };

  if (loadingCharacters) {
    return (
      <main className="grid min-h-screen place-items-center bg-[var(--background)]">
        <div className="text-center">
          <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-[var(--theme-primary)] border-t-transparent" />
          <p className="text-sm text-[var(--muted-foreground)]">正在读取可选角色</p>
        </div>
      </main>
    );
  }

  if (loadError || characters.length === 0 || !selectedCharacter) {
    return (
      <main className="grid min-h-screen place-items-center bg-[var(--background)] px-6">
        <div className="max-w-sm text-center">
          <h1 className="mb-2 text-xl font-semibold">暂无可选角色</h1>
          <p className="mb-6 text-sm text-[var(--muted-foreground)]">
            {loadError ?? "这个剧本尚未声明可由玩家扮演的角色。"}
          </p>
          <button
            type="button"
            onClick={() => router.back()}
            className="rounded border border-white/10 px-5 py-2 text-sm text-white/70 hover:text-white"
          >
            返回剧本
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="relative min-h-screen overflow-x-hidden bg-[var(--background)] text-white">
      <div
        className="pointer-events-none absolute inset-0 opacity-70"
        style={{
          background: `radial-gradient(circle at 50% 0%, ${selectedColor}24, transparent 46%)`,
        }}
      />

      <button
        type="button"
        onClick={() => router.back()}
        className="fixed left-4 top-4 z-20 grid h-9 w-9 place-items-center border border-white/10 bg-black/55 text-white/60 transition-colors hover:text-white"
        aria-label="返回剧本"
      >
        <ArrowLeft className="h-4 w-4" />
      </button>

      <div className="relative z-10 mx-auto flex min-h-screen w-full max-w-6xl flex-col px-5 pb-10 pt-16 md:px-8 md:pt-20">
        <header className="mb-7 text-center">
          <p className="mb-2 text-xs text-white/35">选择你的身份</p>
          <h1 className="text-2xl font-semibold md:text-3xl">可扮演角色</h1>
          <p className="mt-2 text-sm text-white/40">{characters.length} 个身份</p>
        </header>

        <section
          className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6"
          aria-label="可扮演角色列表"
        >
          {characters.map((character, index) => {
            const active = character.id === selectedCharacter.id;
            const color = characterColors[index % characterColors.length];
            const portraitSrc =
              characterPortraits[character.id] || character.portrait_url;
            return (
              <motion.button
                type="button"
                key={character.id}
                onClick={() => setSelectedId(character.id)}
                whileHover={{ y: -3 }}
                whileTap={{ scale: 0.98 }}
                className={`relative flex min-h-40 flex-col items-center justify-center border px-3 py-5 text-center transition-colors ${
                  active
                    ? "border-white/30 bg-white/10"
                    : "border-white/8 bg-white/[0.025] hover:border-white/18 hover:bg-white/[0.05]"
                }`}
                aria-pressed={active}
              >
                {active && (
                  <span className="absolute right-2 top-2 grid h-5 w-5 place-items-center rounded-full bg-white text-black">
                    <Check className="h-3 w-3" />
                  </span>
                )}
                <span
                  className="mb-3 grid h-16 w-16 place-items-center overflow-hidden rounded-full border"
                  style={{
                    borderColor: `${color}66`,
                    backgroundColor: `${color}18`,
                    color,
                  }}
                >
                  {portraitSrc ? (
                    <Image
                      src={portraitSrc}
                      alt={`${character.name}头像`}
                      width={64}
                      height={64}
                      className="h-full w-full object-cover object-center"
                    />
                  ) : (
                    <UserRound className="h-7 w-7" />
                  )}
                </span>
                <strong className="text-sm font-medium">{character.name}</strong>
                <span className="mt-1 line-clamp-2 min-h-8 text-xs leading-4 text-white/35">
                  {character.personality || "等待进入剧本"}
                </span>
              </motion.button>
            );
          })}
        </section>

        <motion.section
          key={selectedCharacter.id}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mx-auto grid w-full max-w-4xl gap-6 border-y border-white/10 py-7 md:grid-cols-[180px_1fr] md:items-center md:gap-10"
        >
          <div className="mx-auto grid h-36 w-36 place-items-center overflow-hidden rounded-full border md:h-40 md:w-40" style={{ borderColor: `${selectedColor}55`, backgroundColor: `${selectedColor}12`, color: selectedColor }}>
            {characterPortraits[selectedCharacter.id] || selectedCharacter.portrait_url ? (
              <Image
                src={characterPortraits[selectedCharacter.id] || selectedCharacter.portrait_url}
                alt={`${selectedCharacter.name}头像`}
                width={160}
                height={160}
                className="h-full w-full object-cover object-center"
              />
            ) : (
              <UserRound className="h-14 w-14" />
            )}
          </div>
          <div className="text-center md:text-left">
            <h2 className="text-3xl font-semibold">{selectedCharacter.name}</h2>
            {selectedCharacter.tagline && (
              <p className="mt-2 text-sm italic text-white/55">“{selectedCharacter.tagline}”</p>
            )}
            {selectedCharacter.personality && (
              <p className="mt-4 text-sm" style={{ color: selectedColor }}>
                {selectedCharacter.personality}
              </p>
            )}
            {selectedCharacter.background && (
              <p className="mt-3 text-sm leading-7 text-white/45">
                {selectedCharacter.background}
              </p>
            )}
          </div>
        </motion.section>

        <div className="mt-8 flex justify-center">
          <button
            type="button"
            onClick={() => void handleSelect()}
            disabled={creatingCharacterId !== null}
            className="inline-flex min-w-56 items-center justify-center gap-2 bg-[var(--theme-primary)] px-8 py-3.5 text-sm font-semibold text-white transition-colors hover:bg-[var(--theme-primary)]/80 disabled:opacity-55"
          >
            {creatingCharacterId ? (
              <>
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                正在进入剧本
              </>
            ) : (
              <>
                <Check className="h-4 w-4" />
                以{selectedCharacter.name}的身份开始
              </>
            )}
          </button>
        </div>
      </div>
    </main>
  );
}
