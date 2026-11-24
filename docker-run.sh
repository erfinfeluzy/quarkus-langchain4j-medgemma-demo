#!/usr/bin/env bash
#
# Menjalankan demo-med-ai dengan "docker run" di network demo-net, tanpa docker compose.
# MySQL, Redis, dan Ollama dipakai bersama dengan demo HR (satu container saja):
#   demo-mysql:3306 (schema clinic), demo-redis:6379 (prefix med-rag:), ollama:11434, med-app:8080
#
# Pemakaian (dari Git Bash, di folder project):
#   ./docker-run.sh            jalankan semua service (mysql, redis, ollama, app)
#   ./docker-run.sh mysql      jalankan satu service saja (mysql|redis|ollama|app)
#   ./docker-run.sh schema     buat ulang schema clinic dari db/init.sql (data pasien di-reset)
#   ./docker-run.sh build      build jar + image aplikasi
#   ./docker-run.sh redeploy   build ulang lalu ganti container aplikasi
#   ./docker-run.sh status     lihat container yang ada di network
#   ./docker-run.sh stop       stop med-app (mysql, redis, ollama dipakai bersama, tidak ikut)

set -euo pipefail

# Git Bash mengubah path seperti /var/lib/mysql jadi path Windows; matikan itu
export MSYS_NO_PATHCONV=1

NETWORK=demo-net
APP_IMAGE=quarkus/demo-med-ai-jvm
APP_PORT=8081

cd "$(dirname "$0")"
# Path project dalam format yang dimengerti Docker Desktop (C:/Users/...)
PROJECT_DIR=$(pwd -W 2>/dev/null || pwd)

exists()  { docker container inspect "$1" >/dev/null 2>&1; }
running() { [ "$(docker container inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" = "true" ]; }

ensure_network() {
  if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
    echo ">> membuat network $NETWORK"
    docker network create "$NETWORK" >/dev/null
  fi
}

# Container yang sudah ada tidak dibuat ulang: cukup di-start dan disambungkan ke network
reuse() {
  local name=$1
  exists "$name" || return 1
  running "$name" || { echo ">> start $name"; docker start "$name" >/dev/null; }
  if ! docker container inspect -f "{{json .NetworkSettings.Networks}}" "$name" | grep -q "\"$NETWORK\""; then
    echo ">> sambungkan $name ke $NETWORK"
    docker network connect "$NETWORK" "$name"
  fi
  echo ">> $name sudah jalan"
}

run_mysql() {
  if ! reuse demo-mysql; then
    echo ">> membuat demo-mysql"
    docker run -d --name demo-mysql --network "$NETWORK" \
      -p 127.0.0.1:3306:3306 \
      -e MYSQL_ROOT_PASSWORD=rootpass \
      -v demo_mysql-data:/var/lib/mysql \
      mysql:8.4 >/dev/null
  fi
  wait_mysql
  # Schema clinic hanya dibuat kalau belum ada, supaya data yang sudah diubah tidak hilang
  if ! docker exec demo-mysql mysql -uroot -prootpass -N -e "SHOW DATABASES LIKE 'clinic'" 2>/dev/null | grep -q clinic; then
    create_schema
  fi
}

create_schema() {
  echo ">> membuat schema clinic dari db/init.sql"
  docker exec -i demo-mysql mysql -uroot -prootpass < db/init.sql 2>/dev/null
}

run_redis() {
  reuse demo-redis && return
  echo ">> membuat demo-redis"
  docker run -d --name demo-redis --network "$NETWORK" \
    -p 127.0.0.1:6379:6379 \
    -v demo_redis-data:/data \
    redis:8 >/dev/null
}

run_ollama() {
  reuse ollama && return
  echo ">> membuat ollama"
  docker run -d --name ollama --network "$NETWORK" --gpus all \
    -p 127.0.0.1:11434:11434 \
    -e OLLAMA_HOST=0.0.0.0:11434 \
    -e OLLAMA_CONTEXT_LENGTH=8192 \
    -e OLLAMA_FLASH_ATTENTION=1 \
    -e LLAMA_ARG_CACHE_RAM=0 \
    -v ollama:/root/.ollama \
    ollama/ollama >/dev/null
  # Download model kalau belum ada (sekali saja, disimpan di volume ollama)
  sleep 3
  docker exec ollama ollama pull qwen2.5:3b
  docker exec ollama ollama pull hf.co/unsloth/medgemma-4b-it-GGUF:Q4_K_M
  # Varian dengan context 8K (lihat application.properties); berbagi file model, tidak menambah disk
  docker exec ollama sh -c 'printf "FROM hf.co/unsloth/medgemma-4b-it-GGUF:Q4_K_M\nPARAMETER num_ctx 8192\n" > /tmp/Modelfile && ollama create medgemma-4b-it-8k:q4_k_m -f /tmp/Modelfile'
  docker exec ollama ollama pull nomic-embed-text
}

wait_mysql() {
  echo -n ">> menunggu MySQL siap"
  for _ in $(seq 1 60); do
    if docker exec demo-mysql mysqladmin ping -h 127.0.0.1 -uroot -prootpass --silent >/dev/null 2>&1; then
      echo " OK"; return
    fi
    echo -n "."; sleep 2
  done
  echo; echo "!! MySQL belum siap setelah 2 menit, cek: docker logs demo-mysql" >&2
  exit 1
}

build_app() {
  echo ">> build jar"
  # mvnw butuh konversi path Git Bash yang dimatikan di atas untuk perintah docker
  env -u MSYS_NO_PATHCONV ./mvnw package -DskipTests
  echo ">> build image $APP_IMAGE"
  docker build -f src/main/docker/Dockerfile.jvm -t "$APP_IMAGE" .
}

run_app() {
  if ! docker image inspect "$APP_IMAGE" >/dev/null 2>&1; then
    build_app
  fi
  # Aplikasi selalu dibuat ulang supaya memakai image dan env terbaru
  if exists med-app; then
    echo ">> hapus med-app lama"
    docker rm -f med-app >/dev/null
  fi
  wait_mysql
  echo ">> membuat med-app"
  docker run -d --name med-app --network "$NETWORK" \
    -p "127.0.0.1:$APP_PORT:8080" \
    -v "$PROJECT_DIR/rag-docs:/deployments/rag-docs:ro" \
    -e QUARKUS_DATASOURCE_JDBC_URL=jdbc:mysql://demo-mysql:3306/clinic \
    -e QUARKUS_REDIS_HOSTS=redis://demo-redis:6379 \
    -e QUARKUS_LANGCHAIN4J_OLLAMA_BASE_URL=http://ollama:11434 \
    -e QUARKUS_LANGCHAIN4J_EASY_RAG_PATH=/deployments/rag-docs \
    -e MED_BENCHMARK_ENABLED="${MED_BENCHMARK_ENABLED:-false}" \
    "$APP_IMAGE" >/dev/null
  echo ">> aplikasi jalan di http://localhost:$APP_PORT  (log: docker logs -f med-app)"
}

status() {
  echo "Container di network $NETWORK:"
  docker network inspect "$NETWORK" -f '{{range .Containers}}  {{.Name}}{{println}}{{end}}'
  docker ps -a --filter "network=$NETWORK" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
}

case "${1:-all}" in
  all)      ensure_network; run_mysql; run_redis; run_ollama; run_app; status ;;
  mysql)    ensure_network; run_mysql ;;
  schema)   wait_mysql; create_schema ;;
  redis)    ensure_network; run_redis ;;
  ollama)   ensure_network; run_ollama ;;
  app)      ensure_network; run_app ;;
  build)    build_app ;;
  redeploy) ensure_network; build_app; run_app ;;
  status)   status ;;
  stop)     docker stop med-app ;;
  *)        sed -n '2,15p' "$0"; exit 1 ;;
esac
