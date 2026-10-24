package com.erfinfeluzy;

import io.quarkiverse.langchain4j.easyrag.EasyRagManualIngestion;
import io.quarkiverse.langchain4j.redis.RedisEmbeddingStore;
import io.quarkus.logging.Log;
import io.quarkus.redis.datasource.RedisDataSource;
import io.quarkus.redis.datasource.keys.KeyScanArgs;
import io.quarkus.runtime.StartupEvent;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.event.Observes;
import jakarta.inject.Inject;
import org.eclipse.microprofile.config.inject.ConfigProperty;

/**
 * Fills the Redis embedding store from rag-docs. Redis keeps the embeddings across restarts,
 * so documents are ingested at startup only when the store is still empty; after changing the
 * documents, call {@link #reindex()} (exposed as POST /rag/reindex).
 */
@ApplicationScoped
public class RagIngestion {

    @Inject
    EasyRagManualIngestion ingestion;

    @Inject
    RedisEmbeddingStore store;

    @Inject
    RedisDataSource redis;

    @ConfigProperty(name = "quarkus.langchain4j.redis.prefix")
    String prefix;

    void onStart(@Observes StartupEvent event) {
        long segments = countSegments();
        if (segments == 0) {
            Log.info("Redis embedding store is empty, ingesting rag-docs");
            reindex();
        } else {
            Log.infof("Redis embedding store already has %d segments, skipping ingestion", segments);
        }
    }

    /** Deletes all stored segments and ingests rag-docs again. Returns the new segment count. */
    public synchronized long reindex() {
        store.deleteAll();
        ingestion.ingest();
        long segments = countSegments();
        Log.infof("Ingested rag-docs into Redis: %d segments", segments);
        return segments;
    }

    public long countSegments() {
        long count = 0;
        var cursor = redis.key().scan(new KeyScanArgs().match(prefix + "*").count(1000));
        while (cursor.hasNext()) {
            count += cursor.next().size();
        }
        return count;
    }
}
