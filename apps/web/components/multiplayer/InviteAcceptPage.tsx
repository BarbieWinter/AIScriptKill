"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleAlert, LoaderCircle, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";

import {
  multiplayerErrorCode,
  multiplayerErrorMessage,
} from "@/lib/multiplayer/error-messages";
import { createMultiplayerRoomClient } from "@/lib/multiplayer/room-client";

export function InviteAcceptPage() {
  const params = useParams<{ token: string }>();
  const token = params.token;
  const router = useRouter();
  const client = useMemo(() => createMultiplayerRoomClient(), []);
  const acceptance = useQuery({
    queryKey: ["multiplayer", "invite-accept", token],
    queryFn: ({ signal }) => client.acceptInvite(token, signal),
    enabled: Boolean(token),
    retry: false,
    staleTime: Infinity,
  });

  useEffect(() => {
    if (!acceptance.data) return;
    router.replace(`/play/${encodeURIComponent(acceptance.data.session_id)}/lobby`);
  }, [acceptance.data, router]);

  const errorCode = multiplayerErrorCode(acceptance.error);

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#080a0c] px-5 text-[#e8e2d5]">
      <section className="w-full max-w-md rounded-3xl border border-[#b89a61]/20 bg-[#111412] p-8 text-center shadow-2xl shadow-black/40">
        {acceptance.isPending || acceptance.isSuccess ? (
          <>
            <LoaderCircle className="mx-auto mb-5 h-8 w-8 animate-spin text-[#c9ae76]" />
            <h1 className="mb-2 text-xl font-semibold">
              {acceptance.isSuccess ? "已加入房间" : "正在接受邀请"}
            </h1>
            <p className="text-sm leading-6 text-[#9fa29c]">
              {acceptance.isSuccess ? "正在进入房间大厅…" : "正在建立匿名玩家身份并验证邀请。"}
            </p>
          </>
        ) : (
          <>
            <CircleAlert className="mx-auto mb-5 h-8 w-8 text-red-300" />
            <h1 className="mb-2 text-xl font-semibold">无法加入房间</h1>
            <div role="alert" className="mb-6 text-sm leading-6 text-[#b8bab4]">
              <p>{multiplayerErrorMessage(acceptance.error)}</p>
              {errorCode && <p className="mt-2 font-mono text-[11px] text-red-200/60">{errorCode}</p>}
            </div>
            <div className="flex flex-col gap-3">
              <button
                type="button"
                onClick={() => acceptance.refetch()}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#c6a867] px-5 py-3 text-sm font-semibold text-[#11120f]"
              >
                <RotateCcw className="h-4 w-4" />
                重试邀请
              </button>
              <Link href="/multiplayer" className="text-sm text-[#9fa29c] hover:text-[#e8e2d5]">
                返回多人入口
              </Link>
            </div>
          </>
        )}
      </section>
    </main>
  );
}
