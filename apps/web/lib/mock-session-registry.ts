export interface MockSessionIdentity {
  sessionId: string;
  scriptId: string;
  characterId: string;
  playerName?: string;
}

const mockSessions = new Map<string, MockSessionIdentity>();

export function registerMockSession(identity: MockSessionIdentity) {
  mockSessions.set(identity.sessionId, identity);
}

export function getMockSessionIdentity(sessionId: string) {
  return mockSessions.get(sessionId) ?? null;
}
