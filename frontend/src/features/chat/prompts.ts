export const EXAMPLE_PROMPTS = ['Buatkan 5 soal C2', 'Buatkan 3 soal C4 bab 2', 'Buatkan 5 soal C3 bab 1'];

/** Contoh perintah untuk soal yang sudah ada di sesi (bahas, buat ulang, revisi). */
export const QUESTION_PROMPTS = [
  'Jelaskan jawaban soal nomor 1',
  'Buat ulang soal nomor 1 jadi C4',
  'Soal nomor 1 terlalu mudah',
];

/** Susun kalimat permintaan yang dipahami parser backend (`_parse_generation_params`). */
export function buildGenerationPrompt({
  count,
  bloom,
  chapter,
}: {
  count: number;
  bloom?: string | null;
  chapter?: string | null;
}) {
  return ['Buatkan', `${count} soal`, bloom, chapter ? `bab ${chapter}` : null].filter(Boolean).join(' ');
}

/** Ambil nomor bab dari label chunk seperti "Bab 2: Berpikir Cerdas" → "2". */
export function chapterNumber(label: string): string | null {
  return label.match(/\bbab\s*([\w]+)/i)?.[1] ?? null;
}
