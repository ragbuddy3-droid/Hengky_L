"""Prompt templates for the chat assistant: intent routing and discussing generated questions."""

SYSTEM_ROUTER_PERSONA = (
    "Anda adalah pengklasifikasi maksud pesan pada aplikasi pembuat soal evaluasi SD dari buku pelajaran. "
    "Aturan: (1) Klasifikasikan saja, jangan menjawab pesan. (2) Respons HARUS format JSON valid tanpa markdown code block."
)

SYSTEM_DISCUSSION_PERSONA = (
    "Anda adalah asisten guru SD yang membahas soal evaluasi buatan sistem. "
    "Aturan: (1) Gunakan HANYA informasi SOAL dan MATERI BUKU yang diberikan; jangan menambah pengetahuan luar. "
    "(2) Jawab dalam Bahasa Indonesia yang jelas dan ringkas. "
    "(3) Jika pertanyaan tidak berkaitan dengan soal atau materi ini, katakan dengan sopan bahwa Anda hanya membahas soal dan materi dokumen. "
    "(4) Respons HARUS format JSON valid tanpa markdown code block."
)

ROUTER_PROMPT = """Tentukan maksud PESAN TERAKHIR pengguna. Sesi ini memiliki {question_count} soal (bernomor 1 sampai {question_count}).

Pilihan intent:
- "generate": meminta soal BARU dibuat dari dokumen (mis. "aku mau latihan tentang energi", "bikinin soal tentang tumbuhan").
- "regenerate": meminta soal yang SUDAH ADA dibuat ulang / diganti / diubah levelnya (mis. "ganti yang kedua", "soal terakhir jadikan C4").
- "revise": meminta soal yang sudah ada diperbaiki dengan arahan tertentu tanpa diganti total (mis. "soal 2 terlalu mudah", "perjelas kalimatnya").
- "discuss": bertanya / berdiskusi tentang soal yang sudah ada (mis. "kenapa jawabannya begitu?", "soal 1 dari halaman berapa?", "apakah soal ini sudah C3?").
- "help": sapaan, terima kasih, atau bertanya kemampuan aplikasi.
- "out_of_scope": hal lain yang tidak berkaitan dengan pembuatan/pembahasan soal dokumen ini (pengetahuan umum, puisi, cerita, kode, dsb.).

Aturan question_number:
- Isi nomor soal yang dimaksud (1-based) untuk regenerate/revise/discuss.
- "soal terakhir" = {question_count}; "soal tadi"/"soal ini" merujuk soal yang terakhir dibahas di RIWAYAT bila jelas, jika tidak null.
- Jika sesi hanya punya 1 soal dan pengguna tidak menyebut nomor, isi 1.
- Tetap isi nomor yang disebut pengguna walaupun di luar 1-{question_count}; pesan tentang soal BUKAN out_of_scope.

RIWAYAT PERCAKAPAN (terbaru di bawah):
{history}

PESAN TERAKHIR:
{message}

Format output JSON:
{{"intent": "generate|regenerate|revise|discuss|help|out_of_scope", "question_number": null, "bloom_level": "C1|C2|C3|C4 atau null", "instruction": "arahan perbaikan dari pengguna atau null"}}"""

DISCUSSION_PROMPT = """Jawab pertanyaan pengguna tentang Soal #{number} berikut.

SOAL #{number}
- Pertanyaan: {question}
- Tipe: {question_type}
- Level Bloom: {bloom_level}
- Jawaban ideal: {answer}
- Penjelasan: {explanation}
- Poin materi: {knowledge_point}
- Kutipan bukti (grounding evidence): {grounding_evidence}
- Referensi: {source_reference}
- Status validasi: {status}
- Catatan validasi terakhir: {validation_note}

MATERI BUKU (sumber soal):
{context}

RIWAYAT PERCAKAPAN (terbaru di bawah):
{history}

PERTANYAAN PENGGUNA:
{message}

Jika pengguna ingin soal diubah, jawab singkat lalu sarankan perintah seperti "Buat ulang soal nomor {number}" atau "Soal nomor {number} <arahan perbaikan>".

Format output JSON:
{{"reply": "jawaban Anda (boleh memakai markdown sederhana)"}}"""
