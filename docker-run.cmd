@echo off
rem
rem Menjalankan demo-med-ai dengan "docker run" di network demo-net, tanpa docker compose.
rem MySQL, Redis, dan Ollama dipakai bersama dengan demo HR (satu container saja):
rem   demo-mysql:3306 (schema clinic), demo-redis:6379 (prefix med-rag:), ollama:11434, med-app:8080
rem
rem Pemakaian (dari CMD atau PowerShell, di folder project):
rem   docker-run.cmd            jalankan semua service (mysql, redis, ollama, app)
rem   docker-run.cmd mysql      jalankan satu service saja (mysql^|redis^|ollama^|app)
rem   docker-run.cmd schema     buat ulang schema clinic dari db/init.sql (data pasien di-reset)
rem   docker-run.cmd build      build jar + image aplikasi
rem   docker-run.cmd redeploy   build ulang lalu ganti container aplikasi
rem   docker-run.cmd status     lihat container yang ada di network
rem   docker-run.cmd stop       stop med-app (mysql, redis, ollama dipakai bersama, tidak ikut)

setlocal EnableDelayedExpansion

set NETWORK=demo-net
set APP_IMAGE=quarkus/demo-med-ai-jvm
set APP_PORT=8081

cd /d "%~dp0"
rem Path project tanpa backslash di akhir (C:\Users\...\demo-med-ai)
set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

set "CMD=%~1"
if "%CMD%"=="" set CMD=all

if /i "%CMD%"=="all" (
  call :ensure_network || goto :fail
  call :run_mysql || goto :fail
  call :run_redis || goto :fail
  call :run_ollama || goto :fail
  call :run_app || goto :fail
  call :status
  goto :end
)
if /i "%CMD%"=="mysql"    ( call :ensure_network && call :run_mysql  || goto :fail & goto :end )
if /i "%CMD%"=="schema"   ( call :wait_mysql && call :create_schema || goto :fail & goto :end )
if /i "%CMD%"=="redis"    ( call :ensure_network && call :run_redis  || goto :fail & goto :end )
if /i "%CMD%"=="ollama"   ( call :ensure_network && call :run_ollama || goto :fail & goto :end )
if /i "%CMD%"=="app"      ( call :ensure_network && call :run_app    || goto :fail & goto :end )
if /i "%CMD%"=="build"    ( call :build_app || goto :fail & goto :end )
if /i "%CMD%"=="redeploy" ( call :ensure_network && call :build_app && call :run_app || goto :fail & goto :end )
if /i "%CMD%"=="status"   ( call :status & goto :end )
if /i "%CMD%"=="stop"     ( docker stop med-app & goto :end )

echo Pemakaian: docker-run.cmd [all^|mysql^|schema^|redis^|ollama^|app^|build^|redeploy^|status^|stop]
exit /b 1


rem ---------------------------------------------------------------------------
:ensure_network
docker network inspect %NETWORK% >nul 2>&1
if errorlevel 1 (
  echo ^>^> membuat network %NETWORK%
  docker network create %NETWORK% >nul || exit /b 1
)
exit /b 0


rem Container yang sudah ada tidak dibuat ulang: cukup di-start dan disambungkan ke network.
rem errorlevel 0 = container sudah ada dan dipakai ulang, 1 = belum ada
:reuse
docker container inspect %1 >nul 2>&1
if errorlevel 1 exit /b 1
set RUNNING=
for /f %%r in ('docker container inspect -f "{{.State.Running}}" %1') do set RUNNING=%%r
if not "%RUNNING%"=="true" (
  echo ^>^> start %1
  docker start %1 >nul
)
docker container inspect -f "{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}" %1 | findstr /r /c:"\<%NETWORK%\>" >nul
if errorlevel 1 (
  echo ^>^> sambungkan %1 ke %NETWORK%
  docker network connect %NETWORK% %1
)
echo ^>^> %1 sudah jalan
exit /b 0


:run_mysql
call :reuse demo-mysql
if errorlevel 1 (
  echo ^>^> membuat demo-mysql
  docker run -d --name demo-mysql --network %NETWORK% ^
    -p 127.0.0.1:3306:3306 ^
    -e MYSQL_ROOT_PASSWORD=rootpass ^
    -v demo_mysql-data:/var/lib/mysql ^
    mysql:8.4 >nul || exit /b 1
)
call :wait_mysql || exit /b 1
rem Schema clinic hanya dibuat kalau belum ada, supaya data yang sudah diubah tidak hilang
docker exec demo-mysql mysql -uroot -prootpass -N -e "SHOW DATABASES LIKE 'clinic'" 2>nul | findstr clinic >nul
if errorlevel 1 call :create_schema
exit /b %errorlevel%


:create_schema
echo ^>^> membuat schema clinic dari db/init.sql
docker exec -i demo-mysql mysql -uroot -prootpass < db\init.sql 2>nul
exit /b %errorlevel%


:run_redis
call :reuse demo-redis && exit /b 0
echo ^>^> membuat demo-redis
docker run -d --name demo-redis --network %NETWORK% ^
  -p 127.0.0.1:6379:6379 ^
  -v demo_redis-data:/data ^
  redis:8 >nul
exit /b %errorlevel%


:run_ollama
call :reuse ollama && exit /b 0
echo ^>^> membuat ollama
docker run -d --name ollama --network %NETWORK% --gpus all ^
  -p 127.0.0.1:11434:11434 ^
  -e OLLAMA_HOST=0.0.0.0:11434 ^
  -e OLLAMA_CONTEXT_LENGTH=32768 ^
  -v ollama:/root/.ollama ^
  ollama/ollama >nul || exit /b 1
rem Download model kalau belum ada (sekali saja, disimpan di volume ollama)
ping -n 4 127.0.0.1 >nul
docker exec ollama ollama pull llama3.1:8b || exit /b 1
docker exec ollama ollama pull nomic-embed-text
exit /b %errorlevel%


:wait_mysql
<nul set /p "=>> menunggu MySQL siap"
for /l %%i in (1,1,60) do (
  docker exec demo-mysql mysqladmin ping -h 127.0.0.1 -uroot -prootpass --silent >nul 2>&1
  if not errorlevel 1 (
    echo  OK
    exit /b 0
  )
  <nul set /p "=."
  ping -n 3 127.0.0.1 >nul
)
echo.
echo !! MySQL belum siap setelah 2 menit, cek: docker logs demo-mysql 1>&2
exit /b 1


:build_app
echo ^>^> build jar
call mvnw.cmd package -DskipTests || exit /b 1
echo ^>^> build image %APP_IMAGE%
docker build -f src/main/docker/Dockerfile.jvm -t %APP_IMAGE% .
exit /b %errorlevel%


:run_app
docker image inspect %APP_IMAGE% >nul 2>&1
if errorlevel 1 (
  call :build_app || exit /b 1
)
rem Aplikasi selalu dibuat ulang supaya memakai image dan env terbaru
docker container inspect med-app >nul 2>&1
if not errorlevel 1 (
  echo ^>^> hapus med-app lama
  docker rm -f med-app >nul
)
call :wait_mysql || exit /b 1
echo ^>^> membuat med-app
docker run -d --name med-app --network %NETWORK% ^
  -p 127.0.0.1:%APP_PORT%:8080 ^
  -v "%PROJECT_DIR%\rag-docs:/deployments/rag-docs:ro" ^
  -e QUARKUS_DATASOURCE_JDBC_URL=jdbc:mysql://demo-mysql:3306/clinic ^
  -e QUARKUS_REDIS_HOSTS=redis://demo-redis:6379 ^
  -e QUARKUS_LANGCHAIN4J_OLLAMA_BASE_URL=http://ollama:11434 ^
  -e QUARKUS_LANGCHAIN4J_EASY_RAG_PATH=/deployments/rag-docs ^
  %APP_IMAGE% >nul || exit /b 1
echo ^>^> aplikasi jalan di http://localhost:%APP_PORT%  (log: docker logs -f med-app)
exit /b 0


:status
echo Container di network %NETWORK%:
docker network inspect %NETWORK% -f "{{range .Containers}}  {{.Name}}{{println}}{{end}}"
docker ps -a --filter "network=%NETWORK%" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
exit /b 0


:fail
echo !! gagal, lihat pesan di atas 1>&2
exit /b 1

:end
endlocal
exit /b 0
