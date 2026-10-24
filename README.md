# Medical AI Assistant with RAG on Redis and Tools

Demo pribadi: asisten AI untuk klinik fiktif **Klinik Sehat Sentosa**. Aplikasi Quarkus (JVM mode) dengan chat AI
berbasis Ollama, RAG (embedding disimpan di Redis), dan database MySQL berisi data pasien fiktif.
Diturunkan dari [quarkus-rag-redis-demo](https://github.com/erfinfeluzy/quarkus-rag-redis-demo).

> **Disclaimer:** semua data pasien, dokter, dan klinik di project ini fiktif. Jawaban AI hanya informasi umum dan
> bukan pengganti konsultasi dengan tenaga medis. Jangan isi dengan data pasien sungguhan.

## Apa yang bisa ditanyakan

| Sumber                    | Isi                                                              | Contoh pertanyaan                                   |
| ------------------------- | ---------------------------------------------------------------- | --------------------------------------------------- |
| RAG (`rag-docs/*.txt`)    | Info klinik, jadwal dokter, tarif, panduan obat, nilai normal lab | "Kapan jadwal Poli Jantung?", "Berapa dosis paracetamol?" |
| Tools (MySQL `clinic`)    | Rekam medis pasien dalam format FHIR R4                          | "Bagaimana hasil lab Bambang Sutrisno?", "Siapa saja pasien Poli Anak?" |

Tools yang bisa dipanggil model ada di `PatientTools.java` (semua read-only, query ber-parameter) dan mengembalikan
FHIR R4 `Bundle`:

- `findPatient(name)`: `Patient`, `Condition`, `AllergyIntolerance`, `MedicationStatement`, `Encounter`
- `labResults(name)`: `Observation` hasil lab, terbaru dulu
- `listPatientsByPolyclinic(polyclinic)`: `Encounter` per poli (Umum, Penyakit Dalam, Jantung, Anak, Kandungan)

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
  `POST /rag/reindex` hanya menghapus key `med-rag:*`

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
- HDD sekitar 6 GB untuk model `llama3.1:8b` dan `nomic-embed-text`

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

# Jumlah segmen dokumen RAG di Redis (hanya key med-rag:*)
curl.exe http://localhost:8081/rag/status

# Baca ulang dokumen di rag-docs setelah ada perubahan
curl.exe -X POST http://localhost:8081/rag/reindex
```

Dokumen di `rag-docs` hanya di-ingest otomatis saat aplikasi start dan belum ada key `med-rag:*` di Redis. Setelah
mengubah atau menambah file `.txt` di folder itu, panggil `POST /rag/reindex`.

## Troubleshooting

- **`Unknown database 'clinic'` / `Access denied for user 'clinic_app'`**: schema belum dibuat, jalankan `init.sql`
  seperti di langkah manual (atau `.\docker-run.cmd schema`).
- **Ingin reset data pasien**: jalankan ulang `init.sql`. Hanya schema `clinic` yang di-drop, schema `hr` aman.
- **Aplikasi gagal konek ke MySQL saat start**: tunggu sampai
  `docker exec demo-mysql mysqladmin ping -h 127.0.0.1 -uroot -prootpass` berhasil, lalu `docker restart med-app`.
- **Chat lambat atau timeout**: pastikan model sudah di-pull dan Ollama memakai GPU (`docker exec ollama nvidia-smi`).

## Dev mode

MySQL, Redis, dan Ollama tetap di Docker, aplikasi jalan langsung di laptop (profil `%dev` memakai
`localhost:3306` dan `localhost:6379`):

```powershell
.\mvnw.cmd quarkus:dev
```

Dev UI tersedia di <http://localhost:8080/q/dev/>. Kalau demo HR juga jalan di dev mode, salah satunya perlu port lain,
misalnya `.\mvnw.cmd quarkus:dev "-Dquarkus.http.port=8082"`.
