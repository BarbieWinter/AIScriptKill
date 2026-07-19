"use client";

import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
} from "react";
import { useStore } from "zustand";

import {
  createSessionClient,
  type GameSessionClient,
} from "@/lib/game/session-client";
import {
  createSessionRuntime,
  type GameSessionRuntime,
} from "@/lib/game/session-runtime";
import type { SessionSource } from "@/lib/game/types";
import {
  createGameStore,
  type GameStore,
  type GameStoreApi,
  useGameStore as legacyGameStore,
} from "@/stores/gameStore";

interface SessionContexts {
  store: GameStoreApi;
  client: GameSessionClient;
  runtime: GameSessionRuntime;
}

const GameSessionContext = createContext<SessionContexts | null>(null);

export interface GameSessionProviderProps {
  source: SessionSource;
  sessionId: string;
  children: ReactNode;
  client?: GameSessionClient;
  autoRefresh?: boolean;
}

export function GameSessionProvider({
  source,
  sessionId,
  children,
  client: providedClient,
  autoRefresh = true,
}: GameSessionProviderProps) {
  const value = useMemo<SessionContexts>(() => {
    const client = providedClient ?? createSessionClient(source, sessionId);
    const store = createGameStore(source, sessionId);
    return {
      client,
      store,
      runtime: createSessionRuntime(source, sessionId, client, store),
    };
  }, [providedClient, sessionId, source]);

  useEffect(() => {
    if (autoRefresh) void value.runtime.refreshAll().catch(() => undefined);
    return () => value.runtime.cancelRefresh();
  }, [autoRefresh, value]);

  return (
    <GameSessionContext.Provider value={value}>
      {children}
    </GameSessionContext.Provider>
  );
}

export function GameSessionBoundary(props: GameSessionProviderProps) {
  return <GameSessionProvider {...props} />;
}

function useSessionContexts() {
  const contexts = useContext(GameSessionContext);
  if (!contexts) {
    throw new Error("Game session hooks must be used inside GameSessionBoundary");
  }
  return contexts;
}

export function useGameSessionRuntime() {
  return useSessionContexts().runtime;
}

export function useOptionalGameSessionRuntime() {
  return useContext(GameSessionContext)?.runtime ?? null;
}

export function useOptionalGameSessionStoreApi() {
  return useContext(GameSessionContext)?.store ?? null;
}

export function useSessionClient() {
  return useSessionContexts().client;
}

export function useGameSessionStore<T>(selector: (state: GameStore) => T): T {
  return useStore(useSessionContexts().store, selector);
}

export function useActiveGameStore<T>(selector: (state: GameStore) => T): T {
  const scopedStore = useContext(GameSessionContext)?.store;
  return useStore(scopedStore ?? legacyGameStore, selector);
}
