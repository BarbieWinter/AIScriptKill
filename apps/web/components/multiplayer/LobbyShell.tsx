"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Clipboard,
  Clock3,
  Crown,
  Link2,
  LoaderCircle,
  Play,
  RotateCcw,
  Trash2,
  UserRound,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  multiplayerErrorCode,
  multiplayerErrorMessage,
} from "@/lib/multiplayer/error-messages";
import {
  lobbySnapshotKey,
  MultiplayerClientError,
  type MultiplayerRoomClient,
} from "@/lib/multiplayer/room-client";
import type {
  CreateInviteResponse,
  LobbyCommandInput,
  LobbyInvite,
  LobbySnapshotV1,
} from "@/lib/multiplayer/types";

function shortId(value: string) {
  return value.length > 10 ? `${value.slice(0, 6)}…${value.slice(-4)}` : value;
}

function formatExpiry(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

type LobbyShellProps = {
  client: MultiplayerRoomClient;
  snapshot: LobbySnapshotV1;
};

export function LobbyShell({ client, snapshot }: LobbyShellProps) {
  const queryClient = useQueryClient();
  const [createdInvite, setCreatedInvite] = useState<CreateInviteResponse | null>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const inviteStorageKey = `multiplayer-invite:${snapshot.session_id}`;

  useEffect(() => {
    const stored = window.sessionStorage.getItem(inviteStorageKey);
    if (!stored) return;
    try {
      const invite = JSON.parse(stored) as CreateInviteResponse;
      if (new Date(invite.expires_at).getTime() > Date.now()) {
        setCreatedInvite(invite);
      } else {
        window.sessionStorage.removeItem(inviteStorageKey);
      }
    } catch {
      window.sessionStorage.removeItem(inviteStorageKey);
    }
  }, [inviteStorageKey]);

  const refreshSnapshot = () => queryClient.invalidateQueries({
    queryKey: lobbySnapshotKey(snapshot.session_id),
  });

  const command = useMutation({
    mutationFn: (input: LobbyCommandInput) => client.sendCommand(snapshot.session_id, input),
    onSuccess: refreshSnapshot,
    onError: (error) => {
      if (error instanceof MultiplayerClientError && error.code === "REVISION_MISMATCH") {
        return refreshSnapshot();
      }
    },
  });
  const createInvite = useMutation({
    mutationFn: () => client.createInvite(snapshot.session_id, 900),
    onSuccess: (invite) => {
      setCreatedInvite(invite);
      window.sessionStorage.setItem(inviteStorageKey, JSON.stringify(invite));
      setCopyState("idle");
      return refreshSnapshot();
    },
  });
  const revokeInvite = useMutation({
    mutationFn: (inviteId: string) => client.revokeInvite(snapshot.session_id, inviteId),
    onSuccess: (_, inviteId) => {
      if (createdInvite?.invite_id === inviteId) {
        setCreatedInvite(null);
        window.sessionStorage.removeItem(inviteStorageKey);
      }
      return refreshSnapshot();
    },
  });

  const characterById = useMemo(
    () => new Map(snapshot.characters.map((character) => [character.id, character])),
    [snapshot.characters],
  );
  const slotCount = Math.max(snapshot.capacity.max_players, snapshot.members.length);
  const allAssigned = snapshot.members.length === snapshot.capacity.max_players &&
    snapshot.capacity.joined === snapshot.capacity.max_players &&
    snapshot.members.every((member) => member.character_id !== null);
  const assignedIds = snapshot.members.flatMap((member) => member.character_id ? [member.character_id] : []);
  const assignmentsUnique = new Set(assignedIds).size === assignedIds.length;
  const allReady = snapshot.members.length > 0 && snapshot.members.every((member) => member.ready);
  const prerequisitesReady = allAssigned && assignmentsUnique && allReady;
  const canStart = snapshot.self.room_role === "host" &&
    snapshot.capabilities.can_start && prerequisitesReady;
  const anyPending = command.isPending || createInvite.isPending || revokeInvite.isPending;
  const actionError = command.error ?? createInvite.error ?? revokeInvite.error;
  const actionErrorCode = multiplayerErrorCode(actionError);

  const resetErrors = () => {
    command.reset();
    createInvite.reset();
    revokeInvite.reset();
  };
  const sendCommand = (input: LobbyCommandInput) => {
    resetErrors();
    command.mutate(input);
  };

  const snapshotInvites: LobbyInvite[] = [...snapshot.invites];
  if (createdInvite && !snapshotInvites.some((invite) => invite.invite_id === createdInvite.invite_id)) {
    snapshotInvites.unshift({
      invite_id: createdInvite.invite_id,
      expires_at: createdInvite.expires_at,
      uses_count: 0,
      max_uses: 1,
      revoked: false,
    });
  }
  const inviteUrl = createdInvite && typeof window !== "undefined"
    ? `${window.location.origin}/invite/${createdInvite.token}`
    : null;

  const copyInvite = async () => {
    if (!inviteUrl) return;
    try {
      await navigator.clipboard.writeText(inviteUrl);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  };

  return (
    <main className="min-h-screen bg-[#080a0c] px-4 py-7 text-[#e8e2d5] md:px-7 md:py-10">
      <div className="mx-auto max-w-6xl">
        <header className="mb-7 flex flex-col justify-between gap-5 border-b border-white/8 pb-7 md:flex-row md:items-end">
          <div>
            <p className="mb-2 text-xs tracking-[0.24em] text-[#a98e5d] uppercase">{snapshot.package.script_id}</p>
            <h1 className="mb-2 text-3xl font-semibold tracking-tight">房间大厅</h1>
            <p className="text-sm text-[#969a94]">
              {snapshot.package.title} · v{snapshot.package.version}
            </p>
          </div>
          <div className="flex items-center gap-3 rounded-xl border border-white/8 bg-white/[0.025] px-4 py-3 text-xs text-[#aeb1ab]">
            <Users className="h-4 w-4 text-[#c9ae76]" />
            {snapshot.capacity.joined}/{snapshot.capacity.max_players} 位玩家
            <span className="text-white/20">·</span>
            <span title={snapshot.session_id}>{shortId(snapshot.session_id)}</span>
          </div>
        </header>

        <div className="grid gap-6 lg:grid-cols-[1.45fr_0.8fr]">
          <div className="order-last space-y-6 lg:order-first">
            <section className="rounded-2xl border border-white/8 bg-[#111412] p-5 md:p-6">
              <div className="mb-5 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold">玩家席位</h2>
                  <p className="mt-1 text-xs text-[#8f938d]">两位玩家都要选择不同角色并准备</p>
                </div>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                {Array.from({ length: slotCount }, (_, index) => {
                  const member = snapshot.members[index];
                  const selectedCharacter = member?.character_id
                    ? characterById.get(member.character_id)
                    : null;
                  const isSelf = member?.member_id === snapshot.self.member_id;
                  return (
                    <article
                      key={member?.member_id ?? `empty-${index}`}
                      data-testid={`player-slot-${index + 1}`}
                      className={`rounded-xl border p-4 ${member ? "border-white/9 bg-white/[0.025]" : "border-dashed border-white/8 bg-black/10"}`}
                    >
                      {member ? (
                        <>
                          <div className="mb-4 flex items-start justify-between gap-3">
                            <div className="flex items-center gap-3">
                              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#252923]">
                                {member.room_role === "host" ? <Crown className="h-4 w-4 text-[#d3b570]" /> : <UserRound className="h-4 w-4 text-[#aeb1ab]" />}
                              </div>
                              <div>
                                <p className="text-sm font-medium">
                                  {member.room_role === "host" ? "房主" : `玩家 ${index + 1}`}
                                  {isSelf && <span className="ml-2 text-xs text-[#c9ae76]">你</span>}
                                </p>
                              </div>
                            </div>
                            <span className={`rounded-full px-2.5 py-1 text-[10px] ${member.ready ? "bg-emerald-300/10 text-emerald-200" : "bg-white/5 text-[#858983]"}`}>
                              {member.ready ? "已准备" : "未准备"}
                            </span>
                          </div>
                          <div className="rounded-lg bg-black/15 px-3 py-2.5 text-sm">
                            <span className="text-[#838780]">角色：</span>
                            <span className={selectedCharacter ? "text-[#e0d7c3]" : "text-[#777b75]"}>
                              {selectedCharacter?.name ?? "尚未选择"}
                            </span>
                          </div>
                        </>
                      ) : (
                        <div className="flex min-h-24 flex-col items-center justify-center text-center">
                          <Clock3 className="mb-2 h-5 w-5 text-[#676a65]" />
                          <p className="text-sm text-[#8b8e88]">等待玩家加入</p>
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            </section>

            <section className="rounded-2xl border border-white/8 bg-[#111412] p-5 md:p-6">
              <div className="mb-5">
                <h2 className="text-lg font-semibold">选择角色</h2>
                <p className="mt-1 text-xs text-[#8f938d]">角色来自房间快照；更换或取消角色会清除准备状态</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {snapshot.characters.map((character) => {
                  const selectedBySelf = character.assigned_member_id === snapshot.self.member_id;
                  const taken = character.assigned_member_id !== null && !selectedBySelf;
                  const label = selectedBySelf
                    ? `取消选择角色 ${character.name}`
                    : taken
                      ? `角色 ${character.name} 已被占用`
                      : `选择角色 ${character.name}`;
                  return (
                    <button
                      key={character.id}
                      type="button"
                      aria-label={label}
                      aria-pressed={selectedBySelf}
                      disabled={taken || anyPending || !snapshot.capabilities.can_assign_character}
                      onClick={() => sendCommand(selectedBySelf ? {
                        expected_revision: snapshot.revision,
                        type: "room.unassign_character",
                        payload: {},
                      } : {
                        expected_revision: snapshot.revision,
                        type: "room.assign_character",
                        payload: { character_id: character.id },
                      })}
                      className={`flex items-center justify-between rounded-xl border p-4 text-left transition ${selectedBySelf ? "border-[#c9ae76]/60 bg-[#c9ae76]/10" : taken ? "cursor-not-allowed border-white/5 bg-black/15 opacity-45" : "border-white/9 bg-white/[0.025] hover:border-[#c9ae76]/40 hover:bg-[#c9ae76]/[0.05]"} disabled:cursor-not-allowed`}
                    >
                      <span>
                        <span className="block text-sm font-medium">{character.name}</span>
                        <span className="mt-1 block text-[11px] leading-5 text-[#858983]">
                          {character.public_description}
                        </span>
                        <span className="mt-1 block text-[11px] text-[#6f736d]">
                          {selectedBySelf ? "你的角色 · 点击取消" : taken ? "已被另一位玩家选择" : "可以选择"}
                        </span>
                      </span>
                      {selectedBySelf && <Check className="h-5 w-5 text-[#d7bd83]" />}
                    </button>
                  );
                })}
              </div>

              <button
                type="button"
                disabled={!snapshot.self.character_id || !snapshot.capabilities.can_ready || anyPending}
                onClick={() => sendCommand({
                  expected_revision: snapshot.revision,
                  type: "room.ready",
                  payload: { ready: !snapshot.self.ready },
                })}
                className={`mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl px-5 py-3 text-sm font-semibold transition ${snapshot.self.ready ? "border border-emerald-300/25 bg-emerald-300/10 text-emerald-100 hover:bg-emerald-300/15" : "bg-[#c6a867] text-[#11120f] hover:bg-[#d6ba78]"} disabled:cursor-not-allowed disabled:opacity-40`}
              >
                {command.isPending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                {snapshot.self.ready ? "取消准备" : "准备"}
              </button>
            </section>
          </div>

          <aside className="order-first space-y-6 lg:order-last">
            {snapshot.self.room_role === "host" && (
              <section className="rounded-2xl border border-white/8 bg-[#111412] p-5">
                <div className="mb-4 flex items-center gap-2">
                  <Link2 className="h-4 w-4 text-[#c9ae76]" />
                  <h2 className="font-semibold">邀请玩家</h2>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    resetErrors();
                    createInvite.mutate();
                  }}
                  disabled={!snapshot.capabilities.can_invite || anyPending}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-[#c9ae76]/25 bg-[#c9ae76]/[0.07] px-4 py-3 text-sm text-[#dfc990] transition hover:bg-[#c9ae76]/10 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {createInvite.isPending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Link2 className="h-4 w-4" />}
                  创建 15 分钟邀请
                </button>

                {inviteUrl && (
                  <div className="mt-4 rounded-xl border border-[#c9ae76]/20 bg-black/15 p-3">
                    <p data-testid="invite-url" className="mb-3 break-all text-xs leading-5 text-[#c5c7c0]">{inviteUrl}</p>
                    <button
                      type="button"
                      onClick={copyInvite}
                      className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-white/7 px-3 py-2 text-xs hover:bg-white/10"
                    >
                      <Clipboard className="h-3.5 w-3.5" />
                      {copyState === "copied" ? "已复制" : copyState === "failed" ? "复制失败，请手动复制" : "复制邀请链接"}
                    </button>
                  </div>
                )}

                {snapshotInvites.length > 0 && (
                  <div className="mt-4 space-y-2">
                    {snapshotInvites.map((invite) => (
                      <div key={invite.invite_id} className="flex items-center justify-between gap-3 rounded-lg border border-white/7 px-3 py-2.5">
                        <div className="min-w-0">
                          <p className="truncate font-mono text-[10px] text-[#9a9d97]">{shortId(invite.invite_id)}</p>
                          <p className="mt-0.5 text-[10px] text-[#71756f]">
                            {invite.revoked ? "已撤销" : `${formatExpiry(invite.expires_at)} 到期 · ${invite.uses_count}/${invite.max_uses}`}
                          </p>
                        </div>
                        <button
                          type="button"
                          aria-label={`撤销邀请 ${invite.invite_id}`}
                          disabled={invite.revoked || anyPending}
                          onClick={() => {
                            resetErrors();
                            revokeInvite.mutate(invite.invite_id);
                          }}
                          className="rounded-lg p-2 text-[#8d908a] transition hover:bg-red-300/8 hover:text-red-200 disabled:opacity-30"
                        >
                          {revokeInvite.isPending && revokeInvite.variables === invite.invite_id
                            ? <LoaderCircle className="h-4 w-4 animate-spin" />
                            : <Trash2 className="h-4 w-4" />}
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            )}

            <section className="rounded-2xl border border-white/8 bg-[#111412] p-5">
              <div className="mb-4 flex items-center gap-2">
                <Play className="h-4 w-4 text-[#c9ae76]" />
                <h2 className="font-semibold">开始条件</h2>
              </div>
              <ul className="mb-5 space-y-2 text-xs text-[#a2a59f]">
                <li className="flex items-center gap-2"><Check className={`h-3.5 w-3.5 ${allAssigned ? "text-emerald-300" : "text-[#555954]"}`} />两位玩家已经加入并选角</li>
                <li className="flex items-center gap-2"><Check className={`h-3.5 w-3.5 ${assignmentsUnique && allAssigned ? "text-emerald-300" : "text-[#555954]"}`} />角色选择互不重复</li>
                <li className="flex items-center gap-2"><Check className={`h-3.5 w-3.5 ${allReady ? "text-emerald-300" : "text-[#555954]"}`} />两位玩家都已准备</li>
              </ul>
              {snapshot.self.room_role === "host" ? (
                <button
                  type="button"
                  disabled={!canStart || anyPending}
                  onClick={() => sendCommand({
                    expected_revision: snapshot.revision,
                    type: "room.start",
                    payload: {},
                  })}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-300 px-5 py-3 text-sm font-semibold text-[#0d1711] transition hover:bg-emerald-200 disabled:cursor-not-allowed disabled:bg-white/6 disabled:text-[#70746e]"
                >
                  {command.isPending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  开始游戏
                </button>
              ) : (
                <p className="rounded-xl bg-white/[0.025] px-3 py-3 text-center text-xs text-[#858983]">全部准备后由房主开始</p>
              )}
            </section>

            {actionError && (
              <div role="alert" className="rounded-xl border border-red-300/20 bg-red-300/[0.06] p-4 text-sm text-red-100">
                <p>{multiplayerErrorMessage(actionError)}</p>
                {actionErrorCode && (
                  <details className="mt-2 text-[10px] text-red-200/55">
                    <summary className="cursor-pointer">技术详情</summary>
                    <p className="mt-1 font-mono">{actionErrorCode}</p>
                  </details>
                )}
                {actionErrorCode === "REVISION_MISMATCH" && (
                  <button type="button" onClick={refreshSnapshot} className="mt-3 inline-flex items-center gap-1 text-xs underline">
                    <RotateCcw className="h-3 w-3" />刷新状态
                  </button>
                )}
              </div>
            )}
          </aside>
        </div>
      </div>
    </main>
  );
}
