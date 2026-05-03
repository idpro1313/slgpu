# Мониторинг

**Логи всех контейнеров в одно место (journald, Loki, syslog):** см. [LOGS.md](LOGS.md). В стеке мониторинга уже подняты **Grafana Loki** + **Promtail** (данные на диске: `LOKI_DATA_DIR`, `PROMTAIL_DATA_DIR` в `main.env`); просмотр в **Grafana → Explore → Loki**.

**Postgres, ClickHouse, Redis, MinIO, Langfuse, LiteLLM** — в [`docker/docker-compose.proxy.yml`](../../docker/docker-compose.proxy.yml) (проект **`slgpu-proxy`**; подъём из **Develonica.LLM** / `native.*`, сеть `slgpu` с [`docker/docker-compose.llm.yml`](../../docker/docker-compose.llm.yml)). Стек **метрик и логов** (Prometheus, Grafana, Loki, Promtail, DCGM, node-exporter) — в [`docker/docker-compose.monitoring.yml`](../../docker/docker-compose.monitoring.yml). UI Langfuse по умолчанию **`:3001`** (`LANGFUSE_PORT`), чтобы не конфликтовать с Grafana **:3000**. MinIO наружу: **`:9010`** / **`:9011`** (`MINIO_*_HOST_PORT`), не **:9090** (Prometheus). Секреты (`NEXTAUTH_SECRET`, `LANGFUSE_ENCRYPTION_KEY`, пароли БД) — в [`main.env`](../../main.env); для продакшена смените дефолты. **LiteLLM:** в репо — [`litellm/config.yaml`](litellm/config.yaml) только **`litellm_settings`** (callbacks, `drop_params`); **модели и `api_base` к vLLM** — в **БД** / [**Admin UI** `/ui`](https://docs.litellm.ai/docs/proxy/ui) при **`STORE_MODEL_IN_DB`**. Клиент: `http://<хост>:LITELLM_PORT/v1/…`, **`"model": "<как в UI>"`** (часто совпадает с `SERVED_MODEL_NAME` / **`devllm`** (старое: `SLGPU_SERVED_MODEL_NAME`) на стороне vLLM). В [`main.env`](../../main.env) **`UI_USERNAME`**, **`UI_PASSWORD`**; **`x-api-key`** — если задан ненулевой **`LITELLM_MASTER_KEY`** (пусто = без ключа, только в закрытой сети). Роуты и цены — в `/ui`, не в `config.yaml`. Трейсинг в Langfuse: в UI — проект → API keys; ключи для LiteLLM — в **[`configs/secrets/langfuse-litellm.env`](../secrets/langfuse-litellm.env.example)** (копия из `*.example`, файл в `.gitignore`), не в `main.env`. При первом **подъёме прокси-стека** из UI (**LiteLLM Proxy** / `native.proxy.*`) пустой файл создаётся из примера, а init-контейнеры bootstrap (профиль `bootstrap` в `docker-compose.proxy.yml`) создают MinIO buckets и БД LiteLLM; **мониторинг** (`native.monitoring.*`) к proxy **не** поднимает. В [`litellm/config.yaml`](litellm/config.yaml) для **Langfuse 3** задано **`callbacks: ["langfuse_otel"]`**. В **proxy** у **litellm**: **`LANGFUSE_OTEL_HOST`** → `http://langfuse-web:3000`, **`STORE_MODEL_IN_DB`**, **`DATABASE_URL`** — хост **`postgres`** (тот же compose, сервис Postgres для Langfuse/LiteLLM).

## Порты: настройки web и `docker compose`

- **Панель «Настройки»** (web) сохраняет значения в **SQLite** (`stack_params`), а не в файл `main.env` автоматически.
- **Запуск мониторинга из Develonica.LLM** и **native-задания** используют один файл **`${WEB_DATA_DIR}/.slgpu/compose-service.env`** (по умолч. **`data/web/.slgpu/…`**, под `data/`): в web он **заполняется строго из БД** (`stack_params` / `sync_merged_flat(require_db=True)`) перед `docker compose`; в bash — **копия `main.env`**, если он есть, иначе `configs/main.env`. Сервисы в compose ссылаются на этот путь в **`env_file:`**, а опубликованные порты/имена проектов в `docker-compose.monitoring.yml` и `docker-compose.proxy.yml` **без YAML fallback** — если БД-снимок не подставился, compose падает, а не молча берёт `3000/9090/3001`.
- **Задачи из web** (`native.monitoring.*`, `native.proxy.*`) **всегда** пишут стек из БД в этот путь (доступен **slgpuweb** под `data/web`, без записи в `<repo>/.slgpu` в корне) и запускают Docker Compose с очищенным окружением, чтобы env контейнера web / хоста не перебивал значения из БД.
- **LiteLLM master-key:** задаётся в **«Настройки» → «Внешний доступ» → litellm_api_key** (SQLite **`settings.public_access`**); **`sync_merged_flat`** подставляет её как переменную окружения **`LITELLM_MASTER_KEY`** для `docker compose proxy`. В **`configs/main.env`** ключ для этого случая больше не перечисляется (**since 7.0**); без UI добавьте **`export LITELLM_MASTER_KEY=...`** перед **`compose`** или используйте снимок **`compose-service.env`** от backend после сохранения ключа в UI.

**Что делать:** после смены портов в web перезапускайте затронутый стек **из UI (Задачи)** — **Мониторинг** или **LiteLLM Proxy** отдельно. `main.env` нужен для **`./slgpu web`**, одноразового **install** и ручного `docker compose` на хосте; для операций из UI источником остаётся **SQLite**.

В [`docker/docker-compose.monitoring.yml`](../../docker/docker-compose.monitoring.yml) публикация на хост: **Grafana** — `${GRAFANA_PORT}`; **Prometheus** — `${PROMETHEUS_PORT}`; **Loki** — `${LOKI_PORT}` (и `${LOKI_BIND}`, по умолч. `127.0.0.1`).

**Grafana: provisioning.** Сервис `grafana` монтирует **отдельно** каталоги `configs/monitoring/grafana/provisioning/{dashboards,alerting,plugins}` и **файл** `${WEB_DATA_DIR}/.slgpu/monitoring/datasource.yml` → `…/datasources/datasource.yml`. Раньше весь `provisioning` с `:ro` и второй bind файла внутри дерева давал у runc «read-only file system» (нельзя создать mountpoint внутри read-only parent).

**Версии образов (дефолты `main.env`):** **Loki** **3.7.1** (конфиг **Loki 3** — `schema: v13`, `store: tsdb`, блок `common.storage` в [`loki/loki-config.yaml.tmpl`](loki/loki-config.yaml.tmpl); **не используйте** устаревший **`chunk_store_config.max_look_back_period`** из Loki 2.x — в Loki 3 поля нет (`ChunkStoreConfig` падает на парсинге); глубину запросов задаёт **`limits_config.max_query_lookback`**. Если **`compactor.retention_enabled: true`**, задайте **`compactor.delete_request_store`** (в шаблоне — **`filesystem`**, иначе валидация: *delete-request-store should be configured when retention is enabled*). При апгрейде **с Loki 2** и старого boltdb-shipper в `LOKI_DATA_DIR` следуйте [Upgrade Loki](https://grafana.com/docs/loki/latest/setup/upgrade/) или очистите каталог после бэкапа). **Promtail** — **3.6.10** (тега **`grafana/promtail:3.7.1`** на Docker Hub нет — выравниваем по линии **3.x**; при появлении **3.7.1** можно сменить в `main.env`). **Grafana** — **13.0.1**; **Prometheus** — **v3.11.3** (правила/скрейп в репо совместимы; при сюрпризах — [Migrate to Prometheus 3](https://prometheus.io/docs/prometheus/3.0/migration/)). **node-exporter** — **v1.11.1**; **DCGM** — **4.5.2-4.8.1**. **`SLGPU_BENCH_CHOWN_IMAGE`** — **alpine:3.21.7**. На VM: `docker compose pull` и пересоздание сервисов; после смены Loki — `native.monitoring.up` (перерендер `loki-config.yaml`).

### LiteLLM: подробные логи (отладка)

В [`main.env`](../../main.env) задайте **`LITELLM_LOG=DEBUG`**, пересоздайте контейнер `slgpu-proxy-litellm` (эквивалент CLI **`--detailed_debug`**: больше деталей по запросам к vLLM и по ошибкам). По умолчанию **`LITELLM_LOG=INFO`**. См. [Debugging | LiteLLM](https://docs.litellm.ai/docs/proxy/debugging). Для диагностики OTEL-экспорта (Langfuse) можно временно **`OTEL_LOG_LEVEL=debug`** в `main.env`.

### Langfuse: HTTP 500 — object storage (MinIO / S3), не путать с OTEL

**Два разных источника 500:**

1. **LiteLLM** шлёт спаны в Langfuse по OTLP — в логах **контейнера `slgpu-proxy-litellm`** бывает `Transient error … exporting span` (см. раздел «подробные логи» выше, заголовок `x-langfuse-ingestion-version`, сеть до `langfuse-web`).
2. **Langfuse** не может залить события/медиа в настроенное **blob-хранилище** (S3, MinIO, Azure…) — приём может отвечать **500**; в логах **`langfuse-web`** или **`langfuse-worker`** чаще видно ошибку **credentials / endpoint / bucket**, а не OTLP.

**В этом репо** объектное хранилище — **MinIO** в compose (`minio:9000` в сети `slgpu`); в [`docker/docker-compose.proxy.yml`](../../docker/docker-compose.proxy.yml) у web/worker заданы **`LANGFUSE_S3_*`** (бакет по умолч. **`langfuse`**, `FORCE_PATH_STYLE`, endpoint `http://minio:9000`) и **`MINIO_ROOT_USER`** / **`MINIO_ROOT_PASSWORD`** из [`main.env`](../../main.env). Сервис **`minio-bucket-init`** (образ `mc`) вынесен в профиль **`bootstrap`** и создаёт бакеты `LANGFUSE_S3_EVENT_UPLOAD_BUCKET` / `LANGFUSE_S3_MEDIA_BUCKET` один раз при первом **`native.proxy.up`** (UI **LiteLLM Proxy**); marker: `data/monitoring/.bootstrap/minio-bucket-init.done`. Без бакетов в логах web: **`NoSuchBucket`**, **`Failed to upload JSON to S3`**, **`events/otel/…`**. Повторить: снова **proxy up** из UI или `SLGPU_MONITORING_BOOTSTRAP_FORCE=1` + тот же bootstrap-контейнер. Проверьте: контейнер **`minio` healthy**; **ключи** совпадают; **диск** `LANGFUSE_MINIO_DATA_DIR` с корректными правами. Для деталей по причине — временно **`LANGFUSE_LOG_LEVEL=debug`** в `main.env` и пересоздание **`langfuse-web`** и **`langfuse-worker`**. Оф. переменные: [Configuration (self-hosted)](https://langfuse.com/self-hosting/configuration), общий troubleshooting: [Troubleshooting & FAQ](https://langfuse.com/self-hosting/troubleshooting-and-faq).

### LiteLLM: «Authentication Error, Not connected to DB!»

Нужен **PostgreSQL** для Prisma (Admin UI `/ui`, виртуальные ключи). Сервис **`litellm-pg-init`** (в **proxy**, profile **`bootstrap`**) создаёт БД **`litellm`**; marker: `data/monitoring/.bootstrap/litellm-pg-init.done`. У контейнера **LiteLLM** в [`docker-compose.proxy.yml`](../../docker/docker-compose.proxy.yml) в **`DATABASE_URL`** указан хост **`postgres`** (имя сервиса в том же compose). Повторить bootstrap: **proxy up** из UI (страница **LiteLLM Proxy**).

## Доступ к Langfuse извне (интернет / другая сеть)

1. **`NEXTAUTH_URL`** в [`main.env`](../../main.env) — **обязан** совпадать с тем URL, по которому вы открываете UI: схема + хост + порт. Для `127.0.0.1` вход с другой машины **не** заработает. Примеры: `https://langfuse.yourdomain.com` (лучше за reverse proxy), `http://203.0.113.7:3001` (тест по IP), после смены — **перезапуск стека из UI**.
2. **Прослушивание:** в репо задано **`LANGFUSE_BIND=0.0.0.0`** — порт `LANGFUSE_PORT` (по умолч. 3001) слушается на всех интерфейсах. Чтобы **не** светить наружу, поставьте `LANGFUSE_BIND=127.0.0.1` и публикуйте Langfuse **только** через Nginx/Traefik на 443. **`curl` / браузер: connection reset** к `:3001` с хоста: для сервиса `langfuse-web` в [`docker/docker-compose.proxy.yml`](../../docker/docker-compose.proxy.yml) задано **`HOSTNAME=0.0.0.0`**, иначе Next.js может слушать не все интерфейсы в контейнере (см. [FAQ Langfuse](https://langfuse.com/faq/all/debug-docker-deployment)); после обновления репо пересоздайте контейнер: `docker compose -f docker/docker-compose.proxy.yml --env-file main.env up -d --force-recreate langfuse-web`.
3. **Фаервол / security group** — откройте только нужный порт (или 80/443 у прокси), остальные сервисы мониторинга (Prometheus, MinIO) по возможности **не** публикуйте в интернет.
4. **Секреты** — смените `NEXTAUTH_SECRET`, `LANGFUSE_ENCRYPTION_KEY`, пароли БД/Redis/MinIO/Postgres в проде.
5. **SDK** (приложения на других хостах): base URL = тот же публичный хост, что в `NEXTAUTH_URL` (часто `https://...` без пути, см. [док. Langfuse](https://langfuse.com/docs) по клиенту).

**После регистрации редирект на `http://127.0.0.1:3001`:** в [`main.env`](../../main.env) задан непубличный `NEXTAUTH_URL`. Исправьте на тот URL, с которого открываете UI (например `http://<ваш-IP>:3001`), **без** слэша в конце, затем `docker compose -f docker/docker-compose.proxy.yml --env-file main.env up -d` или **рестарт из UI**, очистите cookies для сайта и снова зайдите.

Метрики и логи: [`docker/docker-compose.monitoring.yml`](../../docker/docker-compose.monitoring.yml) (`native.monitoring.*`); **Langfuse, MinIO, Postgres (Langfuse/LiteLLM), LiteLLM** — [`docker/docker-compose.proxy.yml`](../../docker/docker-compose.proxy.yml) (`native.proxy.*`, **отдельно** от мониторинга). Сеть **`slgpu`** общая с [`docker/docker-compose.llm.yml`](../../docker/docker-compose.llm.yml) (отдельной bridge-сети `langfuse` больше нет). **vLLM и SGLang** в [`prometheus/prometheus.yml`](prometheus/prometheus.yml) скрейпятся **не** по имени `vllm:8111` (между разными compose-проектами краткое имя `vllm` часто не резолвится), а через **`host.docker.internal:<порт_на_хосте>`** (мост в хост, где опубликованы `LLM_API_PORT` → 8111 / 8222). У сервиса `prometheus` в compose задано `extra_hosts: host.docker.internal:host-gateway` (Linux). Метка **`instance`** для рядов — **`vllm:8111`** / **`sglang:8222`** (Grafana, переменные).

**Мультислотный vLLM из UI Develonica.LLM:** у каждого слота свой **`host_api_port`** на хосте (на странице Runtime — колонка порта). Job **`vllm`** по-прежнему один раз скрейпит только **`LLM_API_PORT`** из стека. Дополнительные порты перечисляются в **`${WEB_DATA_DIR}/.slgpu/monitoring/vllm-slots.json`** (рядом с `prometheus.yml`): при первом рендере мониторинга backend создаёт файл с **дефолтным диапазоном хост-портов `8110–8130`** inclusive (`host.docker.internal:<port>` для каждого), если файла ещё не было (**8.1.7**); дальше файл **не перезаписывается** при «Мониторинг up/restart» (правьте JSON вручную, если нужен другой диапазон или отдельные порты). Targets по свободным портам покажут **DOWN** — ожидаемо. Формат — [Prometheus `file_sd`](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#file_sd_config): массив групп с `targets` и опционально `labels`. Пример — [`prometheus/vllm-slots.json.example`](prometheus/vllm-slots.json.example). После правки JSON подождите до **30s** (`refresh_interval`) или перезапустите контейнер **prometheus**. В **Prometheus → Status → Targets** появится job **`vllm-slots`** (по одному target на порт). Метка **`instance`** выставляется как **`vllm:<порт>`** (как у основного job). В **Grafana** для дашбордов vLLM с фильтром `job="vllm"` добавьте серии со **`job="vllm-slots"`** или замените на `job=~"vllm|vllm-slots"`.

- **Prometheus** (по умолч. **`0.0.0.0:9090`** на хосте, см. `PROMETHEUS_BIND` в [`main.env`](../../main.env)): UI и HTTP API **без аутентификации** — в проде закройте фаерволом или поставьте `PROMETHEUS_BIND=127.0.0.1` и ходите по SSH tunnel. Скрейп vLLM/SGLang: **см. выше**; плюс `dcgm-exporter:9400`, **`node-exporter:9100`**. **Нестандартный `LLM_API_PORT`:** поправьте **хостовый** порт в `targets` в [`prometheus/prometheus.yml`](prometheus/prometheus.yml) (должен совпадать с левой частью `ports` в `docker/docker-compose.llm.yml` для выбранного движка).
  - **SGLang:** для наполнения оф. Grafana «SGLang Dashboard» сервер должен запускаться с **`--enable-metrics`** (в slgpu: по умолчанию через `SGLANG_ENABLE_METRICS=1` в `serve.sh`). Иначе панели по `sglang:*` часто пустые.
  - Когда контейнер vLLM или SGLang **не поднят** (другой профиль compose) — на хосте **нет** слушателя на 8111/8222, target будет **DOWN**. Это ожидаемо для A/B; смотрите метрики активного движка.
- **Grafana** (`127.0.0.1:3000`): datasource Prometheus подключён автоматически.
- **Алерты**: [prometheus/prometheus-alerts.yml](prometheus/prometheus-alerts.yml) (пороги при необходимости ослабьте, если метрики в вашей версии vLLM называются иначе).

## Рекомендуемые дашборды (импорт в UI Grafana)

1. **NVIDIA DCGM** — dashboard ID [12239](https://grafana.com/grafana/dashboards/12239).
2. **Node Exporter Full** (хост: CPU, RAM, диск, сеть) — dashboard ID [**1860**](https://grafana.com/grafana/dashboards/1860).  
   - **Dashboards → Import →** вставьте `1860` → Load.  
   - Datasource: **Prometheus** (как в provisioning, uid `prometheus`).  
   - Убедитесь, что контейнер **`node-exporter`** запущен: **`подъём стека из UI («Мониторинг»)`** (или `docker compose -f docker/docker-compose.monitoring.yml up -d node-exporter`).  
   - В выпадающих списках вверху дашборда выберите **Datasource: Prometheus**, **job = `node-exporter`**, **instance** — обычно **`host`** (так задан label в [`prometheus/prometheus.yml`](prometheus/prometheus.yml)); в других ревизиях дашборда может быть `node-exporter:9100`.
3. **vLLM** — поиск на grafana.com по `vllm` (ID зависят от версии; импорт через **Dashboards → Import**). В репозитории: [`vllmdash2.json`](grafana/templates/vllmdash2.json) — **V2**; datasource **`prometheus`**, переменные **`instance`** / **`Model`** (с **All**), в запросах `job="vllm"`, `model_name=~"$model_name"`. **Данные только при запущенном контейнере vLLM** — если поднят только SGLang, метрик `vllm:*` в Prometheus нет, дашборд будет пустым (смотрите SGLang-дашборды). Если vLLM запущен, а **Model** пуст — сделайте запросы к API или выберите **All** / нужную модель и обновите переменные.

### vLLM V2: все панели «No data» (и Success Rate, и Latency)

Дашборд [vllmdash2.json](grafana/templates/vllmdash2.json) читает **только** серии `vllm:…` с **job="vllm"** и (через переменные) `instance=~…`, `model_name=~…`. **Пусто на всей странице** значит, что в **Prometheus** сейчас **нет** подходящих рядов — Grafana при этом настроен корректно.

| Проверка | Что должно быть |
|----------|-----------------|
| **1. Поднят движок vLLM** | Слот vLLM в **Develonica.LLM** (порт **8111** по умолчанию). Только SGLang → на **8111** ничего не слушает, скрейп **host.docker.internal:8111** → **DOWN** → **0** рядов `vllm:*`. Откройте SGLang-дашборды, не vLLM V2. |
| **2. Target vLLM в UP** | **Prometheus** → **Status → Targets** → job **`vllm`**, URL вроде **`http://host.docker.internal:8111/metrics`** → **State: UP** (после `git pull` и **рестарт из UI**). Старый экран **lookup vllm** — смена в [`prometheus/prometheus.yml`](prometheus/prometheus.yml). Если **DOWN** — vLLM не слушает на хосте (не тот `LLM_API_PORT`, контейнер остановлен) или `host.docker.internal` не резолвится (проверьте `extra_hosts` у `prometheus` в compose). |
| **3. Эндпоинт /metrics** | С хоста: `curl -sS "http://127.0.0.1:${LLM_API_PORT:-8111}/metrics" \| head -n 40` (для vLLM наружу по умолчанию **8111**). Должны быть строки вида **`vllm:request_success_total`**, **`vllm:num_requests_running`**. Если **HTTP 200, но `vllm:` почти нет** (или другие имена) — возможна **движок v1** / смена имён в вашей версии образа. **Explore** в Prometheus: `{__name__=~"vllm:.*"}` — пусто при «живом» API значит, дашборд V2 **не** совпадает с версией vLLM. |
| **4. Обход: `VLLM_USE_V1=0`**| В карточке пресета задайте **`VLLM_USE_V1=0`**, **пересоздайте слот** vLLM из UI и снова проверьте `/metrics` (см. п.3). Подбор под **Grafana V2** и старые имена; на новых vLLM движок v0 могут **убрать** — тогда смотрите **Explore** и подстраивайте PromQL/импорт другого дашборда под ваш `/metrics`. Ссылка: [vLLM #16348](https://github.com/vllm-project/vllm/issues/16348) (обсуждение метрик v1). |
| **5. Диапазон времени** | **Last 3h** пуст, если **не было трафика** — часть **stat** всё равно может показать 0, но **rate(...[5m])** остаётся пустой до первых запросов. Минимум: один `chat/completions`, подождать 1–2 окна скрейпа (15s). |

**Переменные дашборда:** **Instance** в рядах — **`vllm:8111`** (relabel в Prometheus), не `host.docker.internal:8111`. Если **Targets** **UP**, но **instance** в Grafana пуст — обновите страницу, **All** (в JSON `includeAll` + `allValue: ".*"`).

4. **SGLang (два варианта в provisioning)** — JSON в [`grafana/provisioning/dashboards/json/`](grafana/provisioning/dashboards/json/); подхватываются при **`подъём стека из UI («Мониторинг»)`** / `docker compose -f docker/docker-compose.monitoring.yml up -d grafana` (из **корня** репозитория) (datasource **uid `prometheus`**, метрики **`sglang:…`**, **`instance`** / **`model_name`**, `job="sglang"`):
   - [**`sglang-dashboard-slgpu.json`**](grafana/provisioning/dashboards/json/sglang-dashboard-slgpu.json) — сокращённая адаптация [официального SGLang Dashboard](https://github.com/sgl-project/sglang/blob/main/examples/monitoring/grafana/dashboards/json/sglang-dashboard.json) (лагенси, p50/p90/p99, очереди, throughput, cache hit).
   - [**`sglangdash2-slgpu.json`**](grafana/provisioning/dashboards/json/sglangdash2-slgpu.json) — **расширенный** обзор в духе vLLM «V2» (верхние stat/gauge, E2E/TTFT, токены, очередь, KV/token usage, pie aborted/non-aborted). Собран из `vllmdash2` скриптом [`_build_sglangdash2.py`](grafana/provisioning/dashboards/json/_build_sglangdash2.py) при смене исходника vLLM. Прямого соответствия метрик vLLM нет (например `finished_reason` в Prometheus SGLang нет — срезы через aborted/requests). Гистограмма длины промпта — `sglang:prompt_tokens_histogram_bucket` (нужны включённые у сервера гистограммы длин; иначе панель пустая).

   Если в образе префиксы метрик **`sglang_`** без двоеточия — правьте выражения в JSON или импортируйте апстрим-дашборд и укажите datasource вручную.

### SGLang: красный треугольник, «No data», пустой model name

Одинаково для **`sglang-dashboard-slgpu`** и **`sglangdash2-slgpu`**: переменные **`instance`** и **`model_name`** вверху дашборда.

Переменная **`instance`** в дашборде — это метка, попадающая в ряды (после relabel: **`sglang:8222`**, тот же **instance**, что в запросах к Prometheus).

| Конфигурация | В Grafana **instance** |
|--------------|-------------------------|
| Текущий [`prometheus/prometheus.yml`](prometheus/prometheus.yml): скрейп `host.docker.internal:8222`, relabel `instance=sglang:8222` | **`sglang:8222`** |
| Меняли порт SGLang на хосте (`LLM_API_PORT`) — обновите `targets` в `prometheus/prometheus.yml` | Иначе target **DOWN**; instance по-прежнему **`sglang:8222`** в метках (если relabel не трогали) |

Если выбрать **`sglang:8111`**, а Prometheus уже скрейпит **`:8222`**, в выборке **нет** метрик с нужным `instance` → **пустые панели** и **ошибка/предупреждение** на панелях.

**Что сделать:** **Dashboards** → открыть нужный SGLang-дашборд → вверху **instance** переключить на **`sglang:8222`** (или тот, что виден в **Prometheus → Status → Targets** для job `sglang`, **State: UP**). Кнопка **Refresh** у переменных, при необходимости обновить страницу.

**`Model` / model name** — панели в [`sglangdash2-slgpu.json`](grafana/provisioning/dashboards/json/sglangdash2-slgpu.json) фильтруют по `model_name=~"$model_name"`. Пустой **Model** (ничего не выбрано) **не** совпадает с реальным лейблом в Prometheus → **No data** (это не «пропажа» данных: метрики в **Prometheus**; в Grafana — только дашборд). **По умолчанию** в дашбордах включён **All** (регулярка `.*`), либо выберите конкретную модель в дропдауне. (1) неверный **instance**; (2) ещё **не было запросов** к API — сделайте `chat/completions`, обновите переменные; (3) другой `model_name` в метриках — **Explore:** `sglang:generation_tokens_total{job="sglang"}`.

**Проверки:** `--enable-metrics` (в slgpu по умолчанию); `curl -s 127.0.0.1:<хост_порт>/metrics | head` с хоста — должны быть строки с префиксом, характерным для SGLang.

### Node Exporter Full «не работает» / пустые графики

1. **Цель Prometheus в состоянии UP.** Откройте `http://<хост>:9090/targets` (локально часто `127.0.0.1`, снаружи — IP сервера при `PROMETHEUS_BIND=0.0.0.0`). Строка **`node-exporter`** должна быть **UP**. Если **DOWN** — не поднят стек (`подъём стека из UI («Мониторинг»)`), сеть `slgpu` не общая, или порт `9100` недоступен.
2. **Метрики реально есть.** В Prometheus → **Graph**: запрос `up{job="node-exporter"}` должен вернуть **1**. Если пусто — скрейп не доходит до дашборда Grafana.
3. **Переменные дашборда.** У импортированного **1860** вверху страницы выберите **job = `node-exporter`** и подходящий **instance** (в этом репозитории по умолчанию **`host`**). Если оставить другой job (например случайно `prometheus`), почти все панели будут пустыми.
4. **Datasource при импорте.** При импорте укажите **Prometheus** (в provisioning он уже есть, uid **`prometheus`**). Если выбрать «не тот» источник или отключённый — данных не будет.
5. **Время на графике.** Установите диапазон **Last 15 minutes** (или больше), если только что подняли стек.
6. **Версия дашборда.** На grafana.com у **1860** несколько ревизий; при полном «No data» попробуйте импортировать **последнюю ревизию** или дропдаун **job** переключите на все доступные значения по очереди.

После смены [`prometheus/prometheus.yml`](prometheus/prometheus.yml) перезагрузите конфиг (см. ниже) или `docker compose -f docker/docker-compose.monitoring.yml up -d prometheus` (из **корня** репо).

## Перезагрузка конфигурации Prometheus

После правки `prometheus/prometheus.yml`:

```bash
curl -X POST "http://127.0.0.1:9090/-/reload"
```

(с той же машины, где слушает Prometheus; с другой хоста — подставьте IP и убедитесь, что порт 9090 открыт)

(в compose включён `--web.enable-lifecycle`).

## Данные на локальном диске (не в томе Docker)

Пути в [`main.env`](../../main.env): **`PROMETHEUS_DATA_DIR`**, **`GRAFANA_DATA_DIR`**, **`LOKI_DATA_DIR`**, **`PROMTAIL_DATA_DIR`**, а для **Langfuse** (Postgres, ClickHouse, логи ClickHouse, MinIO, Redis) — **`LANGFUSE_POSTGRES_DATA_DIR`**, **`LANGFUSE_CLICKHOUSE_DATA_DIR`**, **`LANGFUSE_CLICKHOUSE_LOGS_DIR`**, **`LANGFUSE_MINIO_DATA_DIR`**, **`LANGFUSE_REDIS_DATA_DIR`** (по умолчанию подкаталоги **`data/monitoring/...`** в корне репо — см. `data/README.md`, не named volumes Docker). С bind mount каталоги на **хосте** должны принадлежать **тому же uid:gid, под которым процесс внутри образа** (иначе `GF_PATHS_DATA not writable`, `plugins: Permission denied`, panics Prometheus, Postgres «data directory has wrong ownership»). Теги **`latest` меняют** предположения — не полагайтесь только на «472:0 в документации».

### Рекомендуется: автоматически по образам

```text
# UI «Стек мониторинга» → «Чинить права» (job native.monitoring.fix-perms), затем подъём стека из UI
```

Backend job **`native.monitoring.fix-perms`** ([`web/backend/app/services/native_jobs.py`](../../web/backend/app/services/native_jobs.py) → `_native_fix_perms`) читает uid/gid из образов Grafana, Prometheus, Loki, Postgres, MinIO, Redis и берёт фиксированные **101:101** для ClickHouse; затем делает **`mkdir -p`** и **`chown -R`** на все перечисленные каталоги. Образы — `GRAFANA_IMAGE`, `PROMETHEUS_IMAGE`, … в БД (см. UI «Настройки»). `mkdir`/`chown` выполняются через короткоживущий root-helper контейнер `docker run --rm -u 0:0` с образом из переменной **`SLGPU_BENCH_CHOWN_IMAGE`** (по умолчанию `alpine:latest`); работает и от обычного пользователя на хосте, и из web-контейнера через `docker.sock`. **`sudo` не требуется.**

**Вручную:** см. [оф. Grafana (docker)](https://grafana.com/docs/grafana/latest/setup-grafana/installation/docker/) и проверяйте `docker run --rm --entrypoint sh grafana/grafana -c 'id'`.

```bash
# Пример путей по умолчанию в main.env (от корня клона); uid — см. fix-perms / образ
sudo mkdir -p ./data/monitoring/prometheus ./data/monitoring/grafana
sudo chown -R 65534:65534 ./data/monitoring/prometheus
sudo chown -R 472:0 ./data/monitoring/grafana
# далее — подъём стека из UI («Мониторинг»)
```

### `GF_PATHS_DATA` not writable / `mkdir .../plugins: Permission denied`

1. **`действие fix-perms из UI («Мониторинг»)`**
2. **рестарт из UI**

### `queries.active` / `permission denied` / panic `Unable to create mmap-ed active query log`

1. **`действие fix-perms из UI («Мониторинг»)`**
2. **рестарт из UI**

### MinIO: `FATAL ... decodeXLHeaders: Unknown xl meta version 3` (цикл restart)

**Смысл:** в каталоге **`LANGFUSE_MINIO_DATA_DIR`** лежат метаданные в формате, который **текущий** бинарник MinIO **не умеет читать**. Типично: данные записала **более новая** версия (например, когда-то тянули `minio/minio:latest` или другой тег), а в compose сейчас зашит **более старый** образ — откат сервера MinIO на «старые» данные **не поддерживается** (см. обсуждения upstream: `Unknown xl meta version`).

**Что сделать:**

1. **Обновить образ** до версии **не ниже** той, на которой создавались данные, или до актуального дефолта в репо (`MINIO_IMAGE` / `SLGPU_MINIO_IMAGE` в `main.env` и в stack web). Затем: **`docker pull`** нужного тега, **`native.proxy.up`** из UI (**LiteLLM Proxy**) или рестарт прокси.
2. **Если S3 в MinIO — только вспомогательное хранилище для Langfuse** и потеря объектов не критична: остановите **прокси-стек**, очистить **`LANGFUSE_MINIO_DATA_DIR`** на диске (содержимое каталога), при необходимости удалить маркер **`data/monitoring/.bootstrap/minio-bucket-init.done`**, снова **`native.proxy.up`** (bootstrap пересоздаст бакеты). Langfuse/Postgres/ClickHouse при этом **не** трогаем, если не переустанавливаете весь стек.

**Порты (GRAFANA_PORT, MinIO_*, …) с настройками web не конфликтуют** — ошибка идёт от **несоответствия бинарник ↔ формат диска**, а не от смены портов.

### Redis (Langfuse): `Can't handle RDB format version` / «Fatal error loading the DB» (цикл restart)

**Смысл:** в **`LANGFUSE_REDIS_DATA_DIR`** лежит **`dump.rdb`** (и/или AOF), записанный **более новым** Redis, чем тот, что сейчас в контейнере. Сообщение вроде **`Can't handle RDB format version 12`** означает, что формат дампа **новее**, чем у бинарника **7.2.x** — такой файл пишет, как правило, **Redis 8+**; образ **`redis:7.2-*`** его **не** открывает.

**Что сделать:**

1. **Совместимость (сохранить данные):** в [`main.env`](../../main.env) и в **Настройки** web задайте **`LANGFUSE_REDIS_IMAGE`** не ниже версии, на которой создавался дамп (в репозитории по умолчанию с **5.2.9** — **`redis:8-alpine`**). Выполните **`docker pull`** нужного тега, затем пересоздайте контейнер **`redis`** (рестарт стека прокси из UI или `docker compose … up -d --force-recreate redis`). После этого Redis прочитает существующий RDB, если мажор/minor образа **не старее** того, кто писал файл.
2. **Пустой Redis допустим (потеря кэша/очередей в Redis):** остановите стек, сделайте **бэкап** каталога **`LANGFUSE_REDIS_DATA_DIR`**, удалите **`dump.rdb`** (и при включённом AOF — файлы **`appendonly.aof`***), снова поднимите стек. Langfuse заново наполнит Redis.

**Предупреждение в логах про `Memory overcommit must be enabled` / `vm.overcommit_memory`:** на **Linux-хосте** (не внутри контейнера) включите overcommit, иначе Redis предупреждает о рисках при RDB/replication. Пример: **`sudo sysctl -w vm.overcommit_memory=1`** и постоянная запись в **`/etc/sysctl.d/*.conf`** с **`vm.overcommit_memory = 1`**, затем перезагрузка или повторное применение sysctl.

**Перенос Langfuse с named volumes** (старые версии compose: `slgpu_lf_postgres_data`, `slgpu_lf_clickhouse_data`, …):

1. **остановка стека из UI**
2. Для каждого тома: `docker volume inspect <имя>` → поле **`Mountpoint`**, внутри **`_data/`** (у Postgres — содержимое `PG_VERSION` и т.д.)
3. Создать каталоги из `main.env` (`LANGFUSE_*_DATA_DIR`), **остановленные** данные скопировать:  
   `sudo rsync -a <mountpoint>/_data/ "${LANGFUSE_POSTGRES_DATA_DIR}/"` (и аналогично для clickhouse, minio, redis — смотрите точку монтирования в старом compose).
4. **`действие fix-perms из UI («Мониторинг»)`** → **`подъём стека из UI («Мониторинг»)`**
5. После проверки: `docker volume rm` старые `slgpu_lf_*` (только если данные на диске работают).

**Перенос из старых named volumes** (`slgpu_prometheus-data`, `slgpu_grafana-data` — до смены на bind):

1. Остановить стек: **остановка стека из UI**.
2. Узнать путь данных Docker: `docker volume inspect slgpu_prometheus-data` / `slgpu_grafana-data` (поле **`Mountpoint`**, внутри — подкаталог **`_data/`**).
3. Создать хостовые каталоги и **скопировать** (с сохранением прав, от root):  
   `sudo rsync -a /var/lib/docker/volumes/slgpu_prometheus-data/_data/ "${PROMETHEUS_DATA_DIR}/"`  
   `sudo rsync -a /var/lib/docker/volumes/slgpu_grafana-data/_data/ "${GRAFANA_DATA_DIR}/"`
4. **Обязательно** выставить владельца: **`действие fix-perms из UI («Мониторинг»)`** (после `rsync` данные с тома — от `root`, скрипт выставит uid:gid по образам).
5. Поднять: **`подъём стека из UI («Мониторинг»)`**. Старые тома, если больше не нужны, удаляйте только после проверки: `docker volume rm slgpu_prometheus-data slgpu_grafana-data`.

**SELinux (RHEL и др.):** если контейнер не видит файлы, для bind mount в compose иногда добавляют суффикс **`:Z`** (или `:z`) к путям; см. документацию Docker/SELinux.

## Сеть `slgpu`: «incorrect label com.docker.compose.network»

Если **`docker compose`** (LLM-слот) или **`подъём стека из UI («Мониторинг»)`** падает с сообщением, что сеть `slgpu` уже есть, но метка `com.docker.compose.network` пустая или не та, значит сеть когда‑то создана **вручную** (`docker network create slgpu`) **до** исправления в репо: Compose v2 ждёт метки `com.docker.compose.project=slgpu` и `com.docker.compose.network=slgpu`.

**Починка:** остановить стеки, удалить сеть, поднять снова (сеть пересоздастся с метками):

```bash
cd /opt/slgpu   # корень клона
docker compose -f docker/docker-compose.monitoring.yml down
docker compose -f docker/docker-compose.llm.yml down
docker network rm slgpu
# Далее поднимите LLM-слот из Develonica.LLM и при необходимости стек «Мониторинг» из UI
```

(Если `docker network rm` ругается на «active endpoints» — сначала `docker compose down` для всех проектов, использующих эту сеть, либо остановите контейнеры вручную.)

## Диск заполнился: `no space left on device` / ошибки WAL Prometheus

Сообщения вида `write /prometheus/wal/...: no space left on device` значат, что **на хосте или в разделе Docker закончилось свободное место**. Prometheus не может писать WAL и TSDB — скрейпы и правила падают.

**Что сделать на сервере:**

1. Посмотреть место: `df -h`, `docker system df` (образы, build cache, тома).
2. Освободить диск: удалить неиспользуемые образы/кэш (`docker system prune` — осторожно), почистить логи, перенести модели/данные на другой раздел.
3. Ограничить рост TSDB в [`main.env`](../../main.env): сократить **`PROMETHEUS_RETENTION_TIME`** (по репозиторию по умолчанию **100y** — практически без срока; раньше было 15d) и/или задать ненулевой **`PROMETHEUS_RETENTION_SIZE`** (например `20GB`). **`PROMETHEUS_RETENTION_SIZE=0`** — без лимита по размеру (только по времени). Перезапустить: рестарт из UI или `docker compose -f docker/docker-compose.monitoring.yml up -d prometheus` (из **корня** репо).

TSDB и WAL лежат в каталоге **`PROMETHEUS_DATA_DIR`** на хосте (см. [выше](#данные-на-локальном-диске-не-в-томе-docker)).

## Сообщения в логах Grafana (часто безвредны)

| Сообщение | Смысл |
|-----------|--------|
| `migrations completed` / `Created default admin` | Первый запуск: встроенная SQLite создала БД и пользователя `admin` — норма. |
| `plugin xychart is already registered` | Известная коллизия встроенного и подгружаемого плагина в части сборок Grafana; дашборды обычно работают. |
| `Failed to read plugin provisioning ... plugins` / `alerting` | Раньше не было пустых каталогов в `provisioning/` — в репозитории добавлены `plugins/` и `alerting/`, после `git pull` и пересоздания контейнера строки пропадают. |
| `Database locked, sleeping then retrying` | SQLite под нагрузкой; Grafana ретраит. Если повторяется часто — для продакшена лучше вынести БД Grafana в PostgreSQL. |
