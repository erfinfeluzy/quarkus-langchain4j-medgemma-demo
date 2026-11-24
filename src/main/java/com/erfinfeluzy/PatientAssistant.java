package com.erfinfeluzy;

import dev.langchain4j.service.SystemMessage;
import dev.langchain4j.service.UserMessage;
import dev.langchain4j.service.V;
import io.quarkiverse.langchain4j.RegisterAiService;
import io.quarkiverse.langchain4j.runtime.aiservice.ChatEvent;
import io.smallrye.mutiny.Multi;
import jakarta.enterprise.context.ApplicationScoped;

/**
 * Medical agent for patient questions: MedGemma explains the records fetched by {@link PatientDataAgent}.
 * The records sit in the user message right next to the question, and there is no RAG and no memory,
 * so the 4B model cannot mix them up with knowledge base excerpts or earlier answers.
 */
@RegisterAiService(retrievalAugmentor = RegisterAiService.NoRetrievalAugmentorSupplier.class,
        chatMemoryProviderSupplier = RegisterAiService.NoChatMemoryProviderSupplier.class)
@ApplicationScoped
public interface PatientAssistant {

    @SystemMessage("""
            You are a helpful medical assistant for Puskesmas Sehat Sentosa. Answer concisely in the user's language.
            Answer only from the patient records given with the question (FHIR R4 JSON) and never guess patient data.
            If the records are empty or do not contain what was asked (for example no allergies listed), say that
            this information is not in the patient records. Never add medications, allergies, diagnoses or lab
            values that are not in the records. Explain them in plain language and never show the raw JSON.
            For the visits of a polyclinic, the patients are the Encounter subjects; the participant is the doctor.
            For a lab result, state its value, unit and reference range, and take low/normal/high only from its
            interpretation code (H = high, N = normal, L = low); never decide it by comparing the numbers yourself.
            Never diagnose or prescribe; for anything beyond the records, advise the user to consult a doctor.
            """)
    @UserMessage("""
            Patient records:
            {{patientData}}

            Question: {{message}}""")
    Multi<ChatEvent> answer(@V("message") String message, @V("patientData") String patientData);
}
