package com.erfinfeluzy;

import dev.langchain4j.data.segment.TextSegment;
import dev.langchain4j.model.embedding.EmbeddingModel;
import dev.langchain4j.model.input.PromptTemplate;
import dev.langchain4j.rag.DefaultRetrievalAugmentor;
import dev.langchain4j.rag.RetrievalAugmentor;
import dev.langchain4j.rag.content.injector.DefaultContentInjector;
import dev.langchain4j.rag.content.retriever.EmbeddingStoreContentRetriever;
import dev.langchain4j.store.embedding.EmbeddingStore;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.inject.Produces;
import org.eclipse.microprofile.config.inject.ConfigProperty;

/**
 * Easy RAG reads the files in rag-docs into the embedding store; this replaces its default
 * prompt template, which tells the model to answer only from the retrieved excerpts and made
 * it refuse general questions.
 */
public class RagConfiguration {

    private static final PromptTemplate PROMPT = PromptTemplate.from("""
            Excerpts from the clinic knowledge base that may or may not be relevant:
            ---
            {{contents}}
            ---
            If the excerpts contain the answer to the question below, answer directly from them in plain text.
            If they are unrelated, ignore them completely and answer from general knowledge without mentioning them.

            Question: {{userMessage}}""");

    @Produces
    @ApplicationScoped
    RetrievalAugmentor retrievalAugmentor(EmbeddingStore<TextSegment> store, EmbeddingModel embeddingModel,
            @ConfigProperty(name = "quarkus.langchain4j.easy-rag.max-results") int maxResults) {
        return DefaultRetrievalAugmentor.builder()
                .contentRetriever(EmbeddingStoreContentRetriever.builder()
                        .embeddingStore(store)
                        .embeddingModel(embeddingModel)
                        .maxResults(maxResults)
                        .build())
                .contentInjector(DefaultContentInjector.builder()
                        .promptTemplate(PROMPT)
                        .build())
                .build();
    }
}
