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

    @Tool("Find patients by (part of) their name. Returns a FHIR R4 Bundle with each matching Patient "
            + "(medical record number, gender, birth date) and their Condition (diagnoses, ICD-10), "
            + "AllergyIntolerance, MedicationStatement (current medications) and Encounter (visits, polyclinic, doctor).")
    public Map<String, Object> findPatient(@P("Full or partial patient name") String name) {
        Log.infof("Tool findPatient(name=%s)", name);
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
        List<Map<String, Object>> resources = new ArrayList<>();
        for (Map<String, Object> patient : fhir.findPatients(name)) {
            resources.addAll(fhir.observations(Integer.parseInt((String) patient.get("id"))));
        }
        return FhirRepository.bundle(resources);
    }

    @Tool("List the visits (FHIR R4 Encounter resources: patient, doctor, visit date) of a polyclinic. "
            + "Polyclinics: Umum, Penyakit Dalam, Jantung, Anak, Kandungan.")
    public Map<String, Object> listPatientsByPolyclinic(@P("Polyclinic name") String polyclinic) {
        Log.infof("Tool listPatientsByPolyclinic(polyclinic=%s)", polyclinic);
        // The model often passes "Poli Jantung" instead of "Jantung"
        return FhirRepository.bundle(fhir.encountersByServiceType(polyclinic.replaceFirst("(?i)^poli\\s+", "").trim()));
    }
}
