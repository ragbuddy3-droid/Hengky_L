# PRD — RAG-AQG: Sistem Automatic Question Generation Berbasis RAG (v3)

## 0. Informasi Dokumen

1. Nama Produk: RAG-AQG (Retrieval-Augmented Generation for Automatic Question Generation)
2. Pemilik Proyek: Hengky Laurencio
3. Versi: 3.0
4. Dokumen Terkait: `ARCHITECTURE.md`

---

## 1. Ringkasan Produk

RAG-AQG v3 adalah aplikasi web modern (Next.js + FastAPI) yang mengubah dokumen buku pelajaran digital (PDF) menjadi soal ujian pilihan ganda secara otomatis, lengkap dengan kunci jawaban dan label tingkat kognitif Taksonomi Bloom. Pengguna berinteraksi melalui antarmuka web interaktif berbasis Mantine UI: mengunggah buku, meminta soal per bab/topik, dan menerima soal yang sudah tervalidasi otomatis tanpa perlu diperiksa manual sebelum digunakan.

---

## 2. Masalah yang Dipecahkan

1. Menyusun soal ujian berkualitas secara manual memakan banyak waktu pendidik.
2. Soal yang dihasilkan LLM murni rawan halusinasi (fakta/kunci jawaban tidak sesuai materi sumber).
3. Label tingkat kesulitan kognitif dari LLM murni sering tidak konsisten dengan Taksonomi Bloom.

---

## 3. Target Pengguna

1. **Pendidik/Guru** — pengguna utama, mengunggah buku dan meminta soal.
2. **Admin Operasional** — mengelola dokumen di Knowledge Base dan konfigurasi sistem (threshold validator, daftar mata pelajaran aktif).
3. **Peneliti/Pengembang** — memantau metrik performa sistem (tingkat penolakan validator, jumlah iterasi refinement, waktu respons).

---

## 4. Tujuan & Metrik Keberhasilan

| Tujuan | Metrik |
|---|---|
| 1. Otomatisasi pembuatan soal end-to-end | Soal dapat dihasilkan dari upload dokumen hingga tampil ke pengguna tanpa langkah manual |
| 2. Menekan halusinasi | Grounding Score rata-rata soal final ≥ threshold yang ditentukan (mis. 0.75) |
| 3. Konsistensi label Bloom | Persentase soal yang lolos rubrik LLM-as-Judge pada percobaan pertama |
| 4. Responsivitas | Waktu rata-rata generasi 1 soal (termasuk refinement) berada dalam batas yang wajar untuk pemakaian interaktif |

---

## 5. Ruang Lingkup (v3)

### 5.1 Fitur Utama (v3)
1. Upload dan manajemen dokumen PDF (buku pelajaran) dengan Mantine Dropzone & Table UI.
2. Ekstraksi teks otomatis + pembersihan noise (header, footer, ISBN, nomor halaman).
3. Segmentasi teks pedagogis (Pedagogical Adaptive Chunking / PAC).
4. Knowledge Base dengan pencarian hybrid (dense + sparse).
5. Chat interaktif Next.js (Mantine UI) dengan riwayat percakapan bertingkat.
6. Generasi soal pilihan ganda + kunci jawaban + label Bloom.
7. Validasi dua lapis (Grounding Score + LLM-as-Judge) berjalan otomatis di background setiap soal dibuat.
8. Self-Refinement Loop otomatis saat soal gagal validasi.
9. Audit viewer log hasil validasi & refinement per soal.

---

## 6. Arsitektur Teknologi v3

- **Backend**: Python 3.11+, FastAPI, `uv`, Pydantic v2, LlamaIndex/LangChain, Qdrant/ChromaDB.
- **Frontend**: Next.js 14/15 App Router, TypeScript, Mantine UI v7, `bun`.
- **Inference**: Ollama / vLLM local LLM inference.
