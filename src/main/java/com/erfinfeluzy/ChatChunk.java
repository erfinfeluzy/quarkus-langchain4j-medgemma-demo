package com.erfinfeluzy;

import com.fasterxml.jackson.annotation.JsonInclude;

/**
 * One streamed piece of the model's answer. Sent as JSON so leading spaces in
 * tokens survive SSE parsing (SSE clients strip the first space after "data:").
 * In benchmark mode the last event carries {@link Metrics} instead of a token.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record ChatChunk(String token, Metrics metrics) {

    public ChatChunk(String token) {
        this(token, null);
    }
}
