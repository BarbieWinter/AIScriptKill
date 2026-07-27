"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  BookOpen,
  Check,
  CircleAlert,
  Eye,
  Lightbulb,
  LoaderCircle,
  MessageCircle,
  RotateCcw,
  Send,
  ShieldCheck,
  StepForward,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { GameplayPanelHost } from "@/components/demo/GameplayPanelHost";
import { MansionDemo, type LocalScenePose, type SceneAvatar } from "@/components/demo/MansionDemo";
import { Sheet } from "@/components/ui/Sheet";
import type { DemoSessionHotspot } from "@/lib/demo-data";
import {
  multiplayerErrorMessage,
  shouldRetryMultiplayer,
} from "@/lib/multiplayer/error-messages";
import {
  multiplayerReviewKey,
  MultiplayerClientError,
  roomSnapshotKey,
  type MultiplayerRoomClient,
} from "@/lib/multiplayer/room-client";
import type {
  GameplayHint,
  GameplayMaterial,
  GameplaySettlement,
  GameplaySnapshotV1,
  RoomCommandInput,
} from "@/lib/multiplayer/types";
import { createUuid } from "@/lib/uuid";

const phaseLabel = {
  read: "阅读角色信息",
  discuss: "公开讨论",
  settle: "提交判断",
  reveal: "查看结果",
} as const;

type ScenePanel = "chapters" | "materials" | "hints" | "discussion" | "settlement" | "review" | null;

const HINT_LEVEL_COUNT = 3;
const PRESENCE_SEND_INTERVAL = 500;
const PRESENCE_HEARTBEAT_INTERVAL = 5_000;
const spawnByCharacter: Record<string, { x: number; y: number }> = {
  investigator: { x: 1455, y: 970 },
  insider: { x: 945, y: 970 },
};

function playerName(snapshot: GameplaySnapshotV1, memberId: string) {
  return snapshot.players.find((player) => player.member_id === memberId)?.character_name ?? "同伴";
}

function sceneHotspots(snapshot: GameplaySnapshotV1): DemoSessionHotspot[] {
  const hotspots: DemoSessionHotspot[] = [
    {
      id: "multiplayer-chapters",
      sceneId: snapshot.stage_id,
      label: "角色手记",
      actionLabel: "阅读",
      x: 780,
      y: 1120,
    },
  ];

  if (snapshot.public_materials.length > 0) {
    hotspots.push({
      id: "multiplayer-materials",
      sceneId: snapshot.stage_id,
      label: snapshot.status === "completed" ? "终局档案" : "公开档案",
      actionLabel: "查阅",
      x: 2080,
      y: 1280,
    });
  }

  if (snapshot.status === "completed") {
    hotspots.push({
      id: "multiplayer-review",
      sceneId: snapshot.stage_id,
      label: "案件复盘",
      actionLabel: "复盘",
      x: 1500,
      y: 1150,
    });
  } else if (snapshot.phase === "discuss") {
    hotspots.push({
      id: "multiplayer-discussion",
      sceneId: snapshot.stage_id,
      label: "双人讨论室",
      actionLabel: "进入讨论",
      x: 2050,
      y: 360,
    });
  } else if (snapshot.phase === "settle" || snapshot.phase === "reveal") {
    hotspots.push({
      id: "multiplayer-settlement",
      sceneId: snapshot.stage_id,
      label: snapshot.phase === "settle" ? "圆桌判断" : "阶段结论",
      actionLabel: snapshot.phase === "settle" ? "判断" : "查看",
      x: 1510,
      y: 840,
    });
  }

  return hotspots;
}

function ChapterPanel({
  snapshot,
  pending,
  onConfirmRead,
}: {
  snapshot: GameplaySnapshotV1;
  pending: boolean;
  onConfirmRead: () => void;
}) {
  const selfRead = snapshot.read_member_ids.includes(snapshot.self_member_id);
  return (
    <div className="space-y-7 px-5 py-6 md:px-8">
      {snapshot.chapters.map((chapter) => (
        <article key={chapter.id} data-testid={`chapter-${chapter.id}`}>
          <h3 className="mb-3 text-lg font-semibold text-[#e3d8bd]">{chapter.title}</h3>
          <p className="whitespace-pre-wrap text-sm leading-8 text-[#c1c3bd]">{chapter.content}</p>
        </article>
      ))}
      {snapshot.chapters.length === 0 && (
        <p className="py-12 text-center text-sm text-[#878b84]">当前没有为你的角色解锁新章节。</p>
      )}
      {snapshot.phase === "read" && (
        <button
          type="button"
          disabled={selfRead || pending}
          onClick={onConfirmRead}
          className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#c6a867] px-5 py-3 text-sm font-semibold text-[#11120f] disabled:opacity-45"
        >
          {pending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
          {selfRead ? "已读，等待同伴" : "我已读完"}
        </button>
      )}
    </div>
  );
}

function MaterialCard({ material }: { material: GameplayMaterial }) {
  return (
    <article className="rounded-xl border border-white/8 bg-white/[0.025] p-4">
      <p className="mb-1 text-[10px] tracking-wider text-[#7f837c] uppercase">{material.kind}</p>
      <h3 className="mb-2 font-medium text-[#e3d8bd]">{material.title}</h3>
      {material.text && <p className="whitespace-pre-wrap text-sm leading-7 text-[#b8bbb4]">{material.text}</p>}
      {material.url && (
        <a href={material.url} target="_blank" rel="noreferrer" className="mt-3 inline-block text-xs text-[#d4bc84] underline">
          打开素材
        </a>
      )}
    </article>
  );
}

function HintPanel({
  snapshot,
  pending,
  onRequest,
  onConfirm,
}: {
  snapshot: GameplaySnapshotV1;
  pending: boolean;
  onRequest: (hint: GameplayHint, level: number) => void;
  onConfirm: (hint: GameplayHint, level: number) => void;
}) {
  return (
    <div className="space-y-5 px-5 py-6 md:px-8">
      {snapshot.hints.map((hint, index) => {
        const nextLevel = hint.revealed_levels.length + 1;
        const selfConfirmed = hint.confirming_member_ids.includes(snapshot.self_member_id);
        return (
          <section key={hint.id} className="space-y-4">
            {snapshot.hints.length > 1 && (
              <h3 className="text-sm font-semibold text-[#e3d8bd]">协作提示 {index + 1}</h3>
            )}
            {hint.revealed_levels.length === 0 ? (
              <p className="rounded-xl border border-white/8 bg-white/[0.025] px-4 py-5 text-sm leading-7 text-[#9da19a]">
                当前还没有公开提示。提示必须按级请求，并由全员确认后公开。
              </p>
            ) : (
              <ol className="space-y-3">
                {hint.revealed_levels.map((text, levelIndex) => (
                  <li key={`${hint.id}-${levelIndex}`} className="rounded-xl border border-[#c9ae76]/20 bg-[#c9ae76]/[0.06] p-4">
                    <p className="mb-1 text-[11px] text-[#c9ae76]">第 {levelIndex + 1} 级提示</p>
                    <p className="whitespace-pre-wrap text-sm leading-7 text-[#d0d1cb]">{text}</p>
                  </li>
                ))}
              </ol>
            )}
            {hint.pending_level !== null ? (
              <div>
                <button
                  type="button"
                  disabled={pending || selfConfirmed}
                  onClick={() => onConfirm(hint, hint.pending_level!)}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#c6a867] px-5 py-3 text-sm font-semibold text-[#11120f] disabled:opacity-45"
                >
                  <Check className="h-4 w-4" />
                  {selfConfirmed ? "已确认，等待同伴" : `同意公开第 ${hint.pending_level} 级提示`}
                </button>
                <p className="mt-2 text-center text-[11px] text-[#777b75]">
                  {hint.confirming_member_ids.length}/{snapshot.players.length} 位玩家已确认
                </p>
              </div>
            ) : nextLevel <= HINT_LEVEL_COUNT ? (
              <button
                type="button"
                disabled={pending}
                onClick={() => onRequest(hint, nextLevel)}
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-[#c9ae76]/30 bg-[#c9ae76]/[0.08] px-5 py-3 text-sm font-semibold text-[#dfc88f] disabled:opacity-45"
              >
                <Lightbulb className="h-4 w-4" />请求第 {nextLevel} 级提示
              </button>
            ) : (
              <p className="text-center text-xs text-[#777b75]">全部三级提示已公开</p>
            )}
          </section>
        );
      })}
    </div>
  );
}

function DiscussionPanel({
  snapshot,
  pending,
  onSend,
  onToggleClose,
}: {
  snapshot: GameplaySnapshotV1;
  pending: boolean;
  onSend: (text: string, onAccepted: () => void) => void;
  onToggleClose: () => void;
}) {
  const [message, setMessage] = useState("");
  const viewportRef = useRef<HTMLDivElement>(null);
  const selfClosed = snapshot.discussion_close_member_ids.includes(snapshot.self_member_id);

  useEffect(() => {
    const viewport = viewportRef.current;
    viewport?.scrollTo({ top: viewport.scrollHeight });
  }, [snapshot.discussion_messages.length]);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = message.trim();
    if (!text) return;
    onSend(text, () => setMessage((current) => current.trim() === text ? "" : current));
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={viewportRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-5" aria-live="polite">
        {snapshot.discussion_messages.length === 0 && (
          <p className="py-10 text-center text-sm text-[#777b75]">还没有讨论消息。把愿意公开的信息告诉同伴。</p>
        )}
        {snapshot.discussion_messages.map((item) => {
          const self = item.member_id === snapshot.self_member_id;
          return (
            <div key={item.message_id} className={`flex ${self ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[85%] rounded-2xl px-4 py-3 ${self ? "bg-[#c6a867] text-[#11120f]" : "bg-white/[0.06] text-[#d5d5cf]"}`}>
                <p className={`mb-1 text-[10px] ${self ? "text-black/50" : "text-[#888c85]"}`}>{playerName(snapshot, item.member_id)}</p>
                <p className="whitespace-pre-wrap text-sm leading-6">{item.text}</p>
              </div>
            </div>
          );
        })}
      </div>
      <div className="border-t border-white/8 p-4">
        <form onSubmit={submit} className="flex gap-2">
          <label className="sr-only" htmlFor="multiplayer-scene-message">讨论消息</label>
          <textarea
            id="multiplayer-scene-message"
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            maxLength={4000}
            rows={2}
            placeholder="分享你愿意公开的信息…"
            className="min-h-12 flex-1 resize-none rounded-xl border border-white/10 bg-black/20 px-4 py-3 text-sm outline-none focus:border-[#c9ae76]/50"
          />
          <button type="submit" aria-label="发送讨论消息" disabled={!message.trim() || pending} className="rounded-xl bg-[#c6a867] px-4 text-[#11120f] disabled:opacity-40">
            <Send className="h-4 w-4" />
          </button>
        </form>
        <button
          type="button"
          disabled={pending}
          onClick={onToggleClose}
          className={`mt-3 w-full rounded-xl px-4 py-3 text-sm font-medium ${selfClosed ? "border border-white/10 text-[#aeb1ab]" : "bg-emerald-300 text-[#0d1711]"}`}
        >
          {selfClosed ? "撤销结束确认" : "确认结束讨论"}
        </button>
        <p className="mt-2 text-center text-[11px] text-[#777b75]">
          {snapshot.discussion_close_member_ids.length}/{snapshot.players.length} 位玩家确认结束
        </p>
      </div>
    </div>
  );
}

function SettlementPanel({
  snapshot,
  settlement,
  pending,
  onSubmit,
  onAdvance,
}: {
  snapshot: GameplaySnapshotV1;
  settlement: GameplaySettlement;
  pending: boolean;
  onSubmit: (optionId: string) => void;
  onAdvance: () => void;
}) {
  const [selectedOptionId, setSelectedOptionId] = useState("");
  const submitted = settlement.submitted_member_ids.includes(snapshot.self_member_id);
  const locked = settlement.mode === "secret_vote" && submitted;
  const optionText = new Map(settlement.options.map((option) => [option.id, option.text]));

  useEffect(() => {
    setSelectedOptionId(settlement.own_option_id ?? settlement.shared_option_id ?? "");
  }, [settlement.settlement_id, settlement.own_option_id, settlement.shared_option_id]);

  if (snapshot.phase === "reveal") {
    return (
      <div className="space-y-4 px-5 py-6 md:px-8">
        <p className="text-sm leading-7 text-[#c3c0b7]">{settlement.question}</p>
        {settlement.reveal === "named_ballots" && (
          <div className="space-y-2" data-testid="revealed-ballots">
            {settlement.revealed_ballots.map((ballot) => (
              <div key={ballot.member_id} className="flex items-center justify-between gap-4 rounded-xl bg-white/[0.035] px-4 py-3 text-sm">
                <span className="text-[#9ea19a]">{playerName(snapshot, ballot.member_id)}</span>
                <span className="text-right text-[#e4d7b9]">{optionText.get(ballot.option_id) ?? ballot.option_id}</span>
              </div>
            ))}
          </div>
        )}
        {settlement.reveal === "aggregate" && settlement.revealed_option_counts.map((item) => (
          <div key={item.option_id} className="flex items-center justify-between rounded-xl bg-white/[0.035] px-4 py-3 text-sm">
            <span>{optionText.get(item.option_id) ?? item.option_id}</span><span>{item.count} 票</span>
          </div>
        ))}
        {settlement.reveal === "outcome_only" && settlement.outcome_id && (
          <p className="rounded-xl border border-emerald-300/15 bg-emerald-300/[0.06] px-4 py-3 text-sm text-emerald-100">双方的共同判断已经确认。</p>
        )}
        {snapshot.can_advance && (
          <button type="button" disabled={pending} onClick={onAdvance} className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#c6a867] px-4 py-3 text-sm font-semibold text-[#11120f] disabled:opacity-45">
            <StepForward className="h-4 w-4" />进入下一阶段
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="px-5 py-6 md:px-8">
      <h3 className="mb-2 text-lg font-semibold">{settlement.question}</h3>
      <p className="mb-5 text-xs leading-5 text-[#8f938d]">
        {settlement.mode === "secret_vote" ? "你的选择在全员提交前不会公开。" : "两位玩家必须确认同一个选择。"}
      </p>
      <fieldset className="space-y-3" disabled={pending || locked}>
        <legend className="sr-only">选择判断</legend>
        {settlement.options.map((option) => (
          <label key={option.id} className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 ${selectedOptionId === option.id ? "border-[#d0b373]/60 bg-[#d0b373]/10" : "border-white/8 bg-white/[0.025]"}`}>
            <input type="radio" name="scene-settlement-option" checked={selectedOptionId === option.id} onChange={() => setSelectedOptionId(option.id)} className="mt-1 accent-[#c9ae76]" />
            <span className="text-sm leading-6">{option.text}</span>
          </label>
        ))}
      </fieldset>
      <button type="button" onClick={() => onSubmit(selectedOptionId)} disabled={!selectedOptionId || pending || locked} className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#c6a867] px-5 py-3 text-sm font-semibold text-[#11120f] disabled:opacity-40">
        <Check className="h-4 w-4" />{locked ? "已提交，等待同伴" : submitted ? "重新确认此选择" : "确认选择"}
      </button>
      <p className="mt-3 text-center text-xs text-[#777b75]">{settlement.submitted_member_ids.length}/{snapshot.players.length} 位玩家已提交</p>
    </div>
  );
}

export function MultiplayerMansionShell({
  client,
  snapshot,
}: {
  client: MultiplayerRoomClient;
  snapshot: GameplaySnapshotV1;
}) {
  const queryClient = useQueryClient();
  const [panel, setPanel] = useState<ScenePanel>(null);
  const refreshSnapshot = useCallback(
    () => queryClient.invalidateQueries({ queryKey: roomSnapshotKey(snapshot.session_id) }),
    [queryClient, snapshot.session_id],
  );
  const command = useMutation({
    mutationFn: (input: RoomCommandInput) => client.sendCommand(snapshot.session_id, input),
    onError: (error) => {
      if (error instanceof MultiplayerClientError && error.code === "REVISION_MISMATCH") {
        void refreshSnapshot();
      }
      toast.error(multiplayerErrorMessage(error));
    },
  });
  const review = useQuery({
    queryKey: multiplayerReviewKey(snapshot.session_id),
    queryFn: ({ signal }) => client.getReview(snapshot.session_id, signal),
    enabled: snapshot.status === "completed" && panel === "review",
    retry: shouldRetryMultiplayer,
  });

  const selfPlayer = useMemo(
    () => snapshot.players.find((player) => player.member_id === snapshot.self_member_id),
    [snapshot.players, snapshot.self_member_id],
  );
  const otherPlayers = useMemo(
    () => snapshot.players.filter((player) => player.member_id !== snapshot.self_member_id),
    [snapshot.players, snapshot.self_member_id],
  );
  const remoteAvatars = useMemo<SceneAvatar[]>(
    () => otherPlayers.flatMap((player) => {
      if (
        !player.scene_online
        || player.scene_x === null
        || player.scene_y === null
        || player.scene_facing === null
      ) return [];
      return [{
        id: `member-${player.member_id}`,
        characterId: player.character_id,
        name: player.character_name,
        x: player.scene_x,
        y: player.scene_y,
        facing: player.scene_facing,
        moving: player.scene_moving,
        online: true,
      }];
    }),
    [otherPlayers],
  );
  const hasSelfPlayer = selfPlayer !== undefined;
  const selfCharacterId = selfPlayer?.character_id;
  const selfSceneX = selfPlayer?.scene_x;
  const selfSceneY = selfPlayer?.scene_y;
  const selfSceneFacing = selfPlayer?.scene_facing;
  const initialPlayerPosition = useMemo(
    () => selfSceneX !== null && selfSceneX !== undefined
      && selfSceneY !== null && selfSceneY !== undefined
      ? { x: selfSceneX, y: selfSceneY }
      : spawnByCharacter[selfCharacterId ?? ""] ?? { x: 1200, y: 1050 },
    [selfCharacterId, selfSceneX, selfSceneY],
  );
  const presenceRef = useRef<{
    lastPose: LocalScenePose | null;
    lastSentAt: number;
    timer: ReturnType<typeof setTimeout> | null;
    inFlight: boolean;
    queued: boolean;
  }>({ lastPose: null, lastSentAt: 0, timer: null, inFlight: false, queued: false });

  const sendLatestPresence = useCallback(async () => {
    const state = presenceRef.current;
    if (!state.lastPose) return;
    if (state.inFlight) {
      state.queued = true;
      return;
    }
    state.inFlight = true;
    state.queued = false;
    const pose = state.lastPose;
    try {
      await client.updateScenePresence(snapshot.session_id, {
        x: Math.round(pose.x * 10) / 10,
        y: Math.round(pose.y * 10) / 10,
        facing: pose.facing,
        moving: pose.moving,
      });
      state.lastSentAt = Date.now();
    } catch (error) {
      if (error instanceof MultiplayerClientError && [401, 403, 409, 422].includes(error.status)) {
        state.lastPose = null;
      }
    } finally {
      state.inFlight = false;
      if (state.queued && state.lastPose) void sendLatestPresence();
    }
  }, [client, snapshot.session_id]);

  const reportPlayerPose = useCallback((pose: LocalScenePose) => {
    const state = presenceRef.current;
    state.lastPose = pose;
    const delay = Math.max(0, PRESENCE_SEND_INTERVAL - (Date.now() - state.lastSentAt));
    if (state.timer) return;
    state.timer = setTimeout(() => {
      state.timer = null;
      void sendLatestPresence();
    }, delay);
  }, [sendLatestPresence]);
  const hotspots = useMemo(() => sceneHotspots(snapshot), [snapshot]);
  const selfRead = snapshot.read_member_ids.includes(snapshot.self_member_id);
  const selfClosed = snapshot.discussion_close_member_ids.includes(snapshot.self_member_id);
  const hintPanelAvailable = snapshot.status === "active"
    && snapshot.phase === "discuss"
    && snapshot.hints.length > 0;

  const presenceIdentityRef = useRef("");
  useEffect(() => {
    if (!hasSelfPlayer || snapshot.status !== "active") return;
    const state = presenceRef.current;
    const identity = `${snapshot.session_id}:${snapshot.self_member_id}`;
    if (presenceIdentityRef.current !== identity) {
      presenceIdentityRef.current = identity;
      state.lastPose = {
        ...initialPlayerPosition,
        facing: selfSceneFacing ?? (selfCharacterId === "insider" ? "right" : "left"),
        moving: false,
      };
    }
    void sendLatestPresence();
    const interval = window.setInterval(() => void sendLatestPresence(), PRESENCE_HEARTBEAT_INTERVAL);
    return () => window.clearInterval(interval);
  }, [
    hasSelfPlayer,
    initialPlayerPosition,
    selfCharacterId,
    selfSceneFacing,
    sendLatestPresence,
    snapshot.self_member_id,
    snapshot.session_id,
    snapshot.status,
  ]);

  useEffect(() => () => {
    const state = presenceRef.current;
    if (state.timer) {
      clearTimeout(state.timer);
      state.timer = null;
    }
  }, []);

  useEffect(() => {
    if (panel === "materials" && snapshot.public_materials.length === 0) setPanel(null);
    if (panel === "hints" && !hintPanelAvailable) setPanel(null);
    if (panel === "discussion" && snapshot.phase !== "discuss") setPanel(null);
    if (panel === "settlement" && snapshot.phase !== "settle" && snapshot.phase !== "reveal") setPanel(null);
  }, [hintPanelAvailable, panel, snapshot.phase, snapshot.public_materials.length]);

  const sendCommand = (input: RoomCommandInput, onSuccess?: () => void) => {
    command.reset();
    command.mutate(input, {
      onSuccess: async () => {
        await refreshSnapshot();
        onSuccess?.();
      },
    });
  };
  const interact = (_sceneId: string, hotspotId: string) => {
    const nextPanel: Record<string, ScenePanel> = {
      "multiplayer-chapters": "chapters",
      "multiplayer-materials": "materials",
      "multiplayer-discussion": "discussion",
      "multiplayer-settlement": "settlement",
      "multiplayer-review": "review",
    };
    setPanel(nextPanel[hotspotId] ?? null);
  };
  const confirmRead = () => sendCommand({
    expected_revision: snapshot.revision,
    type: "stage.confirm_read",
    payload: { stage_id: snapshot.stage_id },
  });
  const toggleDiscussionClose = () => sendCommand({
    expected_revision: snapshot.revision,
    type: selfClosed ? "discussion.revoke_close" : "discussion.confirm_close",
    payload: { stage_id: snapshot.stage_id },
  });
  const requestHint = (hint: GameplayHint, level: number) => {
    if (!hintPanelAvailable) return;
    sendCommand({
      expected_revision: snapshot.revision,
      type: "hint.request",
      payload: { hint_id: hint.id, level },
    });
  };
  const confirmHint = (hint: GameplayHint, level: number) => {
    if (!hintPanelAvailable) return;
    sendCommand({
      expected_revision: snapshot.revision,
      type: "hint.confirm",
      payload: { hint_id: hint.id, level },
    });
  };
  const submitSettlement = (optionId: string) => {
    if (!snapshot.settlement || !optionId) return;
    sendCommand(snapshot.settlement.mode === "secret_vote" ? {
      expected_revision: snapshot.revision,
      type: "settlement.submit",
      payload: { settlement_id: snapshot.settlement.settlement_id, option_id: optionId },
    } : {
      expected_revision: snapshot.revision,
      type: "settlement.confirm_shared_choice",
      payload: { settlement_id: snapshot.settlement.settlement_id, option_id: optionId },
    });
  };

  const objective = snapshot.status === "completed"
    ? "案件已经完成。前往大厅的复盘台，或到档案室查看终局材料。"
    : snapshot.phase === "read"
      ? selfRead ? "你已读完角色手记。等待同伴完成阅读。" : "前往书房，阅读只属于你角色的当前章节。"
      : snapshot.phase === "discuss"
        ? selfClosed ? "你已确认结束讨论；仍可回到双人讨论室撤销。" : "前往双人讨论室，与同伴公开核对各自掌握的信息。"
        : snapshot.phase === "settle"
          ? "前往圆桌，在双方掌握的材料范围内提交判断。"
          : "回到圆桌查看阶段结论，并在允许时进入下一章。";

  return (
    <MansionDemo
      initialPlayerPosition={initialPlayerPosition}
      sessionHotspots={hotspots}
      interactionBlocked={panel !== null}
      interactionPending={command.isPending}
      onInvestigate={interact}
      onPlayerPose={reportPlayerPose}
      playerName={selfPlayer?.character_name ?? "当前角色"}
      playerCharacterId={selfPlayer?.character_id}
      remoteAvatars={remoteAvatars}
      stageName={snapshot.status === "completed" ? "游戏完成" : `${snapshot.stage_name} · ${phaseLabel[snapshot.phase]}`}
      statusLabel="双人房间 · HTTP 同步 · 双方位置可见"
      objectiveText={objective}
      includeDemoContent={false}
      journalLabel="角色章"
      onOpenJournal={() => setPanel("chapters")}
      overlay={
        <GameplayPanelHost>
          <aside className="multiplayer-scene-presence" aria-label="双人进度">
            <span>{selfPlayer?.character_name ?? "你"} · 你</span>
            <span>{otherPlayers[0]?.character_name ?? "同伴"} · {otherPlayers[0]?.scene_online ? "同场" : "连接中"}</span>
            {snapshot.status !== "completed" && (
              <b>{snapshot.phase === "read" ? `${snapshot.read_member_ids.length}/2 已读` : snapshot.phase === "discuss" ? `${snapshot.discussion_close_member_ids.length}/2 确认` : `${snapshot.settlement?.submitted_member_ids.length ?? 0}/2 提交`}</b>
            )}
            {snapshot.public_materials.length > 0 && (
              <button type="button" onClick={() => setPanel("materials")}>
                <Archive />
                {snapshot.status === "completed" ? "打开终局档案" : "打开公开档案"}
              </button>
            )}
            {hintPanelAvailable && (
              <button type="button" onClick={() => setPanel("hints")}><Lightbulb />打开协作提示</button>
            )}
            {snapshot.status === "completed" ? (
              <button type="button" onClick={() => setPanel("review")}><Eye />打开复盘</button>
            ) : snapshot.phase === "discuss" ? (
              <button type="button" onClick={() => setPanel("discussion")}><MessageCircle />打开讨论</button>
            ) : snapshot.phase === "settle" || snapshot.phase === "reveal" ? (
              <button type="button" onClick={() => setPanel("settlement")}>
                <ShieldCheck />
                {snapshot.phase === "settle" ? "打开判断" : "打开结论"}
              </button>
            ) : null}
          </aside>
          {command.error && (
            <div role="alert" className="multiplayer-scene-error">
              <CircleAlert /><span>{multiplayerErrorMessage(command.error)}</span>
              <button type="button" onClick={() => void refreshSnapshot()}><RotateCcw />同步</button>
            </div>
          )}
          <Sheet open={panel === "chapters"} onClose={() => setPanel(null)} title={`${selfPlayer?.character_name ?? "当前角色"}的角色手记`} className="md:w-[min(680px,72vw)]">
            <ChapterPanel snapshot={snapshot} pending={command.isPending} onConfirmRead={confirmRead} />
          </Sheet>
          <Sheet open={panel === "materials"} onClose={() => setPanel(null)} title={snapshot.status === "completed" ? "终局档案" : "公开档案"} className="md:w-[min(680px,72vw)]">
            <div className="grid gap-3 p-5 md:grid-cols-2">
              {snapshot.public_materials.map((material) => <MaterialCard key={material.id} material={material} />)}
            </div>
          </Sheet>
          <Sheet open={panel === "hints" && hintPanelAvailable} onClose={() => setPanel(null)} title="协作提示" className="md:w-[min(620px,72vw)]">
            <HintPanel
              snapshot={snapshot}
              pending={command.isPending}
              onRequest={requestHint}
              onConfirm={confirmHint}
            />
          </Sheet>
          <Sheet open={panel === "discussion"} onClose={() => setPanel(null)} title="双人公开讨论" className="md:w-[min(620px,72vw)]">
            <DiscussionPanel
              snapshot={snapshot}
              pending={command.isPending}
              onSend={(text, onAccepted) => sendCommand({
                expected_revision: snapshot.revision,
                type: "discussion.send_message",
                payload: { stage_id: snapshot.stage_id, message_id: createUuid(), text },
              }, onAccepted)}
              onToggleClose={toggleDiscussionClose}
            />
          </Sheet>
          <Sheet open={panel === "settlement"} onClose={() => setPanel(null)} title={snapshot.phase === "settle" ? "圆桌判断" : "阶段结论"} className="md:w-[min(680px,72vw)]">
            {snapshot.settlement && (
              <SettlementPanel
                snapshot={snapshot}
                settlement={snapshot.settlement}
                pending={command.isPending}
                onSubmit={submitSettlement}
                onAdvance={() => sendCommand({ expected_revision: snapshot.revision, type: "stage.advance", payload: { stage_id: snapshot.stage_id } })}
              />
            )}
          </Sheet>
          <Sheet open={panel === "review"} onClose={() => setPanel(null)} title="案件复盘" className="md:w-[min(760px,78vw)]">
            <div className="space-y-6 p-5 md:p-8">
              {review.isPending && <p className="py-12 text-center text-sm text-[#969a94]"><LoaderCircle className="mx-auto mb-3 h-6 w-6 animate-spin" />正在打开复盘…</p>}
              {review.isError && (
                <div role="alert" className="rounded-xl border border-red-300/20 bg-red-300/[0.06] p-4 text-sm text-red-100">
                  <p>{multiplayerErrorMessage(review.error)}</p>
                  <button type="button" onClick={() => review.refetch()} className="mt-3 inline-flex items-center gap-2 underline"><RotateCcw className="h-4 w-4" />重新加载复盘</button>
                </div>
              )}
              {review.data && (
                <>
                  <header className="rounded-2xl border border-emerald-300/20 bg-emerald-300/[0.05] p-6 text-center">
                    <ShieldCheck className="mx-auto mb-3 text-emerald-300" />
                    <p className="text-xs text-emerald-200/60">游戏完成</p>
                    <h2 className="mt-1 text-2xl font-semibold">{review.data.ending.name}</h2>
                    <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-[#c1c3bd]">{review.data.ending.outcome_text}</p>
                  </header>
                  <section>
                    <h3 className="mb-3 flex items-center gap-2 text-lg font-semibold"><Eye className="h-4 w-4 text-[#c9ae76]" />案件真相</h3>
                    {review.data.truth.case_summary && <p className="mb-5 whitespace-pre-wrap text-sm leading-7 text-[#c1c3bd]">{review.data.truth.case_summary}</p>}
                    <div className="space-y-3">
                      {review.data.truth.timeline.map((item) => (
                        <div key={`${item.time}-${item.event}`} className="grid gap-1 border-l border-[#c9ae76]/30 pl-4 sm:grid-cols-[6rem_1fr]">
                          <span className="text-xs text-[#c9ae76]">{item.time}</span><span className="text-sm text-[#b8bbb4]">{item.event}</span>
                        </div>
                      ))}
                    </div>
                  </section>
                  <section>
                    <h3 className="mb-3 flex items-center gap-2 text-lg font-semibold"><BookOpen className="h-4 w-4 text-[#c9ae76]" />双方角色章节</h3>
                    <div className="space-y-5">
                      {review.data.chapters.map((chapter) => <article key={chapter.id}><h4 className="mb-2 font-medium text-[#e3d8bd]">{chapter.title}</h4><p className="whitespace-pre-wrap text-sm leading-7 text-[#aeb1ab]">{chapter.content}</p></article>)}
                    </div>
                  </section>
                  <div className="text-center"><Link href="/multiplayer" className="text-sm text-[#9fa29c] hover:text-white">返回多人入口</Link></div>
                </>
              )}
            </div>
          </Sheet>
        </GameplayPanelHost>
      }
    />
  );
}
