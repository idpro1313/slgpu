# Мониторинг

**Логи всех контейнеров в одно место (journald, Loki, syslog):** см. [LOGS.md](LOGS.md). В стеке мониторинга уже подняты **Grafana Loki** + **Promtail** (данные на диске: `LOKI_DATA_DIR`, `PROMTAIL_DATA_DIR` в `main.env`); просмотр в **Grafana → Explore → Loki**.

**Langfuse** (трейсинг LLM) и **LiteLLM Proxy** (единая OpenAI-совместимая точка входа к **vLLM** на хосте) поднимаются тем же compose: отдельная внутренняя сеть для Postgres / ClickHouse / Redis / MinIO, плюс **`slgpu`** для Langfuse UI, воркера и LiteLLM. UI Langfuse по умолчанию **`:3001`** (`LANGFUSE_PORT`), чтобы не конфликтовать с Grafana **:3000**. MinIO наружу: **`:9010`** / **`:9011`** (`MINIO_*_HOST_PORT`), не **:9090** (Prometheus). Секреты (`NEXTAUTH_SECRET`, `LANGFUSE_ENCRYPTION_KEY`, пароли БД) — в [`main.env`](../main.env); для продакшена смените дефолты. **LiteLLM:** конфиг в репо — [`config.yaml`](../monitoring/litellm/config.yaml) (после `git pull` готов к запуску; порт `__LLM_API_PORT__` подставляется из `LLM_API_PORT` в entrypoint). Клиент: `http://<хост>:LITELLM_PORT/v1/…`, **`"model": "devllm"`**; **`x-api-key`** — если в [`main.env`](../main.env) задан ненулевой **`LITELLM_MASTER_KEY`** (пусто = без ключа, только в закрытой сети). Смена имени/роутов — правка `config.yaml` и `monitoring up`. Трейсинг в Langfuse: в UI — проект → API keys; ключи для LiteLLM — в **[`configs/secrets/langfuse-litellm.env`](../configs/secrets/langfuse-litellm.env.example)** (копия из `*.example`, файл в `.gitignore`), не в `main.env`. При первом `./slgpu monitoring up` пустой файл создаётся из примера. В [`monitoring/litellm/config.yaml`](../monitoring/litellm/config.yaml) задано **`success_callback: ["langfuse"]`**. **`LANGFUSE_HOST`** в compose: `http://langfuse-web:3000` (сеть `slgpu`).

## Доступ к Langfuse извне (интернет / другая сеть)

1. **`NEXTAUTH_URL`** в [`main.env`](../main.env) — **обязан** совпадать с тем URL, по которому вы открываете UI: схема + хост + порт. Для `127.0.0.1` вход с другой машины **не** заработает. Примеры: `https://langfuse.yourdomain.com` (лучше за reverse proxy), `http://203.0.113.7:3001` (тест по IP), после смены — **`./slgpu monitoring restart`**.
2. **Прослушивание:** в репо задано **`LANGFUSE_BIND=0.0.0.0`** — порт `LANGFUSE_PORT` (по умолч. 3001) слушается на всех интерфейсах. Чтобы **не** светить наружу, поставьте `LANGFUSE_BIND=127.0.0.1` и публикуйте Langfuse **только** через Nginx/Traefik на 443. **`curl` / браузер: connection reset** к `:3001` с хоста: для сервиса `langfuse-web` в [`docker-compose.monitoring.yml`](../docker-compose.monitoring.yml) задано **`HOSTNAME=0.0.0.0`**, иначе Next.js может слушать не все интерфейсы в контейнере (см. [FAQ Langfuse](https://langfuse.com/faq/all/debug-docker-deployment)); после обновления репо пересоздайте контейнер: `docker compose -f docker-compose.monitoring.yml --env-file main.env up -d --force-recreate langfuse-web`.
3. **Фаервол / security group** — откройте только нужный порт (или 80/443 у прокси), остальные сервисы мониторинга (Prometheus, MinIO) по возможности **не** публикуйте в интернет.
4. **Секреты** — смените `NEXTAUTH_SECRET`, `LANGFUSE_ENCRYPTION_KEY`, пароли БД/Redis/MinIO/Postgres в проде.
5. **SDK** (приложения на других хостах): base URL = тот же публичный хост, что в `NEXTAUTH_URL` (часто `https://...` без пути, см. [док. Langfuse](https://langfuse.com/docs) по клиенту).

**После регистрации редирект на `http://127.0.0.1:3001`:** в [`main.env`](../main.env) задан непубличный `NEXTAUTH_URL`. Исправьте на тот URL, с которого открываете UI (например `http://<ваш-IP>:3001`), **без** слэша в конце, затем `docker compose -f docker-compose.monitoring.yml --env-file main.env up -d` или `./slgpu monitoring restart`, очистите cookies для сайта и снова зайдите.

Сервисы: [`docker-compose.monitoring.yml`](../docker-compose.monitoring.yml) (подъём: **`../slgpu monitoring up`**, **не** в `./slgpu up`). Сеть **`slgpu`** общая с [`docker-compose.yml`](../docker-compose.yml) для **dcgm / node-exporter** и контейнеров в одной сети. **vLLM и SGLang** в [`prometheus.yml`](prometheus.yml) скрейпятся **не** по имени `vllm:8111` (между проектами `slgpu` и `slgpu-monitoring` внутренний DNS краткого имени `vllm` часто даёт *lookup vllm … server misbehaving*), а через **`host.docker.internal:<порт_на_хосте>`** (мост в хост, где опубликованы `LLM_API_PORT` → 8111 / 8222). У сервиса `prometheus` в compose задано `extra_hosts: host.docker.internal:host-gateway` (Linux). Метка **`instance`** для рядов — **`vllm:8111`** / **`sglang:8222`** (Grafana, переменные).

- **Prometheus** (по умолч. **`0.0.0.0:9090`** на хосте, см. `PROMETHEUS_BIND` в [`main.env`](../main.env)): UI и HTTP API **без аутентификации** — в проде закройте фаерволом или поставьте `PROMETHEUS_BIND=127.0.0.1` и ходите по SSH tunnel. Скрейп vLLM/SGLang: **см. выше**; плюс `dcgm-exporter:9400`, **`node-exporter:9100`**. **Нестандартный `LLM_API_PORT`:** поправьте **хостовый** порт в `targets` в [`prometheus.yml`](prometheus.yml) (должен совпадать с левой частью `ports` в `docker-compose.yml` для выбранного движка).
  - **SGLang:** для наполнения оф. Grafana «SGLang Dashboard» сервер должен запускаться с **`--enable-metrics`** (в slgpu: по умолчанию через `SGLANG_ENABLE_METRICS=1` в `serve.sh`). Иначе панели по `sglang:*` часто пустые.
  - Когда контейнер vLLM или SGLang **не поднят** (другой профиль compose) — на хосте **нет** слушателя на 8111/8222, target будет **DOWN**. Это ожидаемо для A/B; смотрите метрики активного движка.
- **Grafana** (`127.0.0.1:3000`): datasource Prometheus подключён автоматически.
- **Алерты**: [prometheus-alerts.yml](prometheus-alerts.yml) (пороги при необходимости ослабьте, если метрики в вашей версии vLLM называются иначе).

## Рекомендуемые дашборды (импорт в UI Grafana)

1. **NVIDIA DCGM** — dashboard ID [12239](https://grafana.com/grafana/dashboards/12239).
2. **Node Exporter Full** (хост: CPU, RAM, диск, сеть) — dashboard ID [**1860**](https://grafana.com/grafana/dashboards/1860).  
   - **Dashboards → Import →** вставьте `1860` → Load.  
   - Datasource: **Prometheus** (как в provisioning, uid `prometheus`).  
   - Убедитесь, что контейнер **`node-exporter`** запущен: **`./slgpu monitoring up`** (или `docker compose -f docker-compose.monitoring.yml up -d node-exporter`).  
   - В выпадающих списках вверху дашборда выберите **Datasource: Prometheus**, **job = `node-exporter`**, **instance** — обычно **`host`** (так задан label в [`prometheus.yml`](prometheus.yml)); в других ревизиях дашборда может быть `node-exporter:9100`.
3. **vLLM** — поиск на grafana.com по `vllm` (ID зависят от версии; импорт через **Dashboards → Import**). В репозитории: [`vllmdash2.json`](grafana/provisioning/dashboards/json/vllmdash2.json) — **V2**; datasource **`prometheus`**, переменные **`instance`** / **`Model`** (с **All**), в запросах `job="vllm"`, `model_name=~"$model_name"`. **Данные только при запущенном контейнере vLLM** — если поднят только SGLang, метрик `vllm:*` в Prometheus нет, дашборд будет пустым (смотрите SGLang-дашборды). Если vLLM запущен, а **Model** пуст — сделайте запросы к API или выберите **All** / нужную модель и обновите переменные.

### vLLM V2: все панели «No data» (и Success Rate, и Latency)

Дашборд [vllmdash2.json](grafana/provisioning/dashboards/json/vllmdash2.json) читает **только** серии `vllm:…` с **job="vllm"** и (через переменные) `instance=~…`, `model_name=~…`. **Пусто на всей странице** значит, что в **Prometheus** сейчас **нет** подходящих рядов — Grafana при этом настроен корректно.

| Проверка | Что должно быть |
|----------|-----------------|
| **1. Поднят движок vLLM** | `./slgpu up vllm -m <пресет>` (профиль **vllm**). Только SGLang → на **8111** ничего не слушает, скрейп **host.docker.internal:8111** → **DOWN** → **0** рядов `vllm:*`. Откройте SGLang-дашборды, не vLLM V2. |
| **2. Target vLLM в UP** | **Prometheus** → **Status → Targets** → job **`vllm`**, URL вроде **`http://host.docker.internal:8111/metrics`** → **State: UP** (после `git pull` и **`./slgpu monitoring restart`**). Старый экран **lookup vllm** — смена в [`prometheus.yml`](../prometheus.yml). Если **DOWN** — vLLM не слушает на хосте (не тот `LLM_API_PORT`, контейнер остановлен) или `host.docker.internal` не резолвится (проверьте `extra_hosts` у `prometheus` в compose). |
| **3. Эндпоинт /metrics** | С хоста: `curl -sS "http://127.0.0.1:${LLM_API_PORT:-8111}/metrics" \| head -n 40` (для vLLM наружу по умолчанию **8111**). Должны быть строки вида **`vllm:request_success_total`**, **`vllm:num_requests_running`**. Если **HTTP 200, но `vllm:` почти нет** (или другие имена) — возможна **движок v1** / смена имён в вашей версии образа. **Explore** в Prometheus: `{__name__=~"vllm:.*"}` — пусто при «живом» API значит, дашборд V2 **не** совпадает с версией vLLM. |
| **4. Обход: `VLLM_USE_V1=0`**| В [main.env](../main.env) раскомментируйте **`VLLM_USE_V1=0`**, пересоздайте vLLM (`./slgpu down` / `up` или `restart`) и снова проверьте `/metrics` (см. п.3). Подбор под **Grafana V2** и старые имена; на новых vLLM движок v0 могут **убрать** — тогда смотрите **Explore** и подстраивайте PromQL/импорт другого дашборда под ваш `/metrics`. Ссылка: [vLLM #16348](https://github.com/vllm-project/vllm/issues/16348) (обсуждение метрик v1). |
| **5. Диапазон времени** | **Last 3h** пуст, если **не было трафика** — часть **stat** всё равно может показать 0, но **rate(...[5m])** остаётся пустой до первых запросов. Минимум: один `chat/completions`, подождать 1–2 окна скрейпа (15s). |

**Переменные дашборда:** **Instance** в рядах — **`vllm:8111`** (relabel в Prometheus), не `host.docker.internal:8111`. Если **Targets** **UP**, но **instance** в Grafana пуст — обновите страницу, **All** (в JSON `includeAll` + `allValue: ".*"`).

4. **SGLang (два варианта в provisioning)** — JSON в [`grafana/provisioning/dashboards/json/`](grafana/provisioning/dashboards/json/); подхватываются при **`./slgpu monitoring up`** / `docker compose -f ../docker-compose.monitoring.yml up -d grafana` (datasource **uid `prometheus`**, метрики **`sglang:…`**, **`instance`** / **`model_name`**, `job="sglang"`):
   - [**`sglang-dashboard-slgpu.json`**](grafana/provisioning/dashboards/json/sglang-dashboard-slgpu.json) — сокращённая адаптация [официального SGLang Dashboard](https://github.com/sgl-project/sglang/blob/main/examples/monitoring/grafana/dashboards/json/sglang-dashboard.json) (лагенси, p50/p90/p99, очереди, throughput, cache hit).
   - [**`sglangdash2-slgpu.json`**](grafana/provisioning/dashboards/json/sglangdash2-slgpu.json) — **расширенный** обзор в духе vLLM «V2» (верхние stat/gauge, E2E/TTFT, токены, очередь, KV/token usage, pie aborted/non-aborted). Собран из `vllmdash2` скриптом [`_build_sglangdash2.py`](grafana/provisioning/dashboards/json/_build_sglangdash2.py) при смене исходника vLLM. Прямого соответствия метрик vLLM нет (например `finished_reason` в Prometheus SGLang нет — срезы через aborted/requests). Гистограмма длины промпта — `sglang:prompt_tokens_histogram_bucket` (нужны включённые у сервера гистограммы длин; иначе панель пустая).

   Если в образе префиксы метрик **`sglang_`** без двоеточия — правьте выражения в JSON или импортируйте апстрим-дашборд и укажите datasource вручную.

### SGLang: красный треугольник, «No data», пустой model name

Одинаково для **`sglang-dashboard-slgpu`** и **`sglangdash2-slgpu`**: переменные **`instance`** и **`model_name`** вверху дашборда.

Переменная **`instance`** в дашборде — это метка, попадающая в ряды (после relabel: **`sglang:8222`**, тот же **instance**, что в запросах к Prometheus).

| Конфигурация | В Grafana **instance** |
|--------------|-------------------------|
| Текущий [`prometheus.yml`](prometheus.yml): скрейп `host.docker.internal:8222`, relabel `instance=sglang:8222` | **`sglang:8222`** |
| Меняли порт SGLang на хосте (`LLM_API_PORT`) — обновите `targets` в `prometheus.yml` | Иначе target **DOWN**; instance по-прежнему **`sglang:8222`** в метках (если relabel не трогали) |

Если выбрать **`sglang:8111`**, а Prometheus уже скрейпит **`:8222`**, в выборке **нет** метрик с нужным `instance` → **пустые панели** и **ошибка/предупреждение** на панелях.

**Что сделать:** **Dashboards** → открыть нужный SGLang-дашборд → вверху **instance** переключить на **`sglang:8222`** (или тот, что виден в **Prometheus → Status → Targets** для job `sglang`, **State: UP**). Кнопка **Refresh** у переменных, при необходимости обновить страницу.

**`Model` / model name** — панели в [`sglangdash2-slgpu.json`](grafana/provisioning/dashboards/json/sglangdash2-slgpu.json) фильтруют по `model_name=~"$model_name"`. Пустой **Model** (ничего не выбрано) **не** совпадает с реальным лейблом в Prometheus → **No data** (это не «пропажа» данных: метрики в **Prometheus**; в Grafana — только дашборд). **По умолчанию** в дашбордах включён **All** (регулярка `.*`), либо выберите конкретную модель в дропдауне. (1) неверный **instance**; (2) ещё **не было запросов** к API — сделайте `chat/completions`, обновите переменные; (3) другой `model_name` в метриках — **Explore:** `sglang:generation_tokens_total{job="sglang"}`.

**Проверки:** `--enable-metrics` (в slgpu по умолчанию); `curl -s 127.0.0.1:<хост_порт>/metrics | head` с хоста — должны быть строки с префиксом, характерным для SGLang.

### Node Exporter Full «не работает» / пустые графики

1. **Цель Prometheus в состоянии UP.** Откройте `http://<хост>:9090/targets` (локально часто `127.0.0.1`, снаружи — IP сервера при `PROMETHEUS_BIND=0.0.0.0`). Строка **`node-exporter`** должна быть **UP**. Если **DOWN** — не поднят стек (`./slgpu monitoring up`), сеть `slgpu` не общая, или порт `9100` недоступен.
2. **Метрики реально есть.** В Prometheus → **Graph**: запрос `up{job="node-exporter"}` должен вернуть **1**. Если пусто — скрейп не доходит до дашборда Grafana.
3. **Переменные дашборда.** У импортированного **1860** вверху страницы выберите **job = `node-exporter`** и подходящий **instance** (в этом репозитории по умолчанию **`host`**). Если оставить другой job (например случайно `prometheus`), почти все панели будут пустыми.
4. **Datasource при импорте.** При импорте укажите **Prometheus** (в provisioning он уже есть, uid **`prometheus`**). Если выбрать «не тот» источник или отключённый — данных не будет.
5. **Время на графике.** Установите диапазон **Last 15 minutes** (или больше), если только что подняли стек.
6. **Версия дашборда.** На grafana.com у **1860** несколько ревизий; при полном «No data» попробуйте импортировать **последнюю ревизию** или дропдаун **job** переключите на все доступные значения по очереди.

После смены [`prometheus.yml`](prometheus.yml) перезагрузите конфиг (см. ниже) или `docker compose -f ../docker-compose.monitoring.yml up -d prometheus`.

## Перезагрузка конфигурации Prometheus

После правки `prometheus.yml`:

```bash
curl -X POST "http://127.0.0.1:9090/-/reload"
```

(с той же машины, где слушает Prometheus; с другой хоста — подставьте IP и убедитесь, что порт 9090 открыт)

(в compose включён `--web.enable-lifecycle`).

## Данные на локальном диске (не в томе Docker)

Пути в [`main.env`](../main.env): **`PROMETHEUS_DATA_DIR`**, **`GRAFANA_DATA_DIR`**, **`LOKI_DATA_DIR`**, **`PROMTAIL_DATA_DIR`**, а для **Langfuse** (Postgres, ClickHouse, логи ClickHouse, MinIO, Redis) — **`LANGFUSE_POSTGRES_DATA_DIR`**, **`LANGFUSE_CLICKHOUSE_DATA_DIR`**, **`LANGFUSE_CLICKHOUSE_LOGS_DIR`**, **`LANGFUSE_MINIO_DATA_DIR`**, **`LANGFUSE_REDIS_DATA_DIR`** (по умолчанию подкаталоги **`/opt/mon/langfuse/...`** на хосте, не named volumes Docker). С bind mount каталоги на **хосте** должны принадлежать **тому же uid:gid, под которым процесс внутри образа** (иначе `GF_PATHS_DATA not writable`, `plugins: Permission denied`, panics Prometheus, Postgres «data directory has wrong ownership»). Теги **`latest` меняют** предположения — не полагайтесь только на «472:0 в документации».

### Рекомендуется: автоматически по образам

```bash
./slgpu monitoring fix-perms
./slgpu monitoring up
```

Скрипт [`scripts/monitoring_fix_permissions.sh`](../scripts/monitoring_fix_permissions.sh) читает uid/gid из образов Grafana, Prometheus, Loki, Postgres, MinIO, Redis и фиксированные **101:101** для ClickHouse; делает **`chown -R`** на все перечисленные каталоги. В [`main.env`](../main.env) при необходимости задайте **`SLGPU_*_IMAGE`** для совпадения с compose. Нужны **docker** и **sudo** (скрипт сам вызывает `sudo`, если не root).

**Вручную:** см. [оф. Grafana (docker)](https://grafana.com/docs/grafana/latest/setup-grafana/installation/docker/) и проверяйте `docker run --rm --entrypoint sh grafana/grafana -c 'id'`.

```bash
sudo mkdir -p /opt/mon/prometheus /opt/mon/grafana
# пример для типичного оф. образа; лучше fix-perms
sudo chown -R 65534:65534 /opt/mon/prometheus
sudo chown -R 472:0 /opt/mon/grafana
./slgpu monitoring up
```

### `GF_PATHS_DATA` not writable / `mkdir .../plugins: Permission denied`

1. **`./slgpu monitoring fix-perms`**
2. **`./slgpu monitoring restart`**

### `queries.active` / `permission denied` / panic `Unable to create mmap-ed active query log`

1. **`./slgpu monitoring fix-perms`**
2. **`./slgpu monitoring restart`**

**Перенос Langfuse с named volumes** (старые версии compose: `slgpu_lf_postgres_data`, `slgpu_lf_clickhouse_data`, …):

1. **`./slgpu monitoring down`**
2. Для каждого тома: `docker volume inspect <имя>` → поле **`Mountpoint`**, внутри **`_data/`** (у Postgres — содержимое `PG_VERSION` и т.д.)
3. Создать каталоги из `main.env` (`LANGFUSE_*_DATA_DIR`), **остановленные** данные скопировать:  
   `sudo rsync -a <mountpoint>/_data/ "${LANGFUSE_POSTGRES_DATA_DIR}/"` (и аналогично для clickhouse, minio, redis — смотрите точку монтирования в старом compose).
4. **`./slgpu monitoring fix-perms`** → **`./slgpu monitoring up`**
5. После проверки: `docker volume rm` старые `slgpu_lf_*` (только если данные на диске работают).

**Перенос из старых named volumes** (`slgpu_prometheus-data`, `slgpu_grafana-data` — до смены на bind):

1. Остановить стек: **`./slgpu monitoring down`**.
2. Узнать путь данных Docker: `docker volume inspect slgpu_prometheus-data` / `slgpu_grafana-data` (поле **`Mountpoint`**, внутри — подкаталог **`_data/`**).
3. Создать хостовые каталоги и **скопировать** (с сохранением прав, от root):  
   `sudo rsync -a /var/lib/docker/volumes/slgpu_prometheus-data/_data/ "${PROMETHEUS_DATA_DIR}/"`  
   `sudo rsync -a /var/lib/docker/volumes/slgpu_grafana-data/_data/ "${GRAFANA_DATA_DIR}/"`
4. **Обязательно** выставить владельца: **`./slgpu monitoring fix-perms`** (после `rsync` данные с тома — от `root`, скрипт выставит uid:gid по образам).
5. Поднять: **`./slgpu monitoring up`**. Старые тома, если больше не нужны, удаляйте только после проверки: `docker volume rm slgpu_prometheus-data slgpu_grafana-data`.

**SELinux (RHEL и др.):** если контейнер не видит файлы, для bind mount в compose иногда добавляют суффикс **`:Z`** (или `:z`) к путям; см. документацию Docker/SELinux.

## Сеть `slgpu`: «incorrect label com.docker.compose.network»

Если **`./slgpu up`** или **`./slgpu monitoring up`** падает с сообщением, что сеть `slgpu` уже есть, но метка `com.docker.compose.network` пустая или не та, значит сеть когда‑то создана **вручную** (`docker network create slgpu`) **до** исправления в репо: Compose v2 ждёт метки `com.docker.compose.project=slgpu` и `com.docker.compose.network=slgpu`.

**Починка:** остановить стеки, удалить сеть, поднять снова (сеть пересоздастся с метками):

```bash
cd /opt/slgpu   # корень клона
docker compose -f docker-compose.monitoring.yml down
docker compose -f docker-compose.yml down
docker network rm slgpu
./slgpu up vllm -m <пресет>   # или sglang; при необходимости затем: ./slgpu monitoring up
```

(Если `docker network rm` ругается на «active endpoints» — сначала `docker compose down` для всех проектов, использующих эту сеть, либо остановите контейнеры вручную.)

## Диск заполнился: `no space left on device` / ошибки WAL Prometheus

Сообщения вида `write /prometheus/wal/...: no space left on device` значат, что **на хосте или в разделе Docker закончилось свободное место**. Prometheus не может писать WAL и TSDB — скрейпы и правила падают.

**Что сделать на сервере:**

1. Посмотреть место: `df -h`, `docker system df` (образы, build cache, тома).
2. Освободить диск: удалить неиспользуемые образы/кэш (`docker system prune` — осторожно), почистить логи, перенести модели/данные на другой раздел.
3. Ограничить рост TSDB в [`main.env`](../main.env): сократить **`PROMETHEUS_RETENTION_TIME`** (по репозиторию по умолчанию **100y** — практически без срока; раньше было 15d) и/или задать ненулевой **`PROMETHEUS_RETENTION_SIZE`** (например `20GB`). **`PROMETHEUS_RETENTION_SIZE=0`** — без лимита по размеру (только по времени). Перезапустить: `./slgpu monitoring restart` или `docker compose -f ../docker-compose.monitoring.yml up -d prometheus`.

TSDB и WAL лежат в каталоге **`PROMETHEUS_DATA_DIR`** на хосте (см. [выше](#данные-на-локальном-диске-не-в-томе-docker)).

## Сообщения в логах Grafana (часто безвредны)

| Сообщение | Смысл |
|-----------|--------|
| `migrations completed` / `Created default admin` | Первый запуск: встроенная SQLite создала БД и пользователя `admin` — норма. |
| `plugin xychart is already registered` | Известная коллизия встроенного и подгружаемого плагина в части сборок Grafana; дашборды обычно работают. |
| `Failed to read plugin provisioning ... plugins` / `alerting` | Раньше не было пустых каталогов в `provisioning/` — в репозитории добавлены `plugins/` и `alerting/`, после `git pull` и пересоздания контейнера строки пропадают. |
| `Database locked, sleeping then retrying` | SQLite под нагрузкой; Grafana ретраит. Если повторяется часто — для продакшена лучше вынести БД Grafana в PostgreSQL. |
