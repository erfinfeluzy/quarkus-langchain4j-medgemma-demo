# Benchmark TTFT

Mengukur waktu sampai token pertama (TTFT) dan metrik efisiensi lain untuk paper (RQ3, Tabel 4), lewat aplikasi
yang sebenarnya: Redis, MySQL dan Ollama tetap berjalan seperti pemakaian biasa.

## Empat skenario

| Skenario | Endpoint | Jalur yang diukur |
|---|---|---|
| `baseline` | `POST /chat/baseline` | MedGemma saja: tanpa qwen, RAG, tools, riwayat. Grounding "None" |
| `rag` | `POST /chat` | qwen2.5 memutuskan tanpa tool → embedding + pencarian Redis → MedGemma |
| `tools` | `POST /chat` | qwen2.5 memanggil tool → MySQL (FHIR) → MedGemma. **Tanpa RAG**, sesuai desain aplikasi |
| `image` | `POST /chat/image` | MedGemma vision dengan gambar |

`baseline` memakai pertanyaan yang sama dengan `rag` (B01 = R01, dst.), jadi selisih keduanya bisa diuji berpasangan
(Wilcoxon signed-rank). Pertanyaan ada di [questions.csv](questions.csv): 20 per skenario.

## Cara kerja

- Request dengan header `X-Benchmark: true` mendapat event SSE terakhir berisi waktu per tahap yang diukur di server
  (`System.nanoTime`, lihat `Metrics.java`). Header ini hanya berlaku kalau `med.benchmark.enabled=true`
  (otomatis di dev mode; di container: env `MED_BENCHMARK_ENABLED=true`). Endpoint `/chat/baseline` juga hanya ada saat itu.
- Request benchmark diisolasi: riwayat chat sementara per request (dihapus setelah selesai) dan tidak memakai
  "pasien terakhir", supaya prompt tidak bertambah panjang selama benchmark.
- Klien mengukur TTFT-nya sendiri (request dikirim sampai token pertama yang tidak kosong tiba) di samping angka server.
- `nvidia-smi` dicatat tiap 100 ms untuk daya dan VRAM GPU per request.

## Menjalankan

```powershell
# Dari folder project, aplikasi sudah jalan (dev mode atau container dengan MED_BENCHMARK_ENABLED=true)
java bench/Benchmark.java --reps 5 --warmup 1
# Opsi: --url http://localhost:8081  --seed 42  --only rag,tools  --questions bench/questions.csv
```

Hasil masuk ke `bench/results/<tanggal-jam>/`:

| File | Isi |
|---|---|
| `results.csv` | Satu baris per request: TTFT klien dan server, waktu per tahap, token, tokens/s, daya dan energi GPU, VRAM puncak |
| `summary.csv` | Median, p95, rata-rata, min, maks per skenario; subset `first` (putaran 1) dan `repeat` (putaran 2+) |
| `answers.tsv` | Jawaban lengkap tiap request, untuk memeriksa kualitas |
| `environment.txt` | Commit git, versi Ollama, model dan digest, `ollama ps`, GPU, power plan, status AC/baterai |

## Kolom waktu

| Kolom | Dari | Sampai |
|---|---|---|
| `routing_ms` | request diterima | qwen2.5 selesai memilih tool, termasuk query MySQL |
| `retrieval_ms` | AI service MedGemma dipanggil | embedding pertanyaan dan pencarian Redis selesai (RAG saja) |
| `medgemma_ttft_ms` | MedGemma mulai dipanggil (setelah retrieval) | token pertama MedGemma |
| `server_ttft_ms` | request diterima | token pertama: **TTFT sistem** |
| `client_ttft_ms` | klien mengirim request | klien menerima token pertama (termasuk HTTP dan upload gambar) |
| `generate_ms`, `tokens_per_s` | token pertama | jawaban selesai; tokens/s = (token − 1) / waktu generate |

`route_ok` = false berarti qwen memilih jalur lain dari yang diharapkan (misalnya pertanyaan klinik dijawab lewat tools);
baris itu tidak masuk ringkasan, tapi jumlahnya dilaporkan (`route_ok` di `summary.csv`) dan juga merupakan hasil.

## Protokol untuk paper

1. Laptop tersambung listrik, power plan tetap, tidak ada aplikasi lain yang memakai GPU. Matikan container yang
   tidak dipakai (misalnya `docker stop open-webui`).
2. Pastikan semua model 100% di GPU (`docker exec ollama ollama ps`) dan tidak ada model lain yang ikut dimuat.
3. Jalankan dengan `--reps 5 --warmup 1`. Putaran pemanasan memuat semua model ke VRAM dan tidak dicatat.
4. Laporkan median dan p95 dengan n, dari subset `first` sebagai TTFT pertanyaan baru, dan sebutkan efek cache dari
   selisih `first` dan `repeat` (lihat di bawah).
5. Energi utama tetap dari power meter di stop kontak; kolom GPU hanya daya kartu grafis, sebagai pelengkap.
6. Simpan seluruh folder hasil sebagai data tambahan (supplementary material).

## Konfigurasi Ollama yang dipakai

Container `ollama` (lihat `docker-run.sh`): Ollama 0.40.4, `OLLAMA_CONTEXT_LENGTH=8192`, `OLLAMA_FLASH_ATTENTION=1`,
`LLAMA_ARG_CACHE_RAM=0`, `OLLAMA_NUM_PARALLEL=1` (default). VM Docker/WSL2 diberi `memory=10GB` dan `swap=8GB` di
`%UserProfile%\.wslconfig`. Ketiga model (MedGemma, qwen2.5, nomic-embed) tetap dimuat bersamaan, 100% di GPU.

## Hal yang harus disebut di paper

- **Prompt cache llama.cpp dimatikan** (`LLAMA_ARG_CACHE_RAM=0`). Default-nya llama-server di dalam Ollama menyimpan
  prompt sebelumnya di RAM sampai 8 GB per model. Proses MedGemma tumbuh sampai 7 GB RAM, VM masuk swap, dan TTFT p95
  naik ke 2.5 sampai 3.4 s; pertanyaan yang diulang juga jadi lebih cepat secara tidak realistis (gambar yang sama:
  1.2 s menjadi 0.25 s). Tanpa cache itu, awalan prompt yang sama dengan request sebelumnya tetap dipakai ulang lewat
  KV cache slot, seperti pemakaian nyata. Subset `first` dan `repeat` tetap dilaporkan sebagai pemeriksaan.
- **RAM adalah batas utama di laptop 16 GB**, bukan VRAM. Dengan VM Docker default (7.6 GB) llama-server dibunuh
  OOM killer saat ketiga model dimuat (terlihat di `dmesg`), dan request yang sedang berjalan gagal.
- **Context 8192 token** untuk semua model lewat `OLLAMA_CONTEXT_LENGTH` (dan Modelfile `medgemma-4b-it-8k:q4_k_m`).
  Extension Ollama quarkus-langchain4j 1.13.3 mengirim opsi context dengan nama `numCtx`, yang diabaikan Ollama
  ("invalid option provided"), jadi `model-options.num-ctx` di application.properties tidak berpengaruh. Dengan 32K
  yang sebelumnya diset di container, VRAM hampir penuh dan model saling dikeluarkan sehingga TTFT melonjak 8 sampai 13 s.
- **Jumlah token output** dihitung dari jumlah chunk stream (Ollama mengirim satu token per chunk), karena extension
  yang sama tidak mengisi jumlah token saat streaming. Jumlah token input tidak tersedia.
- **TTFT skenario `rag` dan `tools` sudah termasuk qwen2.5** (`routing_ms`), karena setiap pertanyaan teks lewat
  router itu dulu. Skenario `image` dan `baseline` tidak.
- Untuk perbandingan kuantisasi (Q8_0, BF16), buat varian 8K yang sama untuk tiap file GGUF dan ganti
  `quarkus.langchain4j.ollama.chat-model.model-id`. BF16 MedGemma 4B (sekitar 8 GB) tidak muat penuh di VRAM 8 GB;
  catat pembagian CPU/GPU dari `ollama ps`.
