/** Ambil kode Bloom ("C4") dari nilai backend seperti "C4-Menganalisis". */
export function bloomCode(level?: string | null): string | null {
  const match = level?.match(/\bC([1-6])\b/i);
  return match ? `C${match[1]}` : null;
}

/** Format tanggal backend (ISO atau string bebas) ke tampilan Indonesia; kembalikan apa adanya jika tidak bisa di-parse. */
export function formatDate(value?: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('id-ID', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

export const QUESTION_TYPE_LABELS: Record<string, string> = {
  esai: 'Esai',
  esai_pendek: 'Esai Pendek',
  isian_singkat: 'Isian Singkat',
};

export const CHUNK_CATEGORY_LABELS: Record<string, string> = {
  materi_pokok: 'Materi Pokok',
  uraian_materi: 'Uraian Materi',
  studi_kasus: 'Studi Kasus',
  aktivitas_diskusi: 'Aktivitas Diskusi',
  rangkuman: 'Rangkuman',
};

export const formatNumber = (n: number) => new Intl.NumberFormat('id-ID').format(n);
