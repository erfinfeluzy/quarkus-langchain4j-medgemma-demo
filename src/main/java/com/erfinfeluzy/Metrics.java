package com.erfinfeluzy;

import com.fasterxml.jackson.annotation.JsonInclude;

/**
 * Timing of one chat request per stage, measured on the server (see bench/README.md). All times in milliseconds
 * from {@link System#nanoTime()}; a stage that does not run in this scenario is null.
 *
 * @param scenario        baseline, rag, tools or image
 * @param routingMs       qwen2.5 choosing the patient tools, including the tool calls to MySQL
 * @param toolCalls       tool calls that returned patient data
 * @param retrievalMs     question embedding and Redis vector search (RAG only)
 * @param medgemmaTtftMs  MedGemma call (after retrieval) until its first token
 * @param serverTtftMs    request received until the first token: what the user waits for
 * @param generateMs      first token until the answer is complete
 * @param totalMs         request received until the answer is complete
 * @param inputTokens     MedGemma prompt tokens as counted by Ollama (image tokens included)
 * @param outputTokens    MedGemma answer tokens as counted by Ollama
 * @param tokensPerSecond decode speed: (outputTokens - 1) / generate time
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record Metrics(String scenario, Long routingMs, Integer toolCalls, Long retrievalMs, long medgemmaTtftMs,
        long serverTtftMs, long generateMs, long totalMs, Integer inputTokens, Integer outputTokens,
        Double tokensPerSecond) {
}
