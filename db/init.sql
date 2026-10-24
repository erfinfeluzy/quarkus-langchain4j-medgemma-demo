-- Schema clinic dibuat di MySQL yang sudah ada (demo-mysql), terpisah dari schema hr.
-- Jalankan sebagai root:  docker exec -i demo-mysql mysql -uroot -prootpass < db/init.sql
-- Semua data pasien di bawah FIKTIF, hanya untuk demo.
--
-- Tiap tabel mengikuti satu resource FHIR R4 (lihat FhirRepository untuk pemetaan ke JSON):
--   patient -> Patient, practitioner -> Practitioner, encounter -> Encounter,
--   clinical_condition -> Condition (ICD-10), allergy_intolerance -> AllergyIntolerance (SNOMED CT),
--   medication_statement -> MedicationStatement, observation -> Observation (LOINC, UCUM)
DROP DATABASE IF EXISTS clinic;
CREATE DATABASE clinic;
CREATE USER IF NOT EXISTS 'clinic_app'@'%' IDENTIFIED BY 'clinic_app_pass';
GRANT ALL PRIVILEGES ON clinic.* TO 'clinic_app'@'%';
USE clinic;

CREATE TABLE patient (
    id            INT PRIMARY KEY,
    mrn           VARCHAR(20)   NOT NULL UNIQUE COMMENT 'Nomor rekam medis (Patient.identifier)',
    name          VARCHAR(100)  NOT NULL,
    gender        ENUM('male', 'female', 'other', 'unknown') NOT NULL COMMENT 'FHIR AdministrativeGender',
    birth_date    DATE          NOT NULL
);

CREATE TABLE practitioner (
    id            INT PRIMARY KEY,
    name          VARCHAR(100)  NOT NULL,
    qualification VARCHAR(100)  NOT NULL
);

-- Kunjungan rawat jalan; service_type = poliklinik
CREATE TABLE encounter (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    patient_id      INT          NOT NULL,
    practitioner_id INT          NOT NULL,
    service_type    VARCHAR(50)  NOT NULL,
    status          VARCHAR(20)  NOT NULL DEFAULT 'finished',
    period_start    DATE         NOT NULL,
    FOREIGN KEY (patient_id) REFERENCES patient(id),
    FOREIGN KEY (practitioner_id) REFERENCES practitioner(id)
);

-- "condition" adalah reserved word di MySQL, jadi tabelnya clinical_condition
CREATE TABLE clinical_condition (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    patient_id      INT          NOT NULL,
    encounter_id    INT          NULL,
    icd10_code      VARCHAR(10)  NOT NULL,
    display         VARCHAR(150) NOT NULL,
    clinical_status VARCHAR(20)  NOT NULL DEFAULT 'active',
    recorded_date   DATE         NOT NULL,
    FOREIGN KEY (patient_id) REFERENCES patient(id),
    FOREIGN KEY (encounter_id) REFERENCES encounter(id)
);

CREATE TABLE allergy_intolerance (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    patient_id      INT          NOT NULL,
    category        ENUM('food', 'medication', 'environment', 'biologic') NOT NULL,
    snomed_code     VARCHAR(20)  NULL COMMENT 'Kosong kalau hanya teks',
    substance       VARCHAR(100) NOT NULL,
    FOREIGN KEY (patient_id) REFERENCES patient(id)
);

CREATE TABLE medication_statement (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    patient_id      INT          NOT NULL,
    medication      VARCHAR(100) NOT NULL,
    dosage          VARCHAR(100) NOT NULL,
    status          VARCHAR(20)  NOT NULL DEFAULT 'active',
    FOREIGN KEY (patient_id) REFERENCES patient(id)
);

-- interpretation dihitung MySQL dari nilai dan batas normal (kode FHIR: L = low, N = normal, H = high),
-- jadi model tidak perlu membandingkan angka sendiri
CREATE TABLE observation (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    patient_id      INT          NOT NULL,
    category        VARCHAR(20)  NOT NULL DEFAULT 'laboratory',
    status          VARCHAR(20)  NOT NULL DEFAULT 'final',
    loinc_code      VARCHAR(10)  NOT NULL,
    display         VARCHAR(100) NOT NULL,
    value_quantity  DECIMAL(10,2) NULL,
    value_string    VARCHAR(50)  NULL,
    unit            VARCHAR(20)  NULL COMMENT 'Kode UCUM',
    ref_low         DECIMAL(10,2) NULL,
    ref_high        DECIMAL(10,2) NULL,
    ref_text        VARCHAR(50)  NULL,
    interpretation  CHAR(1) AS (CASE
                        WHEN value_quantity IS NULL THEN NULL
                        WHEN ref_low  IS NOT NULL AND value_quantity < ref_low  THEN 'L'
                        WHEN ref_high IS NOT NULL AND value_quantity > ref_high THEN 'H'
                        ELSE 'N' END) STORED,
    effective_date  DATE         NOT NULL,
    FOREIGN KEY (patient_id) REFERENCES patient(id)
);

INSERT INTO practitioner (id, name, qualification) VALUES
(1, 'dr. Hana Lestari',        'Dokter Umum'),
(2, 'dr. Ratna Dewi, Sp.PD',   'Spesialis Penyakit Dalam'),
(3, 'dr. Arief Hakim, Sp.JP',  'Spesialis Jantung dan Pembuluh Darah'),
(4, 'dr. Bayu Pratama, Sp.A',  'Spesialis Anak'),
(5, 'dr. Melati Sari, Sp.OG',  'Spesialis Obstetri dan Ginekologi');

INSERT INTO patient (id, mrn, name, gender, birth_date) VALUES
(1,  'RM-0001', 'Bambang Sutrisno',  'male',   '1968-04-12'),
(2,  'RM-0002', 'Sri Wahyuni',       'female', '1975-09-30'),
(3,  'RM-0003', 'Joko Purnomo',      'male',   '1959-01-22'),
(4,  'RM-0004', 'Ani Kurniasih',     'female', '1990-06-05'),
(5,  'RM-0005', 'Rudi Hartono',      'male',   '1983-11-17'),
(6,  'RM-0006', 'Wulan Sari',        'female', '2018-03-08'),
(7,  'RM-0007', 'Teguh Santoso',     'male',   '1971-07-29'),
(8,  'RM-0008', 'Lestari Handayani', 'female', '1965-12-01'),
(9,  'RM-0009', 'Arif Rahman',       'male',   '2015-05-14'),
(10, 'RM-0010', 'Fitri Amalia',      'female', '1995-02-19');

INSERT INTO encounter (id, patient_id, practitioner_id, service_type, period_start) VALUES
(1,  1,  2, 'Penyakit Dalam', '2026-10-02'),
(2,  2,  2, 'Penyakit Dalam', '2026-09-18'),
(3,  3,  3, 'Jantung',        '2026-10-10'),
(4,  4,  5, 'Kandungan',      '2026-10-15'),
(5,  5,  2, 'Penyakit Dalam', '2026-08-27'),
(6,  6,  4, 'Anak',           '2026-10-20'),
(7,  7,  3, 'Jantung',        '2026-09-05'),
(8,  8,  2, 'Penyakit Dalam', '2026-10-08'),
(9,  9,  4, 'Anak',           '2026-07-30'),
(10, 10, 1, 'Umum',           '2026-10-12');

INSERT INTO clinical_condition (patient_id, encounter_id, icd10_code, display, recorded_date) VALUES
(1,  1,  'E11.9', 'Diabetes melitus tipe 2',                    '2026-10-02'),
(2,  2,  'I10',   'Hipertensi esensial (grade 1)',              '2026-09-18'),
(3,  3,  'I25.1', 'Penyakit jantung koroner stabil',            '2026-10-10'),
(4,  4,  'Z34.9', 'Kehamilan normal, trimester 2',              '2026-10-15'),
(5,  5,  'E78.5', 'Dislipidemia',                               '2026-08-27'),
(6,  6,  'J06.9', 'Infeksi saluran pernapasan atas akut (ISPA)', '2026-10-20'),
(7,  7,  'I10',   'Hipertensi esensial (grade 2)',              '2026-09-05'),
(8,  8,  'E11.9', 'Diabetes melitus tipe 2',                    '2026-10-08'),
(8,  8,  'I10',   'Hipertensi esensial',                        '2026-10-08'),
(9,  9,  'J45.9', 'Asma ringan',                                '2026-07-30'),
(10, 10, 'D50.9', 'Anemia defisiensi besi',                     '2026-10-12');

INSERT INTO allergy_intolerance (patient_id, category, snomed_code, substance) VALUES
(1, 'medication', '91936005',  'Penisilin'),
(3, 'medication', NULL,        'Sulfonamida (sulfa)'),
(5, 'food',       '300913006', 'Udang (shellfish)'),
(6, 'food',       '91930004',  'Telur'),
(8, 'medication', NULL,        'Ibuprofen');

INSERT INTO medication_statement (patient_id, medication, dosage) VALUES
(1,  'Metformin 500 mg',            '2x sehari setelah makan'),
(2,  'Amlodipin 5 mg',              '1x sehari'),
(3,  'Aspirin 80 mg',               '1x sehari'),
(3,  'Atorvastatin 20 mg',          '1x sehari malam hari'),
(4,  'Asam folat 400 mcg',          '1x sehari'),
(4,  'Tablet tambah darah',         '1x sehari'),
(5,  'Simvastatin 10 mg',           '1x sehari malam hari'),
(6,  'Paracetamol sirup',           'Bila demam'),
(7,  'Amlodipin 10 mg',             '1x sehari'),
(7,  'Candesartan 8 mg',            '1x sehari'),
(8,  'Metformin 850 mg',            '2x sehari setelah makan'),
(8,  'Amlodipin 5 mg',              '1x sehari'),
(9,  'Salbutamol inhaler',          'Bila sesak'),
(10, 'Tablet besi (sulfas ferosus)', '1x sehari');

-- Golongan darah (LOINC 883-9, ABO group)
INSERT INTO observation (patient_id, loinc_code, display, value_string, effective_date) VALUES
(1, '883-9', 'Golongan darah ABO', 'O',  '2026-07-01'),
(2, '883-9', 'Golongan darah ABO', 'A',  '2026-09-18'),
(3, '883-9', 'Golongan darah ABO', 'B',  '2026-10-10'),
(4, '883-9', 'Golongan darah ABO', 'AB', '2026-10-15'),
(5, '883-9', 'Golongan darah ABO', 'O',  '2026-05-20'),
(6, '883-9', 'Golongan darah ABO', 'A',  '2026-10-20'),
(7, '883-9', 'Golongan darah ABO', 'B',  '2026-09-05'),
(8, '883-9', 'Golongan darah ABO', 'O',  '2026-10-08'),
(9, '883-9', 'Golongan darah ABO', 'AB', '2026-07-30'),
(10,'883-9', 'Golongan darah ABO', 'A',  '2026-08-10');

INSERT INTO observation (patient_id, loinc_code, display, value_quantity, unit, ref_low, ref_high, ref_text, effective_date) VALUES
(1,  '1558-6',  'Gula darah puasa',  168,  'mg/dL', 70,   99,   '70 - 99 mg/dL',        '2026-07-01'),
(1,  '1558-6',  'Gula darah puasa',  132,  'mg/dL', 70,   99,   '70 - 99 mg/dL',        '2026-10-02'),
(1,  '4548-4',  'HbA1c',             7.4,  '%',     NULL, 5.6,  '< 5.7 %',              '2026-10-02'),
(2,  '2093-3',  'Kolesterol total',  205,  'mg/dL', NULL, 199,  '< 200 mg/dL',          '2026-09-18'),
(2,  '2160-0',  'Kreatinin',         0.9,  'mg/dL', 0.6,  1.1,  '0.6 - 1.1 mg/dL',      '2026-09-18'),
(3,  '13457-7', 'Kolesterol LDL',    96,   'mg/dL', NULL, 99,   '< 100 mg/dL',          '2026-10-10'),
(3,  '2571-8',  'Trigliserida',      180,  'mg/dL', NULL, 149,  '< 150 mg/dL',          '2026-10-10'),
(4,  '718-7',   'Hemoglobin',        11.2, 'g/dL',  11.0, 14.0, '11.0 - 14.0 g/dL (hamil)', '2026-10-15'),
(5,  '13457-7', 'Kolesterol LDL',    178,  'mg/dL', NULL, 99,   '< 100 mg/dL',          '2026-05-20'),
(5,  '13457-7', 'Kolesterol LDL',    131,  'mg/dL', NULL, 99,   '< 100 mg/dL',          '2026-08-27'),
(7,  '2160-0',  'Kreatinin',         1.3,  'mg/dL', 0.7,  1.3,  '0.7 - 1.3 mg/dL',      '2026-09-05'),
(8,  '1558-6',  'Gula darah puasa',  145,  'mg/dL', 70,   99,   '70 - 99 mg/dL',        '2026-10-08'),
(8,  '4548-4',  'HbA1c',             8.1,  '%',     NULL, 5.6,  '< 5.7 %',              '2026-10-08'),
(10, '718-7',   'Hemoglobin',        9.8,  'g/dL',  12.0, 15.5, '12.0 - 15.5 g/dL',     '2026-08-10'),
(10, '718-7',   'Hemoglobin',        11.6, 'g/dL',  12.0, 15.5, '12.0 - 15.5 g/dL',     '2026-10-12'),
(10, '2276-4',  'Feritin',           14,   'ng/mL', 15,   150,  '15 - 150 ng/mL',       '2026-10-12');
