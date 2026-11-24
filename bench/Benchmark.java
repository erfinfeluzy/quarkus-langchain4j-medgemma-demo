import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Random;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * TTFT benchmark of the chat app for the paper (see bench/README.md). Run from the project folder:
 *
 *   java bench/Benchmark.java [--url http://localhost:8080] [--reps 5] [--warmup 1] [--seed 42]
 *                             [--questions bench/questions.csv] [--only rag,tools]
 *
 * Every request goes through the app (Redis, MySQL and Ollama stay as in normal use) with header X-Benchmark,
 * so the server adds its per-stage timing as the last SSE event. The client measures its own TTFT next to it.
 * Each repetition runs all questions in a new shuffled order, so the same prompt never runs twice in a row
 * (Ollama would otherwise reuse its KV cache and report an unrealistically low TTFT).
 */
public class Benchmark {

    record Question(String id, String scenario, String text, String image) {}

    record GpuSample(long nanos, double watts, double memMiB) {}

    static final HttpClient HTTP = HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).build();
    static final List<GpuSample> GPU = new CopyOnWriteArrayList<>();

    public static void main(String[] args) throws Exception {
        Map<String, String> opt = options(args);
        String url = opt.getOrDefault("url", "http://localhost:8080");
        int reps = Integer.parseInt(opt.getOrDefault("reps", "5"));
        int warmup = Integer.parseInt(opt.getOrDefault("warmup", "1"));
        long seed = Long.parseLong(opt.getOrDefault("seed", "42"));
        List<Question> questions = readQuestions(Path.of(opt.getOrDefault("questions", "bench/questions.csv")));
        if (opt.containsKey("only")) {
            List<String> only = List.of(opt.get("only").split(","));
            questions.removeIf(q -> !only.contains(q.scenario()));
        }

        // Aplikasi harus sudah jalan; tanpa cek ini semua request gagal dan tetap tercatat sebagai hasil
        try {
            HTTP.send(HttpRequest.newBuilder(URI.create(url + "/")).GET().build(), HttpResponse.BodyHandlers.discarding());
        } catch (IOException e) {
            System.err.println("Aplikasi tidak bisa dihubungi di " + url + " (" + e + "); jalankan dulu aplikasinya.");
            System.exit(1);
        }

        String stamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss"));
        Path dir = Path.of("bench", "results", stamp);
        Files.createDirectories(dir);
        writeEnvironment(dir.resolve("environment.txt"), url, reps, warmup, seed, questions.size());
        Process gpu = startGpuSampling();

        Random random = new Random(seed);
        List<String> rows = new ArrayList<>();
        rows.add("rep,order,question_id,prev_question_id,expected_scenario,actual_scenario,route_ok,client_ttft_ms,"
                + "client_total_ms,server_ttft_ms,routing_ms,retrieval_ms,medgemma_ttft_ms,generate_ms,output_tokens,"
                + "tokens_per_s,tool_calls,gpu_avg_w,gpu_energy_j,gpu_peak_mem_mib,answer_chars,error");
        List<String> answers = new ArrayList<>();
        answers.add("rep\tquestion_id\tanswer");
        int connectFailures = 0;
        try {
            for (int rep = 1 - warmup; rep <= reps; rep++) {
                List<Question> order = new ArrayList<>(questions);
                Collections.shuffle(order, random);
                String label = rep <= 0 ? "warmup " + (rep + warmup) : "rep " + rep;
                String prev = "";
                for (int i = 0; i < order.size(); i++) {
                    Question q = order.get(i);
                    System.out.printf("%s  %3d/%d  %-4s %-8s ", label, i + 1, order.size(), q.id(), q.scenario());
                    Map<String, String> r = run(url, q);
                    System.out.printf("client TTFT %6s ms  server TTFT %6s ms  %s%n",
                            r.get("client_ttft_ms"), r.getOrDefault("serverTtftMs", "-"), r.getOrDefault("error", ""));
                    connectFailures = r.getOrDefault("error", "").startsWith("ConnectException") ? connectFailures + 1 : 0;
                    if (connectFailures >= 5) {
                        throw new IllegalStateException("5 request berturut-turut gagal tersambung: aplikasi mati?");
                    }
                    if (rep > 0) {
                        rows.add(csvRow(rep, i + 1, q, prev, r));
                        answers.add(rep + "\t" + q.id() + "\t" + r.get("answer").replace("\t", " ").replace("\n", "\\n"));
                    }
                    prev = q.id();
                }
            }
        } finally {
            if (gpu != null) {
                gpu.destroy();
            }
            Files.write(dir.resolve("results.csv"), rows, StandardCharsets.UTF_8);
            Files.write(dir.resolve("answers.tsv"), answers, StandardCharsets.UTF_8);
            // Sesudah benchmark: model yang benar-benar dimuat (ollama ps sebelum pemanasan bisa masih model lama)
            writeEnvironment(dir.resolve("environment-end.txt"), url, reps, warmup, seed, questions.size());
        }
        List<String> summary = summarize(rows);
        Files.write(dir.resolve("summary.csv"), summary, StandardCharsets.UTF_8);
        System.out.println();
        summary.forEach(System.out::println);
        System.out.println("\nHasil: " + dir.toAbsolutePath());
    }

    /** One request; returns client timings, the server Metrics fields and the answer text. */
    static Map<String, String> run(String url, Question q) throws IOException, InterruptedException {
        HttpRequest.Builder request = HttpRequest.newBuilder()
                .header("Accept", "text/event-stream")
                .header("X-Benchmark", "true");
        if (q.scenario().equals("image")) {
            String boundary = "bench" + UUID.randomUUID().toString().replace("-", "");
            Path image = Path.of(q.image());
            ByteArrayOutputStream body = new ByteArrayOutputStream();
            body.writeBytes(("--" + boundary + "\r\nContent-Disposition: form-data; name=\"message\"\r\n\r\n"
                    + q.text() + "\r\n").getBytes(StandardCharsets.UTF_8));
            body.writeBytes(("--" + boundary + "\r\nContent-Disposition: form-data; name=\"file\"; filename=\""
                    + image.getFileName() + "\"\r\nContent-Type: " + mimeType(image) + "\r\n\r\n")
                    .getBytes(StandardCharsets.UTF_8));
            body.writeBytes(Files.readAllBytes(image));
            body.writeBytes(("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
            request.uri(URI.create(url + "/chat/image"))
                    .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                    .POST(HttpRequest.BodyPublishers.ofByteArray(body.toByteArray()));
        } else {
            String path = q.scenario().equals("baseline") ? "/chat/baseline" : "/chat";
            request.uri(URI.create(url + path))
                    .header("Content-Type", "text/plain; charset=utf-8")
                    .POST(HttpRequest.BodyPublishers.ofString(q.text(), StandardCharsets.UTF_8));
        }

        Map<String, String> result = new LinkedHashMap<>();
        StringBuilder answer = new StringBuilder();
        long start = System.nanoTime();
        long firstToken = 0;
        try {
            HttpResponse<java.io.InputStream> response = HTTP.send(request.build(),
                    HttpResponse.BodyHandlers.ofInputStream());
            if (response.statusCode() != 200) {
                result.put("error", "HTTP " + response.statusCode());
            }
            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(response.body(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    if (!line.startsWith("data:")) {
                        continue;
                    }
                    String json = line.substring(5);
                    Matcher token = Pattern.compile("\"token\":\"((?:[^\"\\\\]|\\\\.)*)\"").matcher(json);
                    if (token.find()) {
                        String text = unescape(token.group(1));
                        if (firstToken == 0 && !text.isBlank()) {
                            firstToken = System.nanoTime();
                        }
                        answer.append(text);
                    }
                    Matcher metrics = Pattern.compile("\"metrics\":\\{(.*)}").matcher(json);
                    if (metrics.find()) {
                        Matcher field = Pattern.compile("\"(\\w+)\":\"?([^\",}]*)\"?").matcher(metrics.group(1));
                        while (field.find()) {
                            result.put(field.group(1), field.group(2));
                        }
                    }
                }
            }
        } catch (IOException e) {
            result.put("error", e.getClass().getSimpleName() + ": " + e.getMessage());
        }
        long end = System.nanoTime();
        result.put("client_ttft_ms", firstToken == 0 ? "" : String.valueOf((firstToken - start) / 1_000_000));
        result.put("client_total_ms", String.valueOf((end - start) / 1_000_000));
        result.put("answer", answer.toString());
        gpuWindow(start, end, result);
        return result;
    }

    static String csvRow(int rep, int order, Question q, String prev, Map<String, String> r) {
        String actual = r.getOrDefault("scenario", "");
        return String.join(",", String.valueOf(rep), String.valueOf(order), q.id(), prev, q.scenario(), actual,
                String.valueOf(actual.equals(q.scenario())), r.get("client_ttft_ms"), r.get("client_total_ms"),
                r.getOrDefault("serverTtftMs", ""), r.getOrDefault("routingMs", ""), r.getOrDefault("retrievalMs", ""),
                r.getOrDefault("medgemmaTtftMs", ""), r.getOrDefault("generateMs", ""),
                r.getOrDefault("outputTokens", ""), round(r.get("tokensPerSecond")), r.getOrDefault("toolCalls", ""),
                r.getOrDefault("gpu_avg_w", ""), r.getOrDefault("gpu_energy_j", ""),
                r.getOrDefault("gpu_peak_mem_mib", ""), String.valueOf(r.get("answer").length()),
                "\"" + r.getOrDefault("error", "").replace("\"", "'") + "\"");
    }

    /**
     * Median, p95 and mean per scenario for the main columns, only for requests that took the expected route.
     * Subset "first" is rep 1, where Ollama has not seen the full prompt yet; "repeat" is rep 2 and later, where
     * llama.cpp's prompt cache in RAM may restore the whole prompt and lower TTFT. Report "first" as the TTFT a
     * user meets with a new question, and the gap to "repeat" as the cache effect.
     */
    static List<String> summarize(List<String> rows) {
        String[] header = rows.get(0).split(",");
        String[] columns = {"client_ttft_ms", "server_ttft_ms", "routing_ms", "retrieval_ms", "medgemma_ttft_ms",
                "generate_ms", "client_total_ms", "output_tokens", "tokens_per_s", "gpu_avg_w", "gpu_energy_j",
                "gpu_peak_mem_mib"};
        List<String> out = new ArrayList<>();
        out.add("scenario,subset,metric,n,median,p95,mean,min,max");
        Map<String, Integer> index = new LinkedHashMap<>();
        for (int i = 0; i < header.length; i++) {
            index.put(header[i], i);
        }
        List<String> routes = new ArrayList<>();
        for (String scenario : List.of("baseline", "rag", "tools", "image")) {
            for (String subset : List.of("all", "first", "repeat")) {
                List<String[]> ok = new ArrayList<>();
                int total = 0;
                for (String row : rows.subList(1, rows.size())) {
                    String[] cells = row.split(",", -1);
                    boolean first = cells[index.get("rep")].equals("1");
                    if (!cells[index.get("expected_scenario")].equals(scenario)
                            || (subset.equals("first") && !first) || (subset.equals("repeat") && first)) {
                        continue;
                    }
                    total++;
                    if (cells[index.get("route_ok")].equals("true")) {
                        ok.add(cells);
                    }
                }
                if (total == 0) {
                    continue;
                }
                if (subset.equals("all")) {
                    routes.add(String.format(Locale.ROOT, "%s,all,route_ok,%d,%d of %d,,,,", scenario, total,
                            ok.size(), total));
                }
                for (String column : columns) {
                    List<Double> values = new ArrayList<>();
                    for (String[] cells : ok) {
                        String value = cells[index.get(column)];
                        if (!value.isEmpty()) {
                            values.add(Double.parseDouble(value));
                        }
                    }
                    if (values.isEmpty()) {
                        continue;
                    }
                    Collections.sort(values);
                    double mean = values.stream().mapToDouble(Double::doubleValue).average().orElse(0);
                    out.add(String.format(Locale.ROOT, "%s,%s,%s,%d,%.1f,%.1f,%.1f,%.1f,%.1f", scenario, subset,
                            column, values.size(), percentile(values, 50), percentile(values, 95), mean,
                            values.get(0), values.get(values.size() - 1)));
                }
            }
        }
        out.addAll(routes);
        return out;
    }

    /** Nearest-rank percentile. */
    static double percentile(List<Double> sorted, double p) {
        int rank = (int) Math.ceil(p / 100.0 * sorted.size());
        return sorted.get(Math.max(0, Math.min(sorted.size() - 1, rank - 1)));
    }

    /** nvidia-smi samples the GPU every 100 ms in the background; null when it is not installed. */
    static Process startGpuSampling() {
        try {
            Process process = new ProcessBuilder("nvidia-smi", "--query-gpu=power.draw,memory.used",
                    "--format=csv,noheader,nounits", "-lms", "100").redirectErrorStream(true).start();
            Thread reader = new Thread(() -> {
                try (BufferedReader in = new BufferedReader(new InputStreamReader(process.getInputStream()))) {
                    String line;
                    while ((line = in.readLine()) != null) {
                        String[] parts = line.split(",");
                        if (parts.length == 2) {
                            try {
                                GPU.add(new GpuSample(System.nanoTime(), Double.parseDouble(parts[0].trim()),
                                        Double.parseDouble(parts[1].trim())));
                            } catch (NumberFormatException ignored) {
                                // "[N/A]" or a header line
                            }
                        }
                    }
                } catch (IOException ignored) {
                    // process stopped
                }
            });
            reader.setDaemon(true);
            reader.start();
            return process;
        } catch (IOException e) {
            System.out.println("nvidia-smi tidak ditemukan: kolom GPU dikosongkan");
            return null;
        }
    }

    /** GPU power and memory during one request: mean watts, energy (mean watts x duration) and peak memory. */
    static void gpuWindow(long start, long end, Map<String, String> result) {
        double watts = 0;
        double peak = 0;
        int n = 0;
        for (GpuSample sample : GPU) {
            if (sample.nanos() >= start && sample.nanos() <= end) {
                watts += sample.watts();
                peak = Math.max(peak, sample.memMiB());
                n++;
            }
        }
        if (n > 0) {
            double mean = watts / n;
            result.put("gpu_avg_w", String.format(Locale.ROOT, "%.1f", mean));
            result.put("gpu_energy_j", String.format(Locale.ROOT, "%.1f", mean * (end - start) / 1e9));
            result.put("gpu_peak_mem_mib", String.format(Locale.ROOT, "%.0f", peak));
        }
    }

    /** Versions and machine state, so the run can be described and repeated in the paper. */
    static void writeEnvironment(Path file, String url, int reps, int warmup, long seed, int questions)
            throws IOException {
        List<String> lines = new ArrayList<>();
        lines.add("date: " + LocalDateTime.now());
        lines.add("url: " + url + "  reps: " + reps + "  warmup: " + warmup + "  seed: " + seed
                + "  questions: " + questions);
        lines.add("java: " + System.getProperty("java.version"));
        String[][] commands = {
            {"git", "rev-parse", "HEAD"},
            {"git", "status", "--short"},
            {"docker", "exec", "ollama", "ollama", "--version"},
            {"docker", "exec", "ollama", "ollama", "list"},
            {"docker", "exec", "ollama", "ollama", "ps"},
            {"docker", "exec", "ollama", "printenv", "OLLAMA_NUM_PARALLEL"},
            {"docker", "ps", "--format", "{{.Names}} {{.Image}} {{.Status}}"},
            {"nvidia-smi", "--query-gpu=name,driver_version,power.limit,clocks.max.graphics,memory.total",
                "--format=csv"},
            {"powercfg", "/getactivescheme"},
            {"powershell", "-NoProfile", "-Command",
                "(Get-CimInstance Win32_Battery | Select-Object -First 1).BatteryStatus"},
        };
        for (String[] command : commands) {
            lines.add("");
            lines.add("$ " + String.join(" ", command));
            try {
                Process process = new ProcessBuilder(command).redirectErrorStream(true).start();
                lines.add(new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8).strip());
            } catch (IOException e) {
                lines.add("(gagal: " + e.getMessage() + ")");
            }
        }
        lines.add("");
        lines.add("BatteryStatus 2 = tersambung listrik (AC), 1 = memakai baterai");
        Files.write(file, lines, StandardCharsets.UTF_8);
    }

    static List<Question> readQuestions(Path file) throws IOException {
        List<Question> questions = new ArrayList<>();
        for (String line : Files.readAllLines(file, StandardCharsets.UTF_8)) {
            if (line.isBlank() || line.startsWith("#")) {
                continue;
            }
            String[] cells = line.split(";", -1);
            questions.add(new Question(cells[0], cells[1], cells[2], cells.length > 3 ? cells[3] : ""));
        }
        return questions;
    }

    static Map<String, String> options(String[] args) {
        Map<String, String> options = new LinkedHashMap<>();
        for (int i = 0; i + 1 < args.length; i += 2) {
            options.put(args[i].replaceFirst("^--", ""), args[i + 1]);
        }
        return options;
    }

    static String mimeType(Path image) {
        String name = image.getFileName().toString().toLowerCase(Locale.ROOT);
        return name.endsWith(".png") ? "image/png" : name.endsWith(".webp") ? "image/webp" : "image/jpeg";
    }

    static String round(String value) {
        return value == null || value.isEmpty() ? "" : String.format(Locale.ROOT, "%.1f", Double.parseDouble(value));
    }

    static String unescape(String s) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c != '\\' || i + 1 >= s.length()) {
                out.append(c);
                continue;
            }
            char next = s.charAt(++i);
            switch (next) {
                case 'n' -> out.append('\n');
                case 't' -> out.append('\t');
                case 'r' -> out.append('\r');
                case 'u' -> {
                    out.append((char) Integer.parseInt(s.substring(i + 1, i + 5), 16));
                    i += 4;
                }
                default -> out.append(next);
            }
        }
        return out.toString();
    }
}
