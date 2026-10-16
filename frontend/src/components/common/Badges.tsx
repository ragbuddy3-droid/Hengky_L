import { Badge, Loader } from '@mantine/core';
import { BLOOM_COLORS } from '@/theme/theme';
import { bloomCode, QUESTION_TYPE_LABELS } from '@/lib/format';

export function BloomBadge({ level, size = 'sm' }: { level?: string | null; size?: string }) {
  const code = bloomCode(level);
  return (
    <Badge color={code ? BLOOM_COLORS[code] : 'gray'} variant="filled" size={size} title={level ?? undefined}>
      {code ?? level ?? '—'}
    </Badge>
  );
}

const DOC_STATUS: Record<string, { color: string; label: string }> = {
  pending: { color: 'gray', label: 'Menunggu' },
  processing: { color: 'blue', label: 'Diproses' },
  ready: { color: 'green', label: 'Siap' },
  failed: { color: 'red', label: 'Gagal' },
};

export function DocumentStatusBadge({ status }: { status: string }) {
  const meta = DOC_STATUS[status] ?? { color: 'gray', label: status };
  const busy = status === 'pending' || status === 'processing';
  return (
    <Badge
      color={meta.color}
      variant={busy ? 'default' : 'dot'}
      leftSection={busy ? <Loader size={10} color={meta.color} /> : undefined}
    >
      {meta.label}
    </Badge>
  );
}

const QUESTION_STATUS: Record<string, { color: string; label: string }> = {
  final: { color: 'green', label: 'Final' },
  needs_review: { color: 'orange', label: 'Perlu Tinjauan' },
};

export function QuestionStatusBadge({ status }: { status: string }) {
  const meta = QUESTION_STATUS[status] ?? { color: 'gray', label: status };
  return (
    <Badge color={meta.color} variant="dot">
      {meta.label}
    </Badge>
  );
}

export function QuestionTypeBadge({ type }: { type?: string | null }) {
  return (
    <Badge color="indigo" variant="outline">
      {QUESTION_TYPE_LABELS[type ?? 'esai'] ?? type}
    </Badge>
  );
}
