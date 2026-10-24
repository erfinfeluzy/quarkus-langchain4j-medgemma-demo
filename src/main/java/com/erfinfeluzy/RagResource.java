package com.erfinfeluzy;

import io.smallrye.common.annotation.Blocking;
import jakarta.inject.Inject;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import java.util.Map;

@Path("/rag")
@Produces(MediaType.APPLICATION_JSON)
public class RagResource {

    @Inject
    RagIngestion ragIngestion;

    @GET
    @Path("/status")
    @Blocking
    public Map<String, Long> status() {
        return Map.of("segments", ragIngestion.countSegments());
    }

    @POST
    @Path("/reindex")
    @Blocking
    public Map<String, Long> reindex() {
        return Map.of("segments", ragIngestion.reindex());
    }
}
