package com.erfinfeluzy;

import dev.langchain4j.data.image.Image;
import dev.langchain4j.model.output.TokenUsage;
import dev.langchain4j.service.Result;
import dev.langchain4j.store.memory.chat.ChatMemoryStore;
import dev.langchain4j.service.tool.ToolExecution;
import io.quarkiverse.langchain4j.runtime.aiservice.ChatEvent;
import io.quarkiverse.langchain4j.runtime.aiservice.ChatEvent.ChatCompletedEvent;
import io.quarkiverse.langchain4j.runtime.aiservice.ChatEvent.ContentFetchedEvent;
import io.quarkiverse.langchain4j.runtime.aiservice.ChatEvent.PartialResponseEvent;
import io.smallrye.common.annotation.Blocking;
import io.smallrye.mutiny.Multi;
import jakarta.inject.Inject;
import jakarta.ws.rs.BadRequestException;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.HeaderParam;
import jakarta.ws.rs.NotFoundException;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import java.io.IOException;
import java.nio.file.Files;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.quarkus.logging.Log;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;
import org.eclipse.microprofile.config.inject.ConfigProperty;
import org.jboss.resteasy.reactive.RestForm;
import org.jboss.resteasy.reactive.RestStreamElementType;
import org.jboss.resteasy.reactive.multipart.FileUpload;

@Path("/chat")
public class ChatResource {

    // Demo pribadi dengan satu pengguna, jadi semua chat memakai satu riwayat yang sama di Redis.
    // Memory id langsung jadi key Redis, jadi diberi prefix med-chat: supaya tidak bentrok dengan demo HR
    private static final String MEMORY_ID = "med-chat:personal";

    private static final Set<String> PATIENT_TOOLS = Set.of("findPatient", "labResults");

    private static final Set<String> IMAGE_TYPES = Set.of("image/jpeg", "image/png", "image/webp");

    private static final String NO_PATIENT = "(no patient discussed yet)";

    // Pasien terakhir yang benar-benar ditemukan, untuk pertanyaan lanjutan seperti "apa alerginya?".
    // Disimpan di memori aplikasi saja: demo satu pengguna, hilang saat restart
    private volatile String currentPatient = NO_PATIENT;

    // Benchmark (bench/README.md): header X-Benchmark: true mengirim Metrics sebagai event SSE terakhir dan
    // mengisolasi request (riwayat chat sendiri, pasien terakhir tidak dipakai/diubah). Mati di produksi
    @ConfigProperty(name = "med.benchmark.enabled", defaultValue = "false")
    boolean benchmarkEnabled;

    @Inject
    PatientDataAgent patientDataAgent;

    @Inject
    Assistant assistant;

    @Inject
    PatientAssistant patientAssistant;

    @Inject
    ImageAssistant imageAssistant;

    @Inject
    BaselineAssistant baselineAssistant;

    @Inject
    PatientTools patientTools;

    @Inject
    FhirRepository fhir;

    @Inject
    ObjectMapper objectMapper;

    // Store Redis yang dipakai chat memory; untuk menghapus riwayat sementara milik request benchmark
    @Inject
    ChatMemoryStore chatMemoryStore;

    // Blocking: agent data pasien (qwen2.5 + MySQL) jalan dulu sebelum MedGemma mulai streaming
    @Blocking
    @POST
    @Consumes(MediaType.TEXT_PLAIN)
    @Produces(MediaType.SERVER_SENT_EVENTS)
    @RestStreamElementType(MediaType.APPLICATION_JSON)
    public Multi<ChatChunk> chat(String message, @HeaderParam("X-Benchmark") boolean benchmarkHeader) {
        long start = System.nanoTime();
        boolean bench = benchmarkEnabled && benchmarkHeader;
        Result<String> fetched = patientDataAgent.fetch(message, bench ? NO_PATIENT : currentPatient);
        List<ToolExecution> found = fetched.toolExecutions().stream()
                .filter(execution -> hasData(execution.result()))
                .toList();
        List<String> patientData = new ArrayList<>(found.stream().map(ChatResource::describe).toList());
        if (!bench) {
            for (ToolExecution execution : found) {
                if (PATIENT_TOOLS.contains(execution.request().name())) {
                    currentPatient = execution.request().arguments().replaceAll(".*\"name\"\\s*:\\s*\"([^\"]*)\".*", "$1");
                }
            }
        }
        if (patientData.isEmpty()) {
            recoverMissingName(fetched.toolExecutions(), message, bench).ifPresent(patientData::add);
        }
        long routingMs = millis(start, System.nanoTime());
        // Tanpa data pasien (tidak ada tool call, atau tool salah panggil dan hasilnya kosong) -> agent klinik dengan RAG
        if (patientData.isEmpty()) {
            if (!bench) {
                return stream(assistant.chat(MEMORY_ID, message), null);
            }
            // Riwayat kosong per request, supaya prompt tidak makin panjang selama benchmark; dihapus setelah selesai
            String memoryId = "med-chat:bench:" + UUID.randomUUID();
            Timing timing = new Timing("rag", start, routingMs, 0);
            return stream(assistant.chat(memoryId, message), timing)
                    .onTermination().invoke(() -> chatMemoryStore.deleteMessages(memoryId));
        }
        Timing timing = bench ? new Timing("tools", start, routingMs, patientData.size()) : null;
        return stream(patientAssistant.answer(message, String.join("\n\n", patientData)), timing);
    }

    /**
     * Deterministic fallback: the router called a tool without its argument (rejected by PatientTools). Instead of
     * a second router turn, take the patient named in the message (or, outside the benchmark, the current patient)
     * and run labResults if that was the tool, otherwise findPatient (also when the router wrongly chose the
     * polyclinic tool). No patient named -> empty, and the question goes to RAG.
     */
    private Optional<String> recoverMissingName(List<ToolExecution> executions, String message, boolean bench) {
        Optional<ToolExecution> rejected = executions.stream()
                .filter(e -> e.result().contains("OperationOutcome"))
                .findFirst();
        if (rejected.isEmpty()) {
            return Optional.empty();
        }
        String name = fhir.patientNamedIn(message);
        if (name == null && !bench && !NO_PATIENT.equals(currentPatient)) {
            name = currentPatient;
        }
        if (name == null) {
            return Optional.empty();
        }
        String tool = "labResults".equals(rejected.get().request().name()) ? "labResults" : "findPatient";
        Map<String, Object> bundle = "labResults".equals(tool) ? patientTools.labResults(name) : patientTools.findPatient(name);
        String result;
        try {
            result = objectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(bundle);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException(e);
        }
        if (!hasData(result)) {
            return Optional.empty();
        }
        Log.infof("Missing name filled in from the message: %s(name=%s)", tool, name);
        if (!bench) {
            currentPatient = name;
        }
        return Optional.of(tool + " {\"name\":\"" + name + "\"}:\n" + result);
    }

    // Gambar medis (MRI, rontgen, foto hasil lab) dibaca langsung oleh MedGemma; DICOM harus diekspor ke JPG/PNG dulu
    @POST
    @Path("/image")
    @Consumes(MediaType.MULTIPART_FORM_DATA)
    @Produces(MediaType.SERVER_SENT_EVENTS)
    @RestStreamElementType(MediaType.APPLICATION_JSON)
    public Multi<ChatChunk> image(@RestForm String message, @RestForm("file") FileUpload file,
            @HeaderParam("X-Benchmark") boolean benchmarkHeader) throws IOException {
        long start = System.nanoTime();
        if (file == null || !IMAGE_TYPES.contains(file.contentType())) {
            throw new BadRequestException("Upload gambar JPG, PNG atau WebP");
        }
        String question = message == null || message.isBlank() ? "Jelaskan gambar medis ini." : message;
        Image image = Image.builder()
                .base64Data(Base64.getEncoder().encodeToString(Files.readAllBytes(file.uploadedFile())))
                .mimeType(file.contentType())
                .build();
        Timing timing = benchmarkEnabled && benchmarkHeader ? new Timing("image", start, null, null) : null;
        return stream(imageAssistant.describe(question, image), timing);
    }

    // Skenario benchmark 1 (tanpa grounding): MedGemma saja. Tidak dipakai UI, hanya ada saat benchmark aktif
    @POST
    @Path("/baseline")
    @Consumes(MediaType.TEXT_PLAIN)
    @Produces(MediaType.SERVER_SENT_EVENTS)
    @RestStreamElementType(MediaType.APPLICATION_JSON)
    public Multi<ChatChunk> baseline(String message, @HeaderParam("X-Benchmark") boolean benchmarkHeader) {
        long start = System.nanoTime();
        if (!benchmarkEnabled) {
            throw new NotFoundException();
        }
        Timing timing = benchmarkHeader ? new Timing("baseline", start, null, null) : null;
        return stream(baselineAssistant.chat(message), timing);
    }

    /** Token MedGemma ke klien; dengan timing, catat tiap tahap dan kirim Metrics sebagai event terakhir. */
    private static Multi<ChatChunk> stream(Multi<ChatEvent> events, Timing timing) {
        if (timing == null) {
            return events.filter(PartialResponseEvent.class::isInstance)
                    .map(event -> new ChatChunk(((PartialResponseEvent) event).getChunk()));
        }
        Multi<ChatChunk> tokens = events
                .invoke(timing::record)
                .filter(PartialResponseEvent.class::isInstance)
                .map(event -> new ChatChunk(((PartialResponseEvent) event).getChunk()));
        return Multi.createBy().concatenating()
                .streams(tokens, Multi.createFrom().item(() -> new ChatChunk(null, timing.metrics())));
    }

    // Hasil tool di-pretty-print oleh LangChain4j ("total" : 0), jadi cek dengan regex, bukan teks persis.
    // OperationOutcome (argumen kosong ditolak, lihat PatientTools) tidak punya "total" dan juga dianggap kosong
    private static final Pattern NON_EMPTY_BUNDLE = Pattern.compile("\"total\"\\s*:\\s*[1-9]");

    static boolean hasData(String toolResult) {
        return toolResult != null && NON_EMPTY_BUNDLE.matcher(toolResult).find();
    }

    private static String describe(ToolExecution execution) {
        return execution.request().name() + " " + execution.request().arguments() + ":\n" + execution.result();
    }

    private static long millis(long from, long to) {
        return (to - from) / 1_000_000;
    }

    /**
     * Waktu (System.nanoTime) satu request benchmark; 0 = belum terjadi. Dibuat tepat sebelum AI service MedGemma
     * dipanggil: retrieval RAG (embedding + Redis) sudah berjalan di dalam panggilan itu, sebelum stream mulai.
     */
    private static final class Timing {
        final String scenario;
        final long start;
        final long callStart = System.nanoTime();
        final Long routingMs;
        final Integer toolCalls;
        volatile long retrievalEnd;
        volatile long firstToken;
        volatile long end;
        volatile int chunks;
        volatile TokenUsage usage;

        Timing(String scenario, long start, Long routingMs, Integer toolCalls) {
            this.scenario = scenario;
            this.start = start;
            this.routingMs = routingMs;
            this.toolCalls = toolCalls;
        }

        void record(ChatEvent event) {
            long now = System.nanoTime();
            if (event instanceof ContentFetchedEvent) {
                retrievalEnd = now;
            } else if (event instanceof PartialResponseEvent) {
                if (firstToken == 0) {
                    firstToken = now;
                }
                chunks++;
            } else if (event instanceof ChatCompletedEvent completed) {
                end = now;
                usage = completed.getChatResponse().tokenUsage();
            }
        }

        Metrics metrics() {
            long finished = end != 0 ? end : System.nanoTime();
            long first = firstToken != 0 ? firstToken : finished;
            long medgemmaStart = retrievalEnd != 0 ? retrievalEnd : callStart;
            Integer input = usage != null ? usage.inputTokenCount() : null;
            // Extension Ollama 1.13.3 tidak mengisi jumlah token saat streaming; Ollama mengirim satu token per chunk
            Integer output = usage != null && usage.outputTokenCount() != null ? usage.outputTokenCount() : chunks;
            Double tokensPerSecond = output > 1 && finished > first ? (output - 1) / ((finished - first) / 1e9) : null;
            return new Metrics(scenario, routingMs, toolCalls,
                    retrievalEnd != 0 ? millis(callStart, retrievalEnd) : null,
                    millis(medgemmaStart, first), millis(start, first), millis(first, finished), millis(start, finished),
                    input, output, tokensPerSecond);
        }
    }
}
