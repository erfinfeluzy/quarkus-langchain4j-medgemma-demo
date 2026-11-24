package com.erfinfeluzy;

import io.quarkiverse.langchain4j.RegisterAiService;
import io.quarkiverse.langchain4j.runtime.aiservice.ChatEvent;
import dev.langchain4j.service.SystemMessage;
import dev.langchain4j.service.UserMessage;
import io.smallrye.mutiny.Multi;
import jakarta.enterprise.context.ApplicationScoped;

/**
 * Benchmark baseline (grounding "None"): MedGemma alone, without qwen2.5 routing, RAG, tools or memory.
 * Only reachable through POST /chat/baseline when med.benchmark.enabled=true; the chat UI never uses it.
 */
@RegisterAiService(retrievalAugmentor = RegisterAiService.NoRetrievalAugmentorSupplier.class,
        chatMemoryProviderSupplier = RegisterAiService.NoChatMemoryProviderSupplier.class)
@ApplicationScoped
public interface BaselineAssistant {

    // Sama dengan Assistant, tanpa kalimat tentang potongan knowledge base yang di sini tidak ada
    @SystemMessage("""
            You are a helpful medical assistant for Puskesmas Sehat Sentosa. Answer concisely in the user's language.
            You have no access to patient records here; never state details of a specific patient.
            Never diagnose or prescribe; for anything beyond general information, advise the user to consult a doctor.
            If the user describes emergency symptoms (chest pain, shortness of breath, stroke signs, heavy bleeding,
            loss of consciousness), tell them to call 119 or go to the nearest emergency room immediately.
            """)
    Multi<ChatEvent> chat(@UserMessage String message);
}
