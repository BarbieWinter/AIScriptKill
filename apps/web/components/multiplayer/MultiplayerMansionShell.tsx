"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
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
import { FormEvent, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { GameplayPanelHost } from "@/components/demo/GameplayPanelHost";
import { MansionDemo, type LocalScenePose, type SceneAvatar } from "@/components/demo/MansionDemo";
import { CompletedReview } from "@/components/multiplayer/CompletedReview";
import { Sheet } from "@/components/ui/Sheet";
import type { DemoSessionHotspot } from "@/lib/demo-data";
import {
  claimPersistedRoomCommand,
  clearPersistedRoomCommand,
  createPersistedRoomCommand,
  pendingRoomCommandStorageKey,
  persistedRoomCommandId,
  readPersistedRoomCommand,
  resumePersistedRoomCommand,
  submitPersistedRoomCommand,
  withCommandRecoveryRequestDeadline,
  type PersistedRoomCommand,
  type RoomCommandTerminal,
} from "@/lib/multiplayer/command-recovery";
import {
  multiplayerErrorMessage,
  shouldRetryMultiplayer,
} from "@/lib/multiplayer/error-messages";
import { isCompletedReview } from "@/lib/multiplayer/review-validation";
import {
  multiplayerReviewKey,
  MultiplayerClientError,
  roomSnapshotKey,
  selectNewerRoomSnapshot,
  type MultiplayerRoomClient,
} from "@/lib/multiplayer/room-client";
import type {
  AcceptedCommandResponse,
  GameplayHint,
  GameplayMaterial,
  GameplaySettlement,
  GameplaySnapshotV1,
  RoomCommandInput,
  RoomSnapshotV1,
} from "@/lib/multiplayer/types";
import { createUuid } from "@/lib/uuid";

const phaseLabel = {
  read: "阅读角色信息",
  discuss: "公开讨论",
  settle: "提交判断",
  reveal: "查看结果",
} as const;

type ScenePanel = "chapters" | "materials" | "hints" | "discussion" | "settlement" | "review" | null;
type CommandRecoveryView =
  | { status: "idle" }
  | { status: "processing"; commandId: string; error: unknown | null }
  | { status: "accepted"; commandId: string; error: unknown | null }
  | { status: "rejected"; commandId: string; error: unknown }
  | { status: "error"; commandId: string; error: unknown };
type AcceptedCommandRecovery = {
  record: PersistedRoomCommand;
  response: AcceptedCommandResponse;
  ownerGeneration: number;
  focusTarget?: HTMLElement | null;
};

function snapshotIncludesAcceptedCommand(
  snapshot: RoomSnapshotV1,
  response: AcceptedCommandResponse,
) {
  if (snapshot.revision < response.revision) return false;
  if (response.event_sequence === 0) return true;
  return "event_head_sequence" in snapshot
    && snapshot.event_head_sequence >= response.event_sequence;
}

function isScenePanelAvailable(
  panel: ScenePanel,
  snapshot: GameplaySnapshotV1,
  hintPanelAvailable: boolean,
  discussionPanelAvailable: boolean,
  settlementPanelAvailable: boolean,
) {
  if (panel === null || panel === "chapters") return true;
  if (panel === "materials") return snapshot.public_materials.length > 0;
  if (panel === "hints") return hintPanelAvailable;
  if (panel === "discussion") return discussionPanelAvailable;
  if (panel === "settlement") return settlementPanelAvailable;
  return snapshot.status === "completed";
}

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
  commandsAvailable,
  onRequest,
  onConfirm,
}: {
  snapshot: GameplaySnapshotV1;
  pending: boolean;
  commandsAvailable: boolean;
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
            {commandsAvailable && hint.pending_level !== null ? (
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
            ) : commandsAvailable && nextLevel <= HINT_LEVEL_COUNT ? (
              <button
                type="button"
                disabled={pending}
                onClick={() => onRequest(hint, nextLevel)}
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-[#c9ae76]/30 bg-[#c9ae76]/[0.08] px-5 py-3 text-sm font-semibold text-[#dfc88f] disabled:opacity-45"
              >
                <Lightbulb className="h-4 w-4" />请求第 {nextLevel} 级提示
              </button>
            ) : commandsAvailable ? (
              <p className="text-center text-xs text-[#777b75]">全部三级提示已公开</p>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}

function DiscussionPanel({
  snapshot,
  pending,
  commandsAvailable,
  onSend,
  onToggleClose,
}: {
  snapshot: GameplaySnapshotV1;
  pending: boolean;
  commandsAvailable: boolean;
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
      {commandsAvailable && (
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
      )}
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
  const [commandRecovery, setCommandRecovery] = useState<CommandRecoveryView>({ status: "idle" });
  const panelContextRef = useRef<string | null>(null);
  const panelFallbackRef = useRef<HTMLElement>(null);
  const commandLockRef = useRef(false);
  const commandOperationRef = useRef<Promise<void> | null>(null);
  const commandRecoveryControllerRef = useRef<AbortController | null>(null);
  const runPersistedCommandRef = useRef<(
    record: PersistedRoomCommand,
    submitFirst: boolean,
    focusTarget?: HTMLElement | null,
  ) => void>(() => undefined);
  const activeCommandRecordRef = useRef<PersistedRoomCommand | null>(null);
  const acceptedCommandRef = useRef<AcceptedCommandRecovery | null>(null);
  const acceptedSnapshotControllerRef = useRef<AbortController | null>(null);
  const postCommandSuccessRef = useRef<(() => void) | null>(null);
  const snapshotRef = useRef<RoomSnapshotV1>(snapshot);
  snapshotRef.current = snapshot;
  const commandIdentity = `${snapshot.session_id}:${snapshot.self_member_id}`;
  const commandIdentityRef = useRef(commandIdentity);
  commandIdentityRef.current = commandIdentity;
  const commandOwnerGenerationRef = useRef(0);

  useEffect(() => {
    const ownerGeneration = commandOwnerGenerationRef.current + 1;
    commandOwnerGenerationRef.current = ownerGeneration;
    return () => {
      if (commandOwnerGenerationRef.current === ownerGeneration) {
        commandOwnerGenerationRef.current += 1;
        commandRecoveryControllerRef.current?.abort();
        commandRecoveryControllerRef.current = null;
        commandOperationRef.current = null;
        activeCommandRecordRef.current = null;
        acceptedCommandRef.current = null;
        acceptedSnapshotControllerRef.current?.abort();
        acceptedSnapshotControllerRef.current = null;
        postCommandSuccessRef.current = null;
        commandLockRef.current = false;
      }
    };
  }, [commandIdentity]);

  const hintCommandsAvailable = snapshot.status === "active"
    && snapshot.phase === "discuss"
    && snapshot.hints.length > 0;
  const hintPanelAvailable = hintCommandsAvailable
    || snapshot.hints.some((hint) => hint.revealed_levels.length > 0);
  const discussionCommandsAvailable = snapshot.status === "active"
    && snapshot.phase === "discuss";
  const discussionPanelAvailable = discussionCommandsAvailable
    || snapshot.discussion_messages.length > 0;
  const settlementPanelAvailable = (snapshot.phase === "settle" || snapshot.phase === "reveal")
    && (
      snapshot.settlement !== null
      || snapshot.can_advance
    );
  const settlementEntryAvailable = snapshot.status === "active"
    && settlementPanelAvailable;
  const panelContext = `${snapshot.stage_id}:${snapshot.phase}`;
  const contextSensitivePanel = panel === "hints" || panel === "discussion";
  const panelOpenedInCurrentContext = !contextSensitivePanel
    || panelContextRef.current === panelContext;
  const activePanel = panelOpenedInCurrentContext
    && isScenePanelAvailable(
      panel,
      snapshot,
      hintPanelAvailable,
      discussionPanelAvailable,
      settlementPanelAvailable,
    )
    ? panel
    : null;
  const selectPanel = (nextPanel: ScenePanel) => {
    panelContextRef.current = nextPanel === null ? null : panelContext;
    setPanel(nextPanel);
  };
  const refreshSnapshot = useCallback(
    (throwOnError = false) => queryClient.invalidateQueries(
      { queryKey: roomSnapshotKey(snapshot.session_id) },
      { throwOnError },
    ),
    [queryClient, snapshot.session_id],
  );
  const review = useQuery({
    queryKey: multiplayerReviewKey(snapshot.session_id, snapshot.self_member_id),
    queryFn: async ({ signal }) => {
      const payload = await client.getReview(snapshot.session_id, signal) as unknown;
      if (!isCompletedReview(payload)) throw new Error("复盘数据格式无效。");
      return payload;
    },
    enabled: activePanel === "review",
    retry: shouldRetryMultiplayer,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
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
  const presenceIdentity = hasSelfPlayer && snapshot.status === "active"
    ? `${snapshot.session_id}:${snapshot.self_member_id}`
    : null;
  const presenceRef = useRef<{
    activeIdentity: string | null;
    lastPose: LocalScenePose | null;
    lastSentAt: number;
    timer: ReturnType<typeof setTimeout> | null;
    inFlight: AbortController | null;
    queued: boolean;
    disabled: boolean;
    failureCount: number;
    retryNotBefore: number;
  }>({
    activeIdentity: presenceIdentity,
    lastPose: null,
    lastSentAt: 0,
    timer: null,
    inFlight: null,
    queued: false,
    disabled: false,
    failureCount: 0,
    retryNotBefore: 0,
  });

  const sendLatestPresence = useCallback(async () => {
    const identity = presenceIdentity;
    const state = presenceRef.current;
    if (
      identity === null
      || state.activeIdentity !== identity
      || state.disabled
      || !state.lastPose
    ) return;
    const now = Date.now();
    if (now < state.retryNotBefore) {
      if (!state.timer) {
        state.timer = setTimeout(() => {
          state.timer = null;
          void sendLatestPresence();
        }, state.retryNotBefore - now);
      }
      return;
    }
    if (state.inFlight) {
      state.queued = true;
      return;
    }
    const controller = new AbortController();
    state.inFlight = controller;
    state.queued = false;
    state.lastSentAt = now;
    const pose = state.lastPose;
    try {
      await client.updateScenePresence(snapshot.session_id, {
        x: Math.round(pose.x * 10) / 10,
        y: Math.round(pose.y * 10) / 10,
        facing: pose.facing,
        moving: pose.moving,
      }, controller.signal);
      state.lastSentAt = Date.now();
      state.failureCount = 0;
      state.retryNotBefore = 0;
    } catch (error) {
      if (controller.signal.aborted || state.activeIdentity !== identity) return;
      if (error instanceof MultiplayerClientError && [403, 409, 422].includes(error.status)) {
        state.disabled = true;
        state.lastPose = null;
        state.queued = false;
      } else {
        state.failureCount += 1;
        state.retryNotBefore = Date.now() + Math.min(
          PRESENCE_SEND_INTERVAL * 2 ** (state.failureCount - 1),
          PRESENCE_HEARTBEAT_INTERVAL,
        );
      }
    } finally {
      if (state.inFlight !== controller) return;
      state.inFlight = null;
      const flushQueued = state.activeIdentity === identity
        && !state.disabled
        && state.queued
        && state.lastPose;
      state.queued = false;
      if (flushQueued) void sendLatestPresence();
    }
  }, [client, presenceIdentity, snapshot.session_id]);

  const reportPlayerPose = useCallback((pose: LocalScenePose) => {
    const identity = presenceIdentity;
    const state = presenceRef.current;
    if (identity === null || state.activeIdentity !== identity || state.disabled) return;
    state.lastPose = pose;
    const now = Date.now();
    const delay = Math.max(
      0,
      PRESENCE_SEND_INTERVAL - (now - state.lastSentAt),
      state.retryNotBefore - now,
    );
    if (state.timer) return;
    state.timer = setTimeout(() => {
      state.timer = null;
      void sendLatestPresence();
    }, delay);
  }, [presenceIdentity, sendLatestPresence]);
  const hotspots = useMemo(() => sceneHotspots(snapshot), [snapshot]);
  const selfRead = snapshot.read_member_ids.includes(snapshot.self_member_id);
  const selfClosed = snapshot.discussion_close_member_ids.includes(snapshot.self_member_id);
  const presenceIdentityRef = useRef("");

  useLayoutEffect(() => {
    const state = presenceRef.current;
    state.activeIdentity = presenceIdentity;
    state.disabled = false;
    state.failureCount = 0;
    state.retryNotBefore = 0;
    state.queued = false;
    if (state.timer) clearTimeout(state.timer);
    state.timer = null;
    state.inFlight?.abort();
    state.inFlight = null;
    if (presenceIdentity === null) {
      presenceIdentityRef.current = "";
      state.lastPose = null;
    }
    return () => {
      presenceIdentityRef.current = "";
      state.activeIdentity = null;
      state.queued = false;
      state.lastPose = null;
      if (state.timer) clearTimeout(state.timer);
      state.timer = null;
      state.inFlight?.abort();
      state.inFlight = null;
    };
  }, [presenceIdentity]);

  useEffect(() => {
    if (presenceIdentity === null) return;
    const state = presenceRef.current;
    if (presenceIdentityRef.current !== presenceIdentity) {
      presenceIdentityRef.current = presenceIdentity;
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
    initialPlayerPosition,
    presenceIdentity,
    selfCharacterId,
    selfSceneFacing,
    sendLatestPresence,
  ]);

  useEffect(() => {
    if (panel === activePanel) return;
    setPanel(null);
    window.requestAnimationFrame(() => panelFallbackRef.current?.focus());
  }, [activePanel, panel]);

  const commandOwnerIsCurrent = useCallback((
    record: PersistedRoomCommand,
    ownerGeneration: number,
  ) => commandOwnerGenerationRef.current === ownerGeneration
    && commandIdentityRef.current === `${record.session_id}:${record.member_id}`, []);

  const finalizeAcceptedCommand = useCallback(async (accepted: AcceptedCommandRecovery) => {
    if (!commandOwnerIsCurrent(accepted.record, accepted.ownerGeneration)) return;
    const current = acceptedCommandRef.current;
    if (
      !current
      || current.ownerGeneration !== accepted.ownerGeneration
      || current.record.serialized_envelope !== accepted.record.serialized_envelope
    ) return;

    const cleared = await clearPersistedRoomCommand(accepted.record);
    if (!commandOwnerIsCurrent(accepted.record, accepted.ownerGeneration)) return;
    const remaining = readPersistedRoomCommand(
      accepted.record.session_id,
      accepted.record.member_id,
    );
    if (!cleared && remaining?.serialized_envelope === accepted.record.serialized_envelope) {
      setCommandRecovery({
        status: "accepted",
        commandId: accepted.response.command_id,
        error: new MultiplayerClientError(
          409,
          "COMMAND_STORAGE_BUSY",
          "命令已接受，但浏览器存储仍在同步，请稍后重试。",
        ),
      });
      return;
    }

    acceptedCommandRef.current = null;
    acceptedSnapshotControllerRef.current?.abort();
    acceptedSnapshotControllerRef.current = null;
    if (
      activeCommandRecordRef.current?.serialized_envelope
      === accepted.record.serialized_envelope
    ) {
      activeCommandRecordRef.current = null;
    }
    const acceptedCallback = remaining?.serialized_envelope === accepted.record.serialized_envelope
      || remaining === null
      ? postCommandSuccessRef.current
      : null;
    postCommandSuccessRef.current = null;
    setCommandRecovery({ status: "idle" });
    acceptedCallback?.();
    if (accepted.focusTarget) {
      window.requestAnimationFrame(() => {
        const target = accepted.focusTarget?.isConnected
          ? accepted.focusTarget
          : panelFallbackRef.current;
        target?.focus();
      });
    }
  }, [commandOwnerIsCurrent]);

  const syncAcceptedCommand = useCallback(async (
    record: PersistedRoomCommand,
    response: AcceptedCommandResponse,
    ownerGeneration: number,
    focusTarget?: HTMLElement | null,
  ) => {
    if (!commandOwnerIsCurrent(record, ownerGeneration)) return;
    const previous = acceptedCommandRef.current;
    const accepted: AcceptedCommandRecovery = {
      record,
      response,
      ownerGeneration,
      focusTarget: focusTarget ?? (
        previous?.record.serialized_envelope === record.serialized_envelope
          ? previous.focusTarget
          : null
      ),
    };
    acceptedCommandRef.current = accepted;
    setCommandRecovery({ status: "accepted", commandId: response.command_id, error: null });
    acceptedSnapshotControllerRef.current?.abort();
    const snapshotController = new AbortController();
    acceptedSnapshotControllerRef.current = snapshotController;

    try {
      await queryClient.cancelQueries({
        queryKey: roomSnapshotKey(record.session_id),
        exact: true,
      });
      if (!commandOwnerIsCurrent(record, ownerGeneration)) return;
      const authoritativeSnapshot = await withCommandRecoveryRequestDeadline(
        (requestSignal) => client.getSnapshot(record.session_id, requestSignal),
        snapshotController.signal,
      );
      if (!commandOwnerIsCurrent(record, ownerGeneration)) return;
      if (
        acceptedCommandRef.current?.record.serialized_envelope
        !== record.serialized_envelope
      ) return;
      if (!snapshotIncludesAcceptedCommand(authoritativeSnapshot, response)) {
        throw new MultiplayerClientError(
          409,
          "COMMAND_SNAPSHOT_STALE",
          "权威房间状态尚未包含已接受命令。",
          {
            command_id: response.command_id,
            required_revision: String(response.revision),
            required_event_sequence: String(response.event_sequence),
          },
        );
      }
      queryClient.setQueryData<RoomSnapshotV1>(
        roomSnapshotKey(record.session_id),
        (current) => selectNewerRoomSnapshot(current, authoritativeSnapshot),
      );
      await finalizeAcceptedCommand(accepted);
    } catch (error) {
      if (!commandOwnerIsCurrent(record, ownerGeneration)) return;
      const current = acceptedCommandRef.current;
      if (
        !current
        || current.record.serialized_envelope !== record.serialized_envelope
      ) return;
      if (snapshotIncludesAcceptedCommand(snapshotRef.current, response)) {
        void finalizeAcceptedCommand(current);
        return;
      }
      setCommandRecovery({ status: "accepted", commandId: response.command_id, error });
      toast.error(multiplayerErrorMessage(error));
    } finally {
      if (acceptedSnapshotControllerRef.current === snapshotController) {
        acceptedSnapshotControllerRef.current = null;
      }
    }
  }, [client, commandOwnerIsCurrent, finalizeAcceptedCommand, queryClient]);

  useEffect(() => {
    const accepted = acceptedCommandRef.current;
    if (!accepted || !snapshotIncludesAcceptedCommand(snapshot, accepted.response)) return;
    void finalizeAcceptedCommand(accepted);
  }, [finalizeAcceptedCommand, snapshot]);

  const handleCommandTerminal = useCallback(async (
    record: PersistedRoomCommand,
    terminal: RoomCommandTerminal,
    ownerGeneration: number,
    focusTarget?: HTMLElement | null,
  ) => {
    if (!commandOwnerIsCurrent(record, ownerGeneration)) return;
    const commandId = terminal.response?.command_id ?? persistedRoomCommandId(record);
    if (terminal.status === "accepted") {
      await syncAcceptedCommand(record, terminal.response, ownerGeneration, focusTarget);
      return;
    }

    const cleared = await clearPersistedRoomCommand(record);
    if (!commandOwnerIsCurrent(record, ownerGeneration)) return;
    const remaining = readPersistedRoomCommand(record.session_id, record.member_id);
    acceptedCommandRef.current = null;
    acceptedSnapshotControllerRef.current?.abort();
    acceptedSnapshotControllerRef.current = null;
    if (activeCommandRecordRef.current?.serialized_envelope === record.serialized_envelope) {
      activeCommandRecordRef.current = null;
    }
    postCommandSuccessRef.current = null;
    setCommandRecovery({ status: "rejected", commandId, error: terminal.error });
    if (terminal.error.code === "REVISION_MISMATCH") void refreshSnapshot();
    if (!cleared && remaining?.serialized_envelope === record.serialized_envelope) {
      toast.error("命令已拒绝，但浏览器存储仍在同步，请稍后刷新恢复。");
    } else {
      toast.error(multiplayerErrorMessage(terminal.error));
    }
  }, [commandOwnerIsCurrent, refreshSnapshot, syncAcceptedCommand]);

  const runPersistedCommand = useCallback((
    record: PersistedRoomCommand,
    submitFirst: boolean,
    focusTarget?: HTMLElement | null,
  ) => {
    if (commandOperationRef.current) return;
    const ownerGeneration = commandOwnerGenerationRef.current;
    const recoveryController = new AbortController();
    commandRecoveryControllerRef.current = recoveryController;
    const commandId = persistedRoomCommandId(record);
    activeCommandRecordRef.current = record;
    commandLockRef.current = true;
    setCommandRecovery({ status: "processing", commandId, error: null });
    const onProcessing = (nextCommandId: string) => {
      if (!commandOwnerIsCurrent(record, ownerGeneration)) return;
      setCommandRecovery({ status: "processing", commandId: nextCommandId, error: null });
    };
    const operation = (submitFirst
      ? submitPersistedRoomCommand(client, record, onProcessing, recoveryController.signal)
      : resumePersistedRoomCommand(client, record, onProcessing, recoveryController.signal))
      .then((terminal) => handleCommandTerminal(
        record,
        terminal,
        ownerGeneration,
        focusTarget,
      ))
      .catch((error: unknown) => {
        if (!commandOwnerIsCurrent(record, ownerGeneration)) return;
        setCommandRecovery({ status: "processing", commandId, error });
        toast.error(multiplayerErrorMessage(error));
      })
      .finally(() => {
        if (commandOperationRef.current !== operation) return;
        commandOperationRef.current = null;
        if (commandRecoveryControllerRef.current === recoveryController) {
          commandRecoveryControllerRef.current = null;
        }
        commandLockRef.current = false;
        const successor = readPersistedRoomCommand(record.session_id, record.member_id);
        if (
          successor
          && successor.serialized_envelope !== record.serialized_envelope
          && commandOwnerIsCurrent(record, ownerGeneration)
        ) {
          postCommandSuccessRef.current = null;
          window.setTimeout(() => {
            if (commandOwnerIsCurrent(record, ownerGeneration) && !commandOperationRef.current) {
              runPersistedCommandRef.current(successor, false);
            }
          }, 0);
        }
      });
    commandOperationRef.current = operation;
  }, [client, commandOwnerIsCurrent, handleCommandTerminal]);
  runPersistedCommandRef.current = runPersistedCommand;

  useEffect(() => {
    const record = readPersistedRoomCommand(snapshot.session_id, snapshot.self_member_id);
    if (record) runPersistedCommand(record, false);
  }, [runPersistedCommand, snapshot.self_member_id, snapshot.session_id]);

  useEffect(() => {
    const storageKey = pendingRoomCommandStorageKey(
      snapshot.session_id,
      snapshot.self_member_id,
    );
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== storageKey || event.newValue === null) return;
      const record = readPersistedRoomCommand(snapshot.session_id, snapshot.self_member_id);
      if (!record) return;
      const activeRecord = activeCommandRecordRef.current;
      if (activeRecord?.serialized_envelope !== record.serialized_envelope) {
        postCommandSuccessRef.current = null;
      }
      runPersistedCommand(record, false);
    };
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, [runPersistedCommand, snapshot.self_member_id, snapshot.session_id]);

  const commandError = "error" in commandRecovery ? commandRecovery.error : null;
  const commandPending = commandRecovery.status === "processing"
    || commandRecovery.status === "accepted";
  const sendCommand = (input: RoomCommandInput, onSuccess?: () => void) => {
    if (commandLockRef.current || commandPending) return;
    const ownerGeneration = commandOwnerGenerationRef.current;
    const prepared = client.prepareCommand(input);
    const record = createPersistedRoomCommand(
      snapshot.session_id,
      snapshot.self_member_id,
      prepared,
    );
    commandLockRef.current = true;
    const claimController = new AbortController();
    commandRecoveryControllerRef.current?.abort();
    commandRecoveryControllerRef.current = claimController;
    postCommandSuccessRef.current = onSuccess ?? null;
    setCommandRecovery({ status: "processing", commandId: prepared.command_id, error: null });
    void claimPersistedRoomCommand(record, claimController.signal).then((claim) => {
      if (!commandOwnerIsCurrent(record, ownerGeneration)) return;
      if (commandRecoveryControllerRef.current === claimController) {
        commandRecoveryControllerRef.current = null;
      }
      if (!claim.claimed && claim.record.serialized_envelope !== record.serialized_envelope) {
        postCommandSuccessRef.current = null;
      }
      if (!commandOperationRef.current) commandLockRef.current = false;
      runPersistedCommand(claim.record, claim.claimed);
    }).catch((error: unknown) => {
      if (!commandOwnerIsCurrent(record, ownerGeneration)) return;
      if (commandRecoveryControllerRef.current === claimController) {
        commandRecoveryControllerRef.current = null;
      }
      const existing = readPersistedRoomCommand(record.session_id, record.member_id);
      if (!commandOperationRef.current) commandLockRef.current = false;
      if (existing) {
        if (existing.serialized_envelope !== record.serialized_envelope) {
          postCommandSuccessRef.current = null;
        }
        runPersistedCommand(existing, false);
        return;
      }
      postCommandSuccessRef.current = null;
      setCommandRecovery({ status: "error", commandId: prepared.command_id, error });
      toast.error(multiplayerErrorMessage(error));
    });
  };
  const recoverCommandError = () => {
    const dialogs = Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"]'));
    const focusTarget = dialogs.at(-1) ?? panelFallbackRef.current;
    if (commandRecovery.status === "processing") {
      const record = activeCommandRecordRef.current
        ?? readPersistedRoomCommand(snapshot.session_id, snapshot.self_member_id);
      if (record) {
        runPersistedCommand(record, false, focusTarget);
        return;
      }
    }
    if (commandRecovery.status === "accepted") {
      const record = activeCommandRecordRef.current
        ?? readPersistedRoomCommand(snapshot.session_id, snapshot.self_member_id);
      const accepted = acceptedCommandRef.current;
      if (
        record
        && accepted
        && accepted.record.serialized_envelope === record.serialized_envelope
        && !commandOperationRef.current
      ) {
        const ownerGeneration = commandOwnerGenerationRef.current;
        commandLockRef.current = true;
        const operation = syncAcceptedCommand(
          record,
          accepted.response,
          ownerGeneration,
          focusTarget,
        ).finally(() => {
          if (commandOperationRef.current === operation) {
            commandOperationRef.current = null;
            commandLockRef.current = false;
          }
        });
        commandOperationRef.current = operation;
        return;
      }
    }
    void refreshSnapshot(true).then(() => {
      setCommandRecovery({ status: "idle" });
      window.requestAnimationFrame(() => {
        const target = focusTarget?.isConnected ? focusTarget : panelFallbackRef.current;
        target?.focus();
      });
    }).catch(() => undefined);
  };
  const interact = (_sceneId: string, hotspotId: string) => {
    const nextPanel: Record<string, ScenePanel> = {
      "multiplayer-chapters": "chapters",
      "multiplayer-materials": "materials",
      "multiplayer-discussion": "discussion",
      "multiplayer-settlement": "settlement",
      "multiplayer-review": "review",
    };
    selectPanel(nextPanel[hotspotId] ?? null);
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
    if (!hintCommandsAvailable) return;
    sendCommand({
      expected_revision: snapshot.revision,
      type: "hint.request",
      payload: { hint_id: hint.id, level },
    });
  };
  const confirmHint = (hint: GameplayHint, level: number) => {
    if (!hintCommandsAvailable) return;
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
  const renderCommandError = (insideSheet: boolean) => {
    if (commandRecovery.status === "idle") return null;
    const hasError = commandError !== null && commandError !== undefined;
    const statusText = commandRecovery.status === "processing"
      ? hasError
        ? `命令状态仍不确定：${multiplayerErrorMessage(commandError)}`
        : "正在确认上一条命令，请勿重复操作。"
      : commandRecovery.status === "accepted"
        ? hasError
          ? `命令已接受，但同步失败：${multiplayerErrorMessage(commandError)}`
          : "命令已接受，正在同步最新房间状态。"
        : commandRecovery.status === "rejected"
          ? `命令已拒绝：${multiplayerErrorMessage(commandRecovery.error)}`
          : `命令未提交：${multiplayerErrorMessage(commandRecovery.error)}`;
    const statusClass = commandRecovery.status === "accepted"
      ? "is-accepted"
      : commandRecovery.status === "processing" && !hasError
        ? "is-processing"
        : "is-error";
    const actionLabel = commandRecovery.status === "processing" ? "继续恢复" : "同步";
    const actionable = hasError
      || commandRecovery.status === "rejected"
      || commandRecovery.status === "error";
    return (
      <div
        role={actionable ? "alert" : "status"}
        data-testid="command-recovery-status"
        className={`multiplayer-scene-error multiplayer-command-status ${statusClass}${insideSheet ? " multiplayer-sheet-error" : ""}`}
      >
        {commandRecovery.status === "processing" && !hasError
          ? <LoaderCircle className="animate-spin" />
          : commandRecovery.status === "accepted" && !hasError
            ? <Check />
            : <CircleAlert />}
        <span>{statusText}</span>
        {actionable && (
          <button type="button" onClick={recoverCommandError}><RotateCcw />{actionLabel}</button>
        )}
      </div>
    );
  };

  return (
    <MansionDemo
      initialPlayerPosition={initialPlayerPosition}
      sessionHotspots={hotspots}
      interactionBlocked={activePanel !== null}
      interactionPending={commandPending}
      onInvestigate={interact}
      onPlayerPose={presenceIdentity === null ? undefined : reportPlayerPose}
      playerName={selfPlayer?.character_name ?? "当前角色"}
      playerCharacterId={selfPlayer?.character_id}
      remoteAvatars={remoteAvatars}
      stageName={snapshot.status === "completed" ? "游戏完成" : `${snapshot.stage_name} · ${phaseLabel[snapshot.phase]}`}
      statusLabel="双人房间 · HTTP 同步 · 双方位置可见"
      objectiveText={objective}
      includeDemoContent={false}
      journalLabel="角色章"
      onOpenJournal={() => selectPanel("chapters")}
      overlay={
        <GameplayPanelHost>
          <aside
            ref={panelFallbackRef}
            tabIndex={-1}
            data-sheet-focus-fallback
            className="multiplayer-scene-presence"
            aria-label="双人进度"
          >
            <span>{selfPlayer?.character_name ?? "你"} · 你</span>
            <span>{otherPlayers[0]?.character_name ?? "同伴"} · {otherPlayers[0]?.scene_online ? "同场" : "连接中"}</span>
            {snapshot.status !== "completed" && (
              <b>{snapshot.phase === "read" ? `${snapshot.read_member_ids.length}/2 已读` : snapshot.phase === "discuss" ? `${snapshot.discussion_close_member_ids.length}/2 确认` : `${snapshot.settlement?.submitted_member_ids.length ?? 0}/2 提交`}</b>
            )}
            {snapshot.public_materials.length > 0 && (
              <button type="button" data-sheet-trigger="materials" onClick={() => selectPanel("materials")}>
                <Archive />
                {snapshot.status === "completed" ? "打开终局档案" : "打开公开档案"}
              </button>
            )}
            {hintPanelAvailable && (
              <button type="button" data-sheet-trigger="hints" onClick={() => selectPanel("hints")}><Lightbulb />打开协作提示</button>
            )}
            {discussionPanelAvailable && (
              <button type="button" data-sheet-trigger="discussion" onClick={() => selectPanel("discussion")}><MessageCircle />打开讨论</button>
            )}
            {settlementEntryAvailable && (
              <button type="button" data-sheet-trigger="settlement" onClick={() => selectPanel("settlement")}>
                <ShieldCheck />
                {snapshot.phase === "settle" ? "打开判断" : "打开结论"}
              </button>
            )}
            {snapshot.status === "completed" && (
              <button type="button" data-sheet-trigger="review" onClick={() => selectPanel("review")}><Eye />打开复盘</button>
            )}
          </aside>
          {activePanel === null && renderCommandError(false)}
          <Sheet fallbackFocusRef={panelFallbackRef} banner={activePanel === "chapters" ? renderCommandError(true) : null} open={activePanel === "chapters"} onClose={() => selectPanel(null)} title={`${selfPlayer?.character_name ?? "当前角色"}的角色手记`} className="md:w-[min(680px,72vw)]">
            <ChapterPanel snapshot={snapshot} pending={commandPending} onConfirmRead={confirmRead} />
          </Sheet>
          <Sheet fallbackFocusRef={panelFallbackRef} banner={activePanel === "materials" ? renderCommandError(true) : null} open={activePanel === "materials"} onClose={() => selectPanel(null)} title={snapshot.status === "completed" ? "终局档案" : "公开档案"} className="md:w-[min(680px,72vw)]">
            <div className="grid gap-3 p-5 md:grid-cols-2">
              {snapshot.public_materials.map((material) => <MaterialCard key={material.id} material={material} />)}
            </div>
          </Sheet>
          <Sheet fallbackFocusRef={panelFallbackRef} banner={activePanel === "hints" ? renderCommandError(true) : null} open={activePanel === "hints"} onClose={() => selectPanel(null)} title="协作提示" className="md:w-[min(620px,72vw)]">
            <HintPanel
              snapshot={snapshot}
              pending={commandPending}
              commandsAvailable={hintCommandsAvailable}
              onRequest={requestHint}
              onConfirm={confirmHint}
            />
          </Sheet>
          <Sheet fallbackFocusRef={panelFallbackRef} banner={activePanel === "discussion" ? renderCommandError(true) : null} open={activePanel === "discussion"} onClose={() => selectPanel(null)} title="双人公开讨论" className="md:w-[min(620px,72vw)]">
            <DiscussionPanel
              snapshot={snapshot}
              pending={commandPending}
              commandsAvailable={discussionCommandsAvailable}
              onSend={(text, onAccepted) => sendCommand({
                expected_revision: snapshot.revision,
                type: "discussion.send_message",
                payload: { stage_id: snapshot.stage_id, message_id: createUuid(), text },
              }, onAccepted)}
              onToggleClose={toggleDiscussionClose}
            />
          </Sheet>
          <Sheet fallbackFocusRef={panelFallbackRef} banner={activePanel === "settlement" ? renderCommandError(true) : null} open={activePanel === "settlement"} onClose={() => selectPanel(null)} title={snapshot.phase === "settle" ? "圆桌判断" : "阶段结论"} className="md:w-[min(680px,72vw)]">
            {snapshot.settlement ? (
              <SettlementPanel
                snapshot={snapshot}
                settlement={snapshot.settlement}
                pending={commandPending}
                onSubmit={submitSettlement}
                onAdvance={() => sendCommand({ expected_revision: snapshot.revision, type: "stage.advance", payload: { stage_id: snapshot.stage_id } })}
              />
            ) : snapshot.phase === "reveal" && snapshot.can_advance ? (
              <div className="space-y-4 px-5 py-6 md:px-8">
                <p className="text-sm leading-7 text-[#c3c0b7]">本阶段已完成。</p>
                <button
                  type="button"
                  disabled={commandPending}
                  onClick={() => sendCommand({ expected_revision: snapshot.revision, type: "stage.advance", payload: { stage_id: snapshot.stage_id } })}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#c6a867] px-4 py-3 text-sm font-semibold text-[#11120f] disabled:opacity-45"
                >
                  <StepForward className="h-4 w-4" />进入下一阶段
                </button>
              </div>
            ) : null}
          </Sheet>
          <Sheet fallbackFocusRef={panelFallbackRef} banner={activePanel === "review" ? renderCommandError(true) : null} open={activePanel === "review"} onClose={() => selectPanel(null)} title="案件复盘" className="md:w-[min(760px,78vw)]">
            <div className="space-y-6 p-5 md:p-8">
              {review.isPending && <p className="py-12 text-center text-sm text-[#969a94]"><LoaderCircle className="mx-auto mb-3 h-6 w-6 animate-spin" />正在打开复盘…</p>}
              {review.isError && (
                <div role="alert" className="rounded-xl border border-red-300/20 bg-red-300/[0.06] p-4 text-sm text-red-100">
                  <p>{multiplayerErrorMessage(review.error)}</p>
                  <button type="button" onClick={() => review.refetch()} className="mt-3 inline-flex items-center gap-2 underline"><RotateCcw className="h-4 w-4" />重新加载复盘</button>
                </div>
              )}
              {review.data && <CompletedReview review={review.data} />}
            </div>
          </Sheet>
        </GameplayPanelHost>
      }
    />
  );
}
