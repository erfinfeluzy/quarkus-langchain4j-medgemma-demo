package com.erfinfeluzy;

/**
 * One streamed piece of the model's answer. Sent as JSON so leading spaces in
 * tokens survive SSE parsing (SSE clients strip the first space after "data:").
 */
public record ChatChunk(String token) {
}
