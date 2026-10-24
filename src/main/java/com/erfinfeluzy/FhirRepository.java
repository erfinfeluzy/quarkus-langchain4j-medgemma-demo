package com.erfinfeluzy;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import javax.sql.DataSource;

/**
 * Reads the clinic schema (one table per FHIR R4 resource, see db/init.sql) and maps the rows to
 * FHIR R4 JSON structures for the AI tools. Only the elements this demo needs are filled in; there
 * is no FHIR REST API, validation or write operations.
 */
@ApplicationScoped
public class FhirRepository {

    private static final String MRN = "https://klinik-sehat-sentosa.example/fhir/sid/mrn";
    private static final String ICD10 = "http://hl7.org/fhir/sid/icd-10";
    private static final String LOINC = "http://loinc.org";
    private static final String SNOMED = "http://snomed.info/sct";
    private static final String UCUM = "http://unitsofmeasure.org";
    private static final String TERMINOLOGY = "http://terminology.hl7.org/CodeSystem/";
    private static final Map<String, String> INTERPRETATIONS = Map.of("L", "Low", "N", "Normal", "H", "High");

    @Inject
    DataSource dataSource;

    public List<Map<String, Object>> findPatients(String name) {
        return query(FhirRepository::patient, "SELECT * FROM patient WHERE name LIKE ? ORDER BY name", "%" + name + "%");
    }

    /** Conditions, allergies, medications and encounters of one patient (lab results: see {@link #observations}). */
    public List<Map<String, Object>> clinicalRecord(int patientId) {
        List<Map<String, Object>> resources = new ArrayList<>();
        resources.addAll(query(FhirRepository::condition, """
                SELECT c.*, p.name AS patient_name FROM clinical_condition c JOIN patient p ON p.id = c.patient_id
                WHERE c.patient_id = ? ORDER BY c.recorded_date DESC""", patientId));
        resources.addAll(query(FhirRepository::allergy, """
                SELECT a.*, p.name AS patient_name FROM allergy_intolerance a JOIN patient p ON p.id = a.patient_id
                WHERE a.patient_id = ?""", patientId));
        resources.addAll(query(FhirRepository::medication, """
                SELECT m.*, p.name AS patient_name FROM medication_statement m JOIN patient p ON p.id = m.patient_id
                WHERE m.patient_id = ?""", patientId));
        resources.addAll(query(FhirRepository::encounter, ENCOUNTERS + " WHERE e.patient_id = ? ORDER BY e.period_start DESC",
                patientId));
        return resources;
    }

    public List<Map<String, Object>> observations(int patientId) {
        return query(FhirRepository::observation, """
                SELECT o.*, p.name AS patient_name FROM observation o JOIN patient p ON p.id = o.patient_id
                WHERE o.patient_id = ? ORDER BY o.effective_date DESC, o.display""", patientId);
    }

    public List<Map<String, Object>> encountersByServiceType(String serviceType) {
        return query(FhirRepository::encounter, ENCOUNTERS + " WHERE e.service_type = ? ORDER BY e.period_start DESC",
                serviceType);
    }

    public static Map<String, Object> bundle(List<Map<String, Object>> resources) {
        return obj("resourceType", "Bundle", "type", "searchset", "total", resources.size(),
                "entry", resources.stream().map(r -> obj("resource", r)).toList());
    }

    private static final String ENCOUNTERS = """
            SELECT e.*, p.name AS patient_name, pr.name AS practitioner_name, pr.qualification
            FROM encounter e JOIN patient p ON p.id = e.patient_id JOIN practitioner pr ON pr.id = e.practitioner_id""";

    private static Map<String, Object> patient(Map<String, Object> row) {
        return obj("resourceType", "Patient", "id", str(row.get("id")),
                "identifier", List.of(obj("system", MRN, "value", row.get("mrn"))),
                "name", List.of(obj("use", "official", "text", row.get("name"))),
                "gender", row.get("gender"),
                "birthDate", str(row.get("birth_date")));
    }

    private static Map<String, Object> condition(Map<String, Object> row) {
        return obj("resourceType", "Condition", "id", str(row.get("id")),
                "clinicalStatus", concept(TERMINOLOGY + "condition-clinical", row.get("clinical_status"), null),
                "code", concept(ICD10, row.get("icd10_code"), row.get("display")),
                "subject", subject(row),
                "encounter", row.get("encounter_id") == null ? null : obj("reference", "Encounter/" + row.get("encounter_id")),
                "recordedDate", str(row.get("recorded_date")));
    }

    private static Map<String, Object> allergy(Map<String, Object> row) {
        return obj("resourceType", "AllergyIntolerance", "id", str(row.get("id")),
                "clinicalStatus", concept(TERMINOLOGY + "allergyintolerance-clinical", "active", null),
                "category", List.of(row.get("category")),
                "code", concept(SNOMED, row.get("snomed_code"), row.get("substance")),
                "patient", subject(row));
    }

    private static Map<String, Object> medication(Map<String, Object> row) {
        return obj("resourceType", "MedicationStatement", "id", str(row.get("id")),
                "status", row.get("status"),
                "medicationCodeableConcept", obj("text", row.get("medication")),
                "subject", subject(row),
                "dosage", List.of(obj("text", row.get("dosage"))));
    }

    private static Map<String, Object> encounter(Map<String, Object> row) {
        return obj("resourceType", "Encounter", "id", str(row.get("id")),
                "status", row.get("status"),
                "class", obj("system", "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code", "AMB", "display", "ambulatory"),
                "serviceType", obj("text", "Poli " + row.get("service_type")),
                "subject", subject(row),
                "participant", List.of(obj("individual", obj("reference", "Practitioner/" + row.get("practitioner_id"),
                        "display", row.get("practitioner_name") + " (" + row.get("qualification") + ")"))),
                "period", obj("start", str(row.get("period_start"))));
    }

    private static Map<String, Object> observation(Map<String, Object> row) {
        Object unit = row.get("unit");
        Object interpretation = row.get("interpretation");
        Map<String, Object> range = obj("low", quantity(row.get("ref_low"), unit), "high", quantity(row.get("ref_high"), unit),
                "text", row.get("ref_text"));
        return obj("resourceType", "Observation", "id", str(row.get("id")),
                "status", row.get("status"),
                "category", List.of(concept(TERMINOLOGY + "observation-category", row.get("category"), null)),
                "code", concept(LOINC, row.get("loinc_code"), row.get("display")),
                "subject", subject(row),
                "effectiveDateTime", str(row.get("effective_date")),
                "valueQuantity", quantity(row.get("value_quantity"), unit),
                "valueString", row.get("value_string"),
                "interpretation", interpretation == null ? null : List.of(concept(TERMINOLOGY + "v3-ObservationInterpretation",
                        interpretation, INTERPRETATIONS.get(str(interpretation)))),
                "referenceRange", range.isEmpty() ? null : List.of(range));
    }

    private static Map<String, Object> subject(Map<String, Object> row) {
        return obj("reference", "Patient/" + row.get("patient_id"), "display", row.get("patient_name"));
    }

    private static Map<String, Object> concept(String system, Object code, Object display) {
        return obj("coding", code == null ? null : List.of(obj("system", system, "code", code, "display", display)),
                "text", display);
    }

    private static Map<String, Object> quantity(Object value, Object unit) {
        return value == null ? null
                : obj("value", ((BigDecimal) value).doubleValue(), "unit", unit, "system", UCUM, "code", unit);
    }

    /** JSON object that keeps insertion order and leaves out null values. */
    private static Map<String, Object> obj(Object... keyValues) {
        Map<String, Object> map = new LinkedHashMap<>();
        for (int i = 0; i < keyValues.length; i += 2) {
            if (keyValues[i + 1] != null) {
                map.put((String) keyValues[i], keyValues[i + 1]);
            }
        }
        return map;
    }

    private static String str(Object value) {
        return value == null ? null : value.toString();
    }

    private List<Map<String, Object>> query(Function<Map<String, Object>, Map<String, Object>> mapper, String sql,
            Object... params) {
        try (Connection connection = dataSource.getConnection();
                PreparedStatement statement = connection.prepareStatement(sql)) {
            for (int i = 0; i < params.length; i++) {
                statement.setObject(i + 1, params[i]);
            }
            try (ResultSet rs = statement.executeQuery()) {
                List<Map<String, Object>> resources = new ArrayList<>();
                int columns = rs.getMetaData().getColumnCount();
                while (rs.next()) {
                    Map<String, Object> row = new LinkedHashMap<>();
                    for (int c = 1; c <= columns; c++) {
                        row.put(rs.getMetaData().getColumnLabel(c), rs.getObject(c));
                    }
                    resources.add(mapper.apply(row));
                }
                return resources;
            }
        } catch (SQLException e) {
            throw new IllegalStateException("Database query failed: " + e.getMessage(), e);
        }
    }
}
