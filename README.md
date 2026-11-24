# Offline Medical AI Assistant with MedGemma, RAG on Redis and FHIR Tools

Demo pribadi: asisten AI untuk klinik fiktif **Klinik Sehat Sentosa** yang berjalan sepenuhnya offline di satu laptop
dengan GPU 8 GB. Aplikasi Quarkus (JVM mode) dengan LangChain4j dan Ollama:

- **MedGemma 4B** (Q4_K_M) menjawab pertanyaan teks dan membaca gambar medis
- **Qwen2.5 3B** sebagai router yang memanggil tool pasien, karena MedGemma 4B tidak bisa memanggil tool di Ollama
- **RAG** atas dokumen klinik di `rag-docs/`, embedding `nomic-embed-text` disimpan di Redis
- **Tool FHIR R4** yang membaca rekam medis pasien fiktif dari MySQL

Project ini juga menjadi artefak penelitian "Sovereign Generative AI at the Edge" tentang asisten klinis offline untuk
puskesmas terpencil; benchmark-nya ada di [`bench/`](bench/README.md).
Diturunkan dari [quarkus-rag-redis-demo](https://github.com/erfinfeluzy/quarkus-rag-redis-demo).

> **Disclaimer:** semua data pasien, dokter, dan klinik di project ini fiktif. Jawaban AI hanya informasi umum dan
> bukan pengganti konsultasi dengan tenaga medis. Jangan isi dengan data pasien sungguhan.

## Apa yang bisa ditanyakan

| Sumber                    | Isi                                                              | Contoh pertanyaan                                   |
| ------------------------- | ---------------------------------------------------------------- | --------------------------------------------------- |
| RAG (`rag-docs/*.txt`)    | Info klinik, jadwal dokter, tarif, panduan obat, nilai normal lab | "Kapan jadwal Poli Jantung?", "Berapa dosis paracetamol?" |
| Tools (MySQL `clinic`)    | Rekam medis pasien dalam format FHIR R4                          | "Bagaimana hasil lab Bambang Sutrisno?", "Siapa saja pasien Poli Anak?" |
| Gambar (upload 📎)        | MRI, rontgen, CT atau foto hasil lab (JPG/PNG/WebP, maks 10 MB)  | Contoh gambar ada di [`sample-image/`](sample-image/README.md) |

Tools yang bisa dipanggil model ada di `PatientTools.java` (semua read-only, query ber-parameter) dan mengembalikan
FHIR R4 `Bundle`:

- `findPatient(name)`: `Patient`, `Condition`, `AllergyIntolerance`, `MedicationStatement`, `Encounter`
- `labResults(name)`: `Observation` hasil lab, terbaru dulu
- `listPatientsByPolyclinic(polyclinic)`: `Encounter` per poli (Umum, Penyakit Dalam, Jantung, Anak, Kandungan)

## Alur request

Satu pertanyaan melewati salah satu dari tiga jalur (`ChatResource.java`):

```text
POST /chat ──► Qwen2.5 3B router (PatientDataAgent + PatientTools)
                 ├─ tool menemukan data pasien ──► MedGemma 4B (PatientAssistant), data FHIR di prompt, tanpa RAG
                 └─ tidak ada data pasien ───────► MedGemma 4B (Assistant) dengan RAG Redis + chat memory
POST /chat/image ───────────────────────────────► MedGemma 4B vision (ImageAssistant), tanpa RAG/tools/memory
```

- Router hanya memilih dan memanggil tool; teks jawabannya dibuang. Kalau router memanggil tool tanpa nama pasien,
  nama diambil dari pesan (atau pasien terakhir yang dibahas) tanpa putaran router kedua.
- Chat memory disimpan di Redis (key `med-chat:personal`, 20 pesan terakhir). Pasien terakhir diingat, jadi
  pertanyaan lanjutan seperti "obatnya apa saja?" tetap merujuk ke pasien yang sama.
- Ketiga model berbagi satu GPU 8 GB (puncak sekitar 7 GB). Ollama dijalankan dengan context 8192, flash attention,
  dan prompt cache di RAM host dimatikan (`LLAMA_ARG_CACHE_RAM=0`); lihat `docker-run.sh`.

## Data pasien format FHIR R4

Schema `clinic` disusun satu tabel per resource FHIR R4 (`db/init.sql`), lalu `FhirRepository.java` memetakan barisnya
ke JSON FHIR yang dipakai oleh tools AI. Ini hanya untuk demo: tidak ada FHIR REST API, validasi profil, atau operasi tulis.

| Tabel                  | Resource FHIR         | Kode                                       |
| ---------------------- | --------------------- | ------------------------------------------ |
| `patient`              | `Patient`             | `identifier` = nomor rekam medis           |
| `practitioner`         | `Practitioner`        | dirujuk dari `Encounter.participant`       |
| `encounter`            | `Encounter`           | class `AMB`, `serviceType` = poli          |
| `clinical_condition`   | `Condition`           | ICD-10                                     |
| `allergy_intolerance`  | `AllergyIntolerance`  | SNOMED CT (sebagian hanya teks)            |
| `medication_statement` | `MedicationStatement` | teks (belum memakai kode KFA)              |
| `observation`          | `Observation`         | LOINC, satuan UCUM, `referenceRange`       |

`observation.interpretation` (H/N/L) adalah generated column di MySQL yang dihitung dari nilai dan batas normal.
Model hanya membaca kode itu dan tidak membandingkan angka sendiri.

Kode ICD-10, LOINC, dan SNOMED CT di data demo belum diverifikasi ke sumber resminya. Cek dulu sebelum dipakai di luar demo.

## Arsitektur

Aplikasi ini memakai container MySQL, Redis, dan Ollama yang sama dengan demo HR, di network `demo-net`.
Datanya dipisah, jadi kedua demo bisa jalan bersamaan tanpa saling ganggu:

- **MySQL**: schema `clinic` dengan user `clinic_app` yang hanya punya akses ke schema itu (demo HR memakai `hr`)
- **Redis**: index `med-rag-index` dengan prefix key `med-rag:` (demo HR memakai `rag-index` / `rag:`).
  `POST /rag/reindex` hanya menghapus key `med-rag:*`. Chat memory memakai key `med-chat:*`

| Service  | Container    | Alamat dari dalam network              | Port di laptop |
| -------- | ------------ | -------------------------------------- | -------------- |
| MySQL    | `demo-mysql` | `jdbc:mysql://demo-mysql:3306/clinic`  | `3306`         |
| Redis    | `demo-redis` | `redis://demo-redis:6379`              | `6379`         |
| Ollama   | `ollama`     | `http://ollama:11434`                  | `11434`        |
| Aplikasi | `med-app`    | `http://med-app:8080`                  | `8081`         |

## Requirement

- Docker Desktop, bisa juga diganti Podman
- JDK 25 (untuk build jar dengan `mvnw`)
- GPU NVIDIA + driver terbaru untuk Ollama (`--gpus all`). Tanpa GPU, hapus opsi `--gpus all`; Ollama tetap jalan tapi lebih lambat
- VRAM minimal 8 GB supaya ketiga model dimuat sekaligus di GPU (diuji di NVIDIA GeForce RTX 5060 Laptop GPU)
- HDD sekitar 6 GB untuk model berikut (di-pull otomatis oleh `docker-run`):

| Model Ollama                               | Peran                                                                         |
| ------------------------------------------ | ----------------------------------------------------------------------------- |
| `hf.co/unsloth/medgemma-4b-it-GGUF:Q4_K_M` | Menjawab teks dan gambar, lewat varian `medgemma-4b-it-8k:q4_k_m` (`num_ctx 8192`) |
| `qwen2.5:3b`                               | Router: memanggil tool pasien                                                 |
| `nomic-embed-text`                         | Embedding untuk RAG                                                           |

## Cara cepat

Script menjalankan semua service, build image kalau belum ada, lalu menjalankan aplikasi:

```powershell
.\docker-run.cmd          # CMD / PowerShell
./docker-run.sh           # Git Bash
```

Perintah lain: `mysql`, `schema` (reset data pasien), `redis`, `ollama`, `app`, `build`, `redeploy`, `status`, `stop`.
Langkah manual satu per satu ada di `docker-run.txt`.

## Langkah manual

Perintah di bawah ditulis untuk PowerShell dan dijalankan dari folder project. Container `demo-mysql`, `demo-redis`,
dan `ollama` diasumsikan sudah ada dari demo HR.

```powershell
docker start demo-mysql demo-redis ollama

# Model (sekali saja). Varian 8k memakai file model yang sama, tidak menambah disk
docker exec ollama ollama pull qwen2.5:3b
docker exec ollama ollama pull hf.co/unsloth/medgemma-4b-it-GGUF:Q4_K_M
docker exec ollama sh -c "printf 'FROM hf.co/unsloth/medgemma-4b-it-GGUF:Q4_K_M\nPARAMETER num_ctx 8192\n' > /tmp/Modelfile && ollama create medgemma-4b-it-8k:q4_k_m -f /tmp/Modelfile"
docker exec ollama ollama pull nomic-embed-text

# Buat schema clinic + user clinic_app + data pasien fiktif (sekali saja; menjalankan ulang = reset schema clinic)
Get-Content db/init.sql | docker exec -i demo-mysql mysql -uroot -prootpass

.\mvnw.cmd package -DskipTests
docker build -f src/main/docker/Dockerfile.jvm -t quarkus/demo-med-ai-jvm .

docker run -d --name med-app --network demo-net `
  -p 127.0.0.1:8081:8080 `
  -v "${PWD}/rag-docs:/deployments/rag-docs:ro" `
  -e QUARKUS_LANGCHAIN4J_EASY_RAG_PATH=/deployments/rag-docs `
  quarkus/demo-med-ai-jvm
```

## Mencoba aplikasi

Buka <http://localhost:8081> (atau <http://localhost:8080> di dev mode), atau lewat curl:

```powershell
# Chat (respons berupa stream Server-Sent Events)
curl.exe -N -X POST http://localhost:8081/chat -H "Content-Type: text/plain" -d "Kapan jadwal Poli Jantung?"
curl.exe -N -X POST http://localhost:8081/chat -H "Content-Type: text/plain" -d "Bagaimana hasil lab Bambang Sutrisno?"

# Upload gambar medis (MRI, rontgen, CT; JPG/PNG/WebP maks 10 MB), dijelaskan oleh MedGemma. File DICOM ekspor dulu ke PNG
curl.exe -N -X POST http://localhost:8081/chat/image -F "message=Tolong jelaskan hasil MRI ini" -F "file=@mri.png;type=image/png"

# Jumlah segmen dokumen RAG di Redis (hanya key med-rag:*)
curl.exe http://localhost:8081/rag/status

# Baca ulang dokumen di rag-docs setelah ada perubahan
curl.exe -X POST http://localhost:8081/rag/reindex
```

Dokumen di `rag-docs` hanya di-ingest otomatis saat aplikasi start dan belum ada key `med-rag:*` di Redis. Setelah
mengubah atau menambah file `.txt` di folder itu, panggil `POST /rag/reindex`.

## Benchmark

`bench/Benchmark.java` mengukur waktu sampai token pertama (TTFT), tokens/s, VRAM dan energi GPU per request untuk
empat skenario: `baseline` (MedGemma saja), `rag`, `tools` (data pasien) dan `image`. Benchmark butuh
`MED_BENCHMARK_ENABLED=true` (otomatis di dev mode):

```powershell
$env:MED_BENCHMARK_ENABLED = "true"; .\docker-run.cmd redeploy
java bench/Benchmark.java --reps 5 --warmup 1
```

Hasil run terakhir (`bench/results/20261110-175216`, 400 request, RTX 5060 Laptop 8 GB):

| Skenario   | Median TTFT (klien) | Jalur                                                         |
| ---------- | ----------- | ------------------------------------------------------------- |
| `baseline` | 0,10 s      | MedGemma tanpa grounding                                      |
| `rag`      | 0,54 s      | Router + pencarian Redis + MedGemma                           |
| `tools`    | 2,14 s      | Router + query FHIR + MedGemma; router sekitar 79% dari waktu |
| `image`    | 1,11 s      | MedGemma vision                                               |

VRAM puncak 7.050 MiB dengan ketiga model dimuat, energi GPU 0,009–0,045 Wh per request. Cara kerja, kolom hasil
dan protokolnya ada di [bench/README.md](bench/README.md).

## Struktur folder

| Folder          | Isi                                                                            |
| --------------- | ------------------------------------------------------------------------------ |
| `src/`          | Aplikasi Quarkus: REST endpoint, AI service, tool FHIR, UI chat (`index.html`) |
| `db/init.sql`   | Schema `clinic`, user `clinic_app` dan data pasien fiktif                      |
| `rag-docs/`     | Dokumen pengetahuan klinik untuk RAG                                           |
| `sample-image/` | Contoh gambar MRI publik dari Wikimedia Commons                                |
| `bench/`        | Benchmark TTFT dan efisiensi, beserta hasil mentahnya                          |
| `docs/figures/` | Gambar untuk paper                                                             |

## Troubleshooting

- **`Unknown database 'clinic'` / `Access denied for user 'clinic_app'`**: schema belum dibuat, jalankan `init.sql`
  seperti di langkah manual (atau `.\docker-run.cmd schema`).
- **Ingin reset data pasien**: jalankan ulang `init.sql`. Hanya schema `clinic` yang di-drop, schema `hr` aman.
- **Aplikasi gagal konek ke MySQL saat start**: tunggu sampai
  `docker exec demo-mysql mysqladmin ping -h 127.0.0.1 -uroot -prootpass` berhasil, lalu `docker restart med-app`.
- **Chat lambat atau timeout**: pastikan model sudah di-pull dan Ollama memakai GPU (`docker exec ollama nvidia-smi`).
  `docker exec ollama ollama ps` harus menunjukkan `100% GPU`; kalau sebagian di CPU, VRAM tidak cukup untuk ketiga model.

## Dev mode

MySQL, Redis, dan Ollama tetap di Docker, aplikasi jalan langsung di laptop (profil `%dev` memakai
`localhost:3306` dan `localhost:6379`):

```powershell
.\mvnw.cmd quarkus:dev
```

Dev UI tersedia di <http://localhost:8080/q/dev/>. Kalau demo HR juga jalan di dev mode, salah satunya perlu port lain,
misalnya `.\mvnw.cmd quarkus:dev "-Dquarkus.http.port=8082"`.
