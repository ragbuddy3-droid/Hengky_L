export const queryKeys = {
  me: ['auth', 'me'] as const,
  quota: ['auth', 'quota'] as const,

  documents: ['documents'] as const,
  document: (id: string) => ['documents', id] as const,
  documentChunks: (id: string) => ['documents', id, 'chunks'] as const,

  sessions: ['chat', 'sessions'] as const,
  session: (sessionId: string) => ['chat', 'sessions', sessionId] as const,
  messages: (sessionId: string) => ['chat', 'sessions', sessionId, 'messages'] as const,

  questions: (sessionId?: string) => ['questions', { sessionId: sessionId ?? null }] as const,
  question: (id: string) => ['questions', 'detail', id] as const,
};
