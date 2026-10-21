import type { Question } from '@/types/question';
import { QUESTION_STATUS_LABELS, QUESTION_TYPE_LABELS } from './format';

export interface ExportOptions {
  title: string;
  /** true: kunci jawaban & penjelasan di bawah tiap soal. false: lembar soal, kunci di lampiran akhir. */
  includeAnswers: boolean;
}

function questionBlock(q: Question, index: number, includeAnswers: boolean) {
  const meta = [
    `**Tipe:** ${QUESTION_TYPE_LABELS[q.question_type] ?? q.question_type}`,
    `**Level:** ${q.bloom_level}`,
    includeAnswers ? `**Status:** ${QUESTION_STATUS_LABELS[q.status] ?? q.status}` : null,
  ]
    .filter(Boolean)
    .join(' · ');

  const lines = [`## Soal ${index}`, '', meta, '', q.question_text.trim(), ''];

  if (includeAnswers) {
    lines.push(`**Kunci jawaban:** ${q.answer_key.trim()}`, '');
    if (q.explanation) lines.push(`**Penjelasan:** ${q.explanation.trim()}`, '');
    if (q.source_reference) lines.push(`**Referensi materi:** ${q.source_reference.trim()}`, '');
  }
  return lines.join('\n');
}

/** Susun daftar soal menjadi dokumen Markdown siap cetak/bagikan. */
export function questionsToMarkdown(questions: Question[], { title, includeAnswers }: ExportOptions) {
  const date = new Intl.DateTimeFormat('id-ID', { dateStyle: 'long' }).format(new Date());
  const parts = [`# ${title}`, '', `_Diekspor ${date} · ${questions.length} soal_`, ''];

  questions.forEach((q, i) => parts.push(questionBlock(q, i + 1, includeAnswers), '---', ''));

  if (!includeAnswers && questions.length) {
    parts.push('## Kunci Jawaban', '');
    questions.forEach((q, i) => parts.push(`${i + 1}. ${q.answer_key.trim()}`));
    parts.push('');
  }
  return parts.join('\n');
}

/** Picu unduhan file teks di browser. */
export function downloadTextFile(filename: string, content: string, mime = 'text/markdown;charset=utf-8') {
  const url = URL.createObjectURL(new Blob([content], { type: mime }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Nama file aman: "Bank Soal" → "bank-soal-2026-10-15.md". */
export function exportFilename(base: string) {
  const slug = base
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/[\s_]+/g, '-')
    .slice(0, 60);
  return `${slug || 'soal'}-${new Date().toISOString().slice(0, 10)}.md`;
}
