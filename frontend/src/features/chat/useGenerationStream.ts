'use client';

import { useEffect, useReducer } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { chatApi } from '@/lib/api/chat';
import { queryKeys } from '@/lib/query-keys';
import type { CandidateDraft, CandidateStatus, GenerationEvent } from '@/types/chat';

export interface StreamCandidate {
  id: string;
  status: CandidateStatus;
  attempt?: number;
  question?: CandidateDraft;
}

export interface GenerationProgress {
  target: number;
  phaseLabel: string;
  /** Kandidat yang masih relevan (yang dibuang karena duplikat/dibatalkan tidak ikut). */
  candidates: StreamCandidate[];
  finalCount: number;
  percent: number;
}

interface State {
  target: number;
  phase: string;
  phaseLabel: string;
  order: string[];
  byId: Record<string, StreamCandidate>;
  /** Persen tertinggi yang pernah tampil, agar bar tidak mundur saat ronde pengganti dimulai. */
  maxPercent: number;
}

const INITIAL: State = { target: 0, phase: 'retrieval', phaseLabel: 'Memulai…', order: [], byId: {}, maxPercent: 0 };

/** Persen awal tiap fase sebelum kandidat soal mulai dikerjakan. */
const PHASE_BASE: Record<string, number> = { retrieval: 3, analysis: 8, planning: 12, generation: 15, top_up: 15, saving: 97 };

/** Seberapa jauh satu kandidat dari selesai (0–1). */
const STATUS_WEIGHT: Record<CandidateStatus, number> = {
  blueprint: 0.1,
  writing: 0.3,
  validating: 0.6,
  refining: 0.75,
  final: 1,
  needs_review: 1,
  dropped: 0,
};

function computePercent(state: State): number {
  const base = PHASE_BASE[state.phase] ?? 15;
  if (state.phase === 'saving' || state.target === 0) return base;
  const weights = state.order
    .map((id) => STATUS_WEIGHT[state.byId[id].status])
    .sort((a, b) => b - a)
    .slice(0, state.target);
  const done = weights.reduce((sum, w) => sum + w, 0) / state.target;
  return Math.round(base + (95 - base) * Math.min(1, done));
}

function reducer(state: State, event: GenerationEvent | { type: 'reset' }): State {
  let next: State;
  switch (event.type) {
    case 'reset':
      return INITIAL;
    case 'start':
      // Juga saat tersambung ulang: server memutar ulang riwayat dari awal.
      next = { ...INITIAL, target: event.target };
      break;
    case 'phase':
      next = { ...state, phase: event.phase, phaseLabel: event.label };
      break;
    case 'candidate': {
      const prev = state.byId[event.id];
      const candidate: StreamCandidate = {
        id: event.id,
        status: event.status,
        attempt: event.attempt ?? prev?.attempt,
        question: event.question ?? prev?.question,
      };
      next = {
        ...state,
        order: prev ? state.order : [...state.order, event.id],
        byId: { ...state.byId, [event.id]: candidate },
      };
      break;
    }
    default:
      return state;
  }
  return { ...next, maxPercent: Math.max(event.type === 'start' ? 0 : state.maxPercent, computePercent(next)) };
}

/**
 * Berlangganan progres generasi soal lewat SSE selama `running`. Mengembalikan progres terkini, atau null
 * bila tidak ada generasi berjalan. Saat event `done` tiba, status sesi langsung di-refresh supaya
 * `useSessionGeneration` tidak perlu menunggu polling berikutnya.
 */
export function useGenerationStream(sessionId: string, running: boolean): GenerationProgress | null {
  const queryClient = useQueryClient();
  const [state, dispatch] = useReducer(reducer, INITIAL);

  useEffect(() => {
    if (!running) return;
    dispatch({ type: 'reset' });
    const source = new EventSource(chatApi.generationStreamUrl(sessionId));
    source.onmessage = (message) => {
      const event = JSON.parse(message.data) as GenerationEvent;
      dispatch(event);
      if (event.type === 'done') {
        source.close();
        queryClient.invalidateQueries({ queryKey: queryKeys.session(sessionId) });
      }
    };
    // Bila koneksi putus, EventSource menyambung ulang sendiri; polling status tetap menjadi cadangan.
    return () => source.close();
  }, [running, sessionId, queryClient]);

  if (!running) return null;
  const candidates = state.order.map((id) => state.byId[id]).filter((c) => c.status !== 'dropped');
  return {
    target: state.target,
    phaseLabel: state.phaseLabel,
    candidates,
    finalCount: candidates.filter((c) => c.status === 'final').length,
    percent: state.maxPercent,
  };
}
