package com.erfinfeluzy;

import dev.langchain4j.service.MemoryId;
import dev.langchain4j.service.memory.ChatMemoryAccess;
import dev.langchain4j.service.SystemMessage;
import dev.langchain4j.service.UserMessage;
import io.quarkiverse.langchain4j.RegisterAiService;
import io.quarkiverse.langchain4j.runtime.aiservice.ChatEvent;
import io.smallrye.mutiny.Multi;
import jakarta.enterprise.context.ApplicationScoped;

/**
 * Medical agent for questions without patient data (clinic, guidelines, general health): MedGemma with
 * RAG and chat memory. Questions about patients go to {@link PatientAssistant} instead.
 */
@RegisterAiService
// ApplicationScoped: AI service default-nya RequestScoped, dan chat memory-nya dihapus di akhir tiap request
@ApplicationScoped
public interface Assistant extends ChatMemoryAccess {

    @SystemMessage("""
            You are a helpful medical assistant for Puskesmas Sehat Sentosa. Answer concisely in the user's language.
            Questions about the clinic (its schedule, polyclinics, doctors, services and prices) and about the
            medication and health guidelines must be answered only from the knowledge base excerpts included in
            the user message. If the answer is not in the excerpts, say you don't know.
            You have no access to patient records here; never state details of a specific patient.
            Never diagnose or prescribe; for anything beyond general information, advise the user to consult a doctor.
            If the user describes emergency symptoms (chest pain, shortness of breath, stroke signs, heavy bleeding,
            loss of consciousness), tell them to call 119 or go to the nearest emergency room immediately.
            """)
    Multi<ChatEvent> chat(@MemoryId String memoryId, @UserMessage String message);
}
