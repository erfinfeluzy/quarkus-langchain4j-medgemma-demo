package com.erfinfeluzy;

import dev.langchain4j.memory.chat.ChatMemoryProvider;
import dev.langchain4j.memory.chat.MessageWindowChatMemory;
import dev.langchain4j.service.Result;
import dev.langchain4j.service.SystemMessage;
import dev.langchain4j.service.UserMessage;
import dev.langchain4j.service.V;
import io.quarkiverse.langchain4j.RegisterAiService;
import java.util.function.Supplier;

/**
 * First agent: looks up patient data with the patient tools (qwen2.5 3B, model "tools"). Its own text is
 * discarded; {@link ChatResource} passes the raw tool results to {@link PatientAssistant} (MedGemma), which
 * cannot call tools itself. No RAG here, the knowledge base is only for the answering agent.
 */
// Tanpa riwayat antar pertanyaan: pasien terakhir sudah diberikan lewat currentPatient, dan riwayat berisi hasil
// tool membuat model kecil menjawab dari riwayat alih-alih memanggil tool lagi. Tool tetap butuh chat memory untuk
// satu putaran tool call, jadi dipakai memory di RAM; bean RequestScoped (default) menghapusnya di akhir request
@RegisterAiService(modelName = "tools", tools = PatientTools.class,
        retrievalAugmentor = RegisterAiService.NoRetrievalAugmentorSupplier.class,
        chatMemoryProviderSupplier = PatientDataAgent.RequestMemory.class)
public interface PatientDataAgent {

    @SystemMessage("""
            You pick the patient tool for a clinic's medical assistant; you never answer the user yourself.
            Rules:
            1. A patient's diagnoses, allergies (alergi), medications (obat) or visits: call findPatient.
            2. A patient's lab results (hasil lab): call labResults.
            3. Which patients visited a polyclinic ("siapa saja pasien poli ..."): call listPatientsByPolyclinic.
            4. Anything else, including polyclinic schedules and opening hours (jadwal, jam buka), prices and
               general health questions: call no tool.
            The name argument is the patient named in the message. If the message names no patient ("dia",
            "pasien itu", or the suffix "-nya" as in "alerginya", "obatnya", "hasil labnya"), use the current
            patient given with the message; never pass those words as the name.
            After the tool call, or when no tool is needed, reply with only: DONE
            """)
    // Pasien terakhir diberikan eksplisit: model kecil tidak andal mengambil nama dari tool call sebelumnya
    @UserMessage("""
            Current patient: {{currentPatient}}
            Message: {{message}}""")
    Result<String> fetch(@V("message") String message, @V("currentPatient") String currentPatient);

    class RequestMemory implements Supplier<ChatMemoryProvider> {
        @Override
        public ChatMemoryProvider get() {
            return memoryId -> MessageWindowChatMemory.withMaxMessages(20);
        }
    }
}
