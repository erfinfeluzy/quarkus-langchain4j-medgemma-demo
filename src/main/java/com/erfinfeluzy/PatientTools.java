package com.erfinfeluzy;

import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;
import io.quarkus.logging.Log;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Read-only tools the model can call to look up (fictional) patient records. Results are FHIR R4
 * Bundles built by {@link FhirRepository}; every query is parameterized, the model never writes SQL.
 */
@ApplicationScoped
public class PatientTools {

    @Inject
    FhirRepository fhir;

    // Deskripsi tool hanya dibaca model kecil pemanggil tool (qwen2.5 3B): bahasa sederhana lebih akurat daripada istilah FHIR
    @Tool("Find patients by (part of) their name: their diagnoses, allergies, current medications and visits.")
    public Map<String, Object> findPatient(@P("Full or partial patient name") String name) {
        Log.infof("Tool findPatient(name=%s)", name);
        if (isBlank(name)) {
            return missingArgument("name");
        }
        List<Map<String, Object>> resources = new ArrayList<>();
        for (Map<String, Object> patient : fhir.findPatients(name)) {
            resources.add(patient);
            resources.addAll(fhir.clinicalRecord(Integer.parseInt((String) patient.get("id"))));
        }
        return FhirRepository.bundle(resources);
    }

    @Tool("Get the laboratory results of a patient, newest first, as a FHIR R4 Bundle of Observation resources "
            + "(LOINC code, value, unit, reference range and interpretation: H = high, N = normal, L = low).")
    public Map<String, Object> labResults(@P("Full or partial patient name") String name) {
        Log.infof("Tool labResults(name=%s)", name);
        if (isBlank(name)) {
            return missingArgument("name");
        }
        List<Map<String, Object>> resources = new ArrayList<>();
        for (Map<String, Object> patient : fhir.findPatients(name)) {
            resources.addAll(fhir.observations(Integer.parseInt((String) patient.get("id"))));
        }
        return FhirRepository.bundle(resources);
    }

    @Tool("List which patients visited a polyclinic (patient, doctor, visit date). Not for the polyclinic's "
            + "schedule or opening hours. Polyclinics: Umum, Penyakit Dalam, Jantung, Anak, Kandungan.")
    public Map<String, Object> listPatientsByPolyclinic(@P("Polyclinic name") String polyclinic) {
        Log.infof("Tool listPatientsByPolyclinic(polyclinic=%s)", polyclinic);
        if (isBlank(polyclinic)) {
            return missingArgument("polyclinic");
        }
        // The model often passes "Poli Jantung" instead of "Jantung"
        return FhirRepository.bundle(fhir.encountersByServiceType(polyclinic.replaceFirst("(?i)^poli\\s+", "").trim()));
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    /**
     * Rejects a call without its required argument (the 3B router sometimes sends {}) instead of querying. Returned,
     * not thrown; ChatResource sees it as no data and fills in the patient named in the message deterministically.
     */
    private static Map<String, Object> missingArgument(String argument) {
        Log.warnf("Tool call rejected: missing %s", argument);
        return Map.of("resourceType", "OperationOutcome", "issue", List.of(Map.of(
                "severity", "error", "code", "required", "diagnostics", "Missing argument '" + argument + "'.")));
    }
}
