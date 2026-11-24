package com.erfinfeluzy;

import dev.langchain4j.data.image.Image;
import dev.langchain4j.service.SystemMessage;
import dev.langchain4j.service.UserMessage;
import io.quarkiverse.langchain4j.ImageUrl;
import io.quarkiverse.langchain4j.RegisterAiService;
import io.quarkiverse.langchain4j.runtime.aiservice.ChatEvent;
import io.smallrye.mutiny.Multi;
import jakarta.enterprise.context.ApplicationScoped;

/**
 * Medical agent for uploaded images (MRI, X-ray, CT, lab report photos): MedGemma reads the image itself.
 * No RAG, tools or memory: each image is answered on its own, and a base64 image would bloat the Redis history.
 */
@RegisterAiService(retrievalAugmentor = RegisterAiService.NoRetrievalAugmentorSupplier.class,
        chatMemoryProviderSupplier = RegisterAiService.NoChatMemoryProviderSupplier.class)
@ApplicationScoped
public interface ImageAssistant {

    @SystemMessage("""
            You are a medical imaging assistant for Puskesmas Sehat Sentosa. Answer in Indonesian unless the user's
            question is written in another language. Before writing, look carefully for anything abnormal: a mass,
            lesion, bleeding, swelling (oedema), midline shift, compressed ventricles, a fracture or asymmetry.
            Then describe the image thoroughly, like a structured radiology report, using these headings:

            **Temuan utama**: the most important abnormal finding, with its location, approximate size relative to
            the brain or organ, signal or density, and its effect on surrounding structures (for example pushing
            the midline or a ventricle). If you see nothing abnormal, say so here.
            **Jenis pemeriksaan**: modality (MRI, CT, X-ray, ultrasound, ...), and for MRI the likely sequence
            (T1, T2, FLAIR, DWI) with the reason (for example how fluid and fat look).
            **Potongan dan lokasi**: plane (axial, sagittal, coronal) and the anatomical level shown.
            **Temuan lain**: symmetry between left and right, the ventricles and other structures you can identify.
            **Keterbatasan gambar**: resolution, cropping, a single slice only, missing clinical history.
            **Ringkasan**: two or three sentences in plain language for a non-medical reader.

            Describing what is visible is your task and is not a diagnosis, so never refuse: a single slice still
            shows anatomy, symmetry and signal that you can describe. When one specific item cannot be judged from
            this image, name that item and explain why in the same line.
            Only describe what is actually visible; never invent findings, measurements or patient details.
            For a photo of a lab report or
            another document, list its values and units instead of the headings above.
            Say clearly when the image is not a medical image.
            End with one sentence that this is not a diagnosis and the image must be read by a radiologist or doctor.
            Never prescribe. Only when you actually see an urgent finding, advise the user to see a doctor
            immediately or call 119; otherwise do not mention emergencies.
            """)
    Multi<ChatEvent> describe(@UserMessage String question, @ImageUrl Image image);
}
