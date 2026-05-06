# slgpu — семантическая карта

> Расположение: **docs/AGENTS.md**. Скопировано из **template** репозитория и адаптировано для **slgpu**.

# GRACE Framework - Project Engineering Protocol

## Keywords

slgpu, vllm, sglang, llm-inference, benchmark, docker-compose, gpu, h200, prometheus, grafana, dcgm, sg-lang, comparative-benchmark, openai-api

## Annotation

**slgpu** — стенд для сравнения движков LLM-инференса **vLLM** и **SGLang** на Linux-сервере с NVIDIA GPU.

- **CLI (хост):** **`./slgpu help`** и **`./slgpu web up|down|restart|logs|build|install`**; env-файл `docker compose` — **`configs/bootstrap.env`** (минимум для подъёма web). LLM/мониторинг/proxy — из **slgpu-web** (`native.*` jobs, Docker API), не из host `./slgpu` (кроме web).
- **Web UI — Develonica.LLM:** импорт стека: **`POST /api/v1/app-config/install`** читает **`configs/main.env`** (это **только** шаблон импорта — backend больше не сидит БД при старте) и импортирует пресеты с диска в БД. Стек в рантайме — **только SQLite** (`stack_params`), без кодовых дефолтов и без `${VAR:-...}` в compose-YAML. Все имена сервисов / контейнеров / внутренних портов / сети / образов параметризованы через реестр (`SLGPU_NETWORK_NAME`, `WEB_DOCKER_IMAGE`, `*_SERVICE_NAME`, `*_CONTAINER_NAME`, `*_INTERNAL_PORT`); конфиги мониторинга — из `*.tmpl` в `configs/monitoring/...` рендерятся в `${WEB_DATA_DIR}/.slgpu/monitoring/` (`render_monitoring_configs`). **5.2.1:** в `*.tmpl` запрещено оставлять буквальные `${VAR}` в комментариях — `string.Template.substitute` не различает комментарий и тело и падает с `KeyError`; страница **«Настройки»** показывает **все ключи реестра, кроме `ui_hidden`** (со столбцом «Описание / для чего»; с **6.0.2** listen внутри контейнеров LLM помечены `ui_hidden` — см. там же), подсвечивает **красным** незаполненные обязательные параметры (`!allow_empty && required_for≠∅ && value===''`). **5.2.2:** реестр `_STACK_KEY_REGISTRY` и UI «Настройки» приведены 1-в-1 к разделам **`configs/main.env` (1..8)** — `network` / `web` / `paths` / `images` / `inference` / `monitoring` / `proxy` / `secrets`; `registry_to_public()` отдаёт ключи в порядке вставки (без алфавитной сортировки), фронт идёт по тому же порядку без своего sort'а. Чекбокс «секрет» больше не вырывает строку в группу `secrets` — секрет остаётся в своём смысловом разделе (как в main.env, где `GRAFANA_ADMIN_PASSWORD` — в «Мониторинг», `LANGFUSE_SALT` — в «Прокси»). **5.2.3:** для `is_secret`-ключей фронт читает маску `data.secrets[k] === "***"` от `mask_secrets()` и хранит её во флаге `StackRow.secretSet`; `isMissingRequired(meta, value, secretSet)` для `is_secret && secretSet` возвращает `false` — строка с уже сохранённым в БД секретом **не** подсвечивается красным даже при пустом поле «Значение». В поле value такой строки placeholder показывает `••••••••` с пометкой «значение задано в БД (скрыто)»; пустой ввод при сохранении трактуется как «не менять» (см. `buildStackPatch`: `if (v) secrets[r.k] = v`). **5.2.4:** страница **«Стек мониторинга»** (`Monitoring.tsx`) рендерит карточки только сервисов с `service.category === "monitoring"` (базово пять + опционально DCGM при **`monitoring_dcgm_wanted`**, **8.3.0** — итого **5–6**); карточки `Langfuse` (`category="proxy"`) и `LiteLLM Proxy` (`category="gateway"`) переехали в отдельную секцию «Сервисы прокси-стека» на странице «LiteLLM Proxy» (`LiteLLM.tsx`, фильтр `category in {"proxy","gateway"}`). Backend `_settings_probes()` в `app/services/monitoring.py` — число проб зависит от **`MONITORING_DCGM`** и опроса GPU; endpoint `/monitoring/services` отдаёт список без фиксированной длины 8 для monitoring-only карточек. **5.2.6:** Docker-образ slgpu-web — в репозитории `web/frontend/package-lock.json`, в `docker/Dockerfile.web` на стадии frontend — **`npm ci`** (детерминированный install); кэш BuildKit для `/root/.cache/pip` на `pip install`; один вызов **`pip install -e .`** до `COPY backend/` вместо пары `pip install .` + `pip install --no-deps -e .`. **5.2.7:** `configs/monitoring/promtail/promtail-config.yml.tmpl` — путь в `relabel_configs.replacement` с regex-группой: **не** писать сырой `$1` (ломает конструктор `string.Template`); в `.tmpl` — **`$$1`**, после `render_monitoring_configs` в YAML снова **`$1`** для Promtail. **5.2.8:** `docker/docker-compose.monitoring.yml` — сервис **grafana**: не монтировать **весь** `…/provisioning:ro` и поверх **файл** `datasource.yml` в подкаталоге (nested bind внутри :ro — ошибка runc «read-only file system»). Монтировать **отдельно** `dashboards`, `alerting`, `plugins` и **`${WEB_DATA_DIR}/.slgpu/monitoring/datasource.yml`** → `provisioning/datasources/datasource.yml`. **5.2.9:** дефолт **`LANGFUSE_REDIS_IMAGE`** в **`configs/main.env`** — **`redis:8-alpine`** (RDB v12+); детали — [`configs/monitoring/README.md`](../configs/monitoring/README.md) (Redis: RDB, `vm.overcommit_memory`). **5.2.10:** в **`main.env`** — node-exporter, DCGM, alpine chown. **6.0.0:** **Loki 3.7.1** / **Promtail 3.6.10** / **Prometheus v3.11.3** / **Grafana 13.0.1** + `loki-config.yaml.tmpl` (Loki 3, TSDB; **8.5.1:** retention и query lookback **120 дней**, `2880h`); MAJOR — смена дефолтных образов и несовместимость данных Loki 2 без миграции — [configs/monitoring/README.md](../configs/monitoring/README.md). **6.0.1:** `native.monitoring.*` поднимает **только** `docker-compose.monitoring.yml`; **`native.proxy.*`** — прокси-стек + bootstrap MinIO/БД LiteLLM (`_monitoring_bootstrap` в `proxy.up`). **6.0.2:** редактируются только **`LLM_API_BIND`**, **`LLM_API_PORT`**, **`LLM_API_PORT_SGLANG`**; внутриконтейнерный listen (**`VLLM_HOST`**/**`VLLM_PORT`**/**`SGLANG_LISTEN_*`**) помечены **`ui_hidden`** и не показываются в «Настройки»/`GET /app-config/stack` (`presentation_stack`); подстановка из хост-биндов/портов — `apply_llm_listen_derived_defaults` после `apply_vllm_aliases_to_merged`; `buildStackPatch` не удаляет скрытые ключи из БД. **6.0.7:** в «Настройки» — чекбокс «Показывать секреты в явном виде»: **`GET /api/v1/app-config/stack?reveal_secrets=true`** возвращает реальные значения в **`secrets`** и **`secrets_revealed: true`** (иначе маска **`***`**, **`secrets_revealed: false`**); аудит **`app_config.stack_secrets_read_plain`**. Визуал в духе [`develonica.ru`](https://develonica.ru/) / [гайдлайна](https://develonica.ru/company/guideline/): **`IBM Plex Sans`**, **`Finlandica`**, палитра **`#59AFFF`** / **`#0A5AA4`**; footer — **`VERSION`** через **`/healthz`**, копирайт `Igor Yatsishen, Develonica`.
- **Данные на хосте** — в **`data/`** (`data/README.md`): по умолчанию `MODELS_DIR=./data/models`, `PRESETS_DIR=./data/presets`, `WEB_DATA_DIR=./data/web`, **`WEB_BIND=0.0.0.0`**, **`WEB_MONITORING_HTTP_HOST=host.docker.internal`** (пробы из контейнера web); публичный host для ссылок в браузере — **`/api/v1/settings/public-access`**. Entrypoint web chown’ит `/data`, `…/data/models`, `…/data/presets`, `…/data/bench` под uid приложения.
- **Модели и пресеты:** реестр в БД синхронизируется с **`MODELS_DIR/<org>/<repo>`**; **`pull_progress`** в **`GET /api/v1/models`** — активная **`native.model.pull`**; **8.1.8:** зависший pull снимается через **`POST /api/v1/models/{id}/pull/force-stop`** (job → `cancelled`, model-lock снят, частичные файлы остаются для докачки). Пресеты: рабочие **`data/presets/*.env`**, эталоны **`examples/presets/`**, формат — **[`examples/presets/README.md`](../examples/presets/README.md)**; **8.2.4:** env-параметры **`TORCH_FLOAT32_MATMUL_PRECISION`** и **`VLLM_USE_V1`** разрешены в `presets.parameters` и передаются в контейнер vLLM; **8.2.12:** расширены канонические ключи **`presets.parameters`** для **SGLang** (DP-attention, chunked prefill, EAGLE MTP, **`SGLANG_DOCKER_IMAGE`**, **`NVIDIA_VISIBLE_DEVICES`** и смежные env); см. **`web/backend/app/services/presets.py`** (`PRESET_RUNTIME_KEYS` / **`_RUNTIME_KEYS`**); **8.2.15:** **`DATA_PARALLEL_SIZE`** (`vllm serve --data-parallel-size`) и алиас **`VLLM_DATA_PARALLEL_SIZE`** в пресете; в **`PRESET_ONLY_KEYS`** — слот не подмешивает значение из глобального стека; **8.2.16:** в **`STACK_KEY_REGISTRY`** **`allow_empty`** для **`SGLANG_ENABLE_DP_ATTENTION`**, **`SGLANG_ENABLE_DP_LM_HEAD`**, **`SGLANG_MM_ENABLE_DP_ENCODER`**, **`SGLANG_ENABLE_MULTI_LAYER_EAGLE`** — пусто в «Настройки» не блокирует **`llm_slot`** (`validate_required`/`missing_keys_in_db`); фактическое значение — из пресета или **`0`** по умолчанию в **`scripts/serve.sh`**; **8.2.13:** **`GET /api/v1/presets/parameter-schema`** — список всех поддерживаемых ключей для UI (группа, описание из реестра, подсказка дефолта из **`scripts/serve.sh`**); страница **«Пресеты»** рендерит полную таблицу параметров из схемы; **8.2.5:** **`GET /presets/{id}/download-env`** отдаёт `.env` как browser attachment для клиентского ПК, без записи в `PRESETS_DIR`; **UI** — CRUD, клон, **«Скачать .env на ПК»** (`GET /presets/{id}/download-env`), **«Выгрузить в PRESETS_DIR»** из карточки (`POST /presets/{id}/export`), **импорт из файла в БД** (`POST /presets/import-env`, на «Пресеты» — блок «Загрузить пресет из файла»; конфликт имени → **409** → `confirm` и **`overwrite`**). В **v5.0.0** сняты **`POST /presets/sync`** и **`/import-templates`**. **Логи Docker (все слоты/мониторинг):** **`GET /api/v1/docker/containers`**, **`…/docker/containers/{id|name}/logs`**, **`/docker/engine-events`**, **`/docker/daemon-log`**; UI **`/docker-logs`**. **Логи приложения (таблица `app_log_event` в SQLite):** **`GET /api/v1/app-logs/events`**; опцион. файл `app.log` при `WEB_LOG_FILE_ENABLED`; UI **`/app-logs`** (**8.5.0:** кнопка «Сохранить в файл» — JSON на ПК по текущим фильтрам, пагинация на клиенте). **8.2.0/8.2.6/8.2.8 — отчёты по логам Loki:** **`POST /api/v1/log-reports`**, **`GET /api/v1/log-reports`**, **`GET /api/v1/log-reports/{id}`**, **`GET /api/v1/log-reports/llm-catalog-source`**; job **`web.log_report.generate`** (Loki → факты → LLM `POST …/v1/chat/completions`: по умолчанию внутренний LiteLLM, **8.4.0** — опционально **`LOG_REPORT_LLM_API_BASE`** / **`LOG_REPORT_LLM_API_KEY`**); при 500/недоступности LLM — локальная Markdown-сводка по `facts` без падения отчёта; severity-классификатор OOM/error/warn — regex с границами слов, чтобы `bloom`/info-шум не давал ложные срабатывания); UI **`/log-reports`**.
- **Инференс (slots-only, 4.0.0+):** только **`native.slot.*`** и lock **`("engine","slot:{key}")`**; страница **`/runtime`** — слоты из **`GET /api/v1/runtime/snapshot`**, создание **`POST /api/v1/runtime/slots`**, GPU — **`GET /api/v1/gpu/state`**, **`/gpu/availability`**. **8.1.5:** если в теле **`POST /runtime/slots`** не передан **`slot_key`**, бэкенд назначает **`slot_key` = имя пресета** (при коллизии в БД — суффиксы `-2`, `-3`, …; иначе короткий uuid); имя контейнера на хосте — **`slgpu-<engine>-<slot_key>`** (`slot_runtime.slot_container_name`). **Лог слота:** **`GET /api/v1/runtime/slots/{key}/logs?tail=1..2000`**, в UI — выбор tail (не более 2000 строк). **Stop** при активной job — **`POST .../down?force=1`**. Нет **`native.llm.*`** и глобального lock **`("engine","runtime")`**. Лента **Задачи** / **`GET /jobs/{id}`**: для **`native.*`** при **running** лог подтягивается в БД периодически (в т.ч. **docker pull** по слоям до `containers.run`). **8.5.0:** UI **`/jobs`** — «Сохранить ленту в файл» (`GET /activity?limit=500`) и «Сохранить задачу в файл» в модалке (полный **`Job`**, хвосты stdout/stderr как в БД).
- **Стек в web:** **`stack_params`** + **`cfg.meta`**, операции мониторинга и бенча через **`native.*`** jobs (**docker compose** из backend). **Monitoring** и **proxy** — **разные** jobs (`native.monitoring.*` / `native.proxy.*`); общий снимок **`${WEB_DATA_DIR}/.slgpu/compose-service.env`** из БД (`sync_merged_flat`). См. [configs/monitoring/README.md](../configs/monitoring/README.md). **8.3.0:** ключ **`MONITORING_DCGM`** и **`monitoring_dcgm_wanted()`** — опциональный DCGM (compose **`--profile gpu`**), условный scrape/job в **`prometheus.yml.tmpl`** (**`DCGM_SCRAPE_YAML`**); LiteLLM/proxy-compose **без** `gpus`. **8.3.1:** **`HOST_GPU_DOCKER_PROBE`** / **`NVIDIA_SMI_DOCKER_IMAGE`** — отключение эфемерного `docker run` с GPU для `nvidia-smi` на хосте (дашборд «Сервер», **`/gpu/state`**, ветка **`MONITORING_DCGM=auto`**); образ пробы из стека или **`WEB_NVIDIA_SMI_DOCKER_IMAGE`** (дефолт **`nvidia/cuda:12.4.1-base-ubuntu22.04`**). **8.3.2:** в «Настройки» для этих ключей в группе **`web`** — подблок по **`subgroup`** **`gpu_docker_probe`**. **`8.1.6`–`8.1.7`:** второй Prometheus job **`vllm-slots`** (file_sd) читает **`${WEB_DATA_DIR}/.slgpu/monitoring/vllm-slots.json`** — дополнительные хост-порты vLLM при мультислоте из UI; `render_monitoring_configs` при **отсутствии** файла создаёт дефолт **`8110–8130`** (**8.1.7**), существующий файл не перезаписывается. **LiteLLM:** с **8.2.11** два секрета находятся в **«Настройки → Стек в базе данных → 8. Секреты приложения»**: **`LITELLM_MASTER_KEY`** для proxy/Admin UI (пишется в `compose-service.env`) и **`LITELLM_API_KEY`** для backend Bearer-вызовов `/v1/chat/completions` (по умолчанию — сводка «Отчётов логов» через внутренний LiteLLM; не пишется в compose-env). **8.4.0:** опционально **`LOG_REPORT_LLM_API_BASE`** (web, подгруппа **«Отчёты логов (LLM)»**) и **`LOG_REPORT_LLM_API_KEY`** — отдельный OpenAI-compatible origin/ключ; при непустой базе и пустом секрете Bearer берётся из **`LITELLM_API_KEY`**. Оба раскрываются только через общий `reveal_secrets=true`; legacy `settings.public_access.litellm_*` мигрируются в эти строки.
- **Бенчмарки:** **`/api/v1/bench/*`**, артефакты **`data/bench/results/`**, в UI — модалка по **`summary.json`**.

Контракт web: **`web/CONTRACT.md`**.

## Core Principles

### 1. Never Write Code Without a Contract
Before generating or editing any module, create or update its MODULE_CONTRACT with PURPOSE, SCOPE, INPUTS, and OUTPUTS. The contract is the source of truth. Code implements the contract, not the other way around.

### 2. Semantic Markup Is Load-Bearing Structure
Markers like `# START_BLOCK_<NAME>` and `# END_BLOCK_<NAME>` in shell scripts, or comments in Python (`# START_BLOCK: ...`) are navigation anchors, not documentation. They must be:
- uniquely named
- paired
- proportionally sized so one block fits inside an LLM working window

### 3. Knowledge Graph Is Always Current
`grace/knowledge-graph/knowledge-graph.xml` is the project map. When you add a module, move a script, rename exports, or add dependencies, update the graph so future agents can navigate deterministically.

### 4. Verification Is a First-Class Artifact
Testing, traces, and log anchors are designed before large execution waves. `grace/verification/verification-plan.xml` is part of the architecture, not an afterthought. Logs are evidence. Tests are executable contracts.

### 5. Top-Down Synthesis
Code generation follows:
`RequirementsAnalysis -> TechnologyStack -> DevelopmentPlan -> VerificationPlan -> Code + Tests`

Never jump straight to code when requirements, architecture, or verification intent are still unclear.

### 6. Governed Autonomy
Agents have freedom in HOW to implement, but not in WHAT to build. Contracts, plans, graph references, and verification requirements define the allowed space.

## Semantic Markup Reference

### Module Level (Shell / Python)
```bash
# FILE: scripts/cmd_example.sh
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: [What this module does - one sentence]
#   SCOPE: [What operations are included]
#   DEPENDS: [List of module dependencies]
#   LINKS: [Knowledge graph references]
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   exportedSymbol - one-line description
# END_MODULE_MAP
```

### Function or Component Level
```bash
# START_CONTRACT: functionName
#   PURPOSE: [What it does]
#   INPUTS: { paramName: Type - description }
#   OUTPUTS: { ReturnType - description }
#   SIDE_EFFECTS: [External state changes or "none"]
#   LINKS: [Related modules/functions]
# END_CONTRACT: functionName
```

### Code Block Level
```bash
# START_BLOCK_VALIDATE_INPUT
# ... code ...
# END_BLOCK_VALIDATE_INPUT
```

### Change Tracking
```bash
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.2.0 - What changed and why]
# END_CHANGE_SUMMARY
```

## Logging and Trace Convention

All important logs must point back to semantic blocks:
```bash
# Shell scripts: use structured echo or logger
echo "[ModuleName][functionName][BLOCK_NAME] message" | logger -t slgpu
```

```python
# Python scripts
logger.info(`[ModuleName][functionName][BLOCK_NAME] message`, {
  correlationId,
  stableField: value,
})
```

Rules:
- prefer structured fields over prose-heavy log lines
- redact secrets (HF_TOKEN, Grafana passwords) and high-risk payloads
- treat missing log anchors on critical branches as a verification defect
- update tests when log markers change intentionally

## Verification Conventions

`grace/verification/verification-plan.xml` is the project-wide verification contract. Keep it current when module scope, test files, commands, critical log markers, or gate expectations change.

Testing rules:
- deterministic assertions first
- trace or log assertions when trajectory matters
- test files may also carry MODULE_CONTRACT, MODULE_MAP, semantic blocks, and CHANGE_SUMMARY when they are substantial
- module-local tests should stay close to the module they verify
- wave-level and phase-level checks should be explicit in the verification plan

## File Structure
```
grace/
  requirements/requirements.xml       - Product requirements and use cases
  technology/technology.xml             - Stack decisions, tooling, observability, testing
  plan/development-plan.xml           - Modules M-*, phases, data flows, ownership, write scopes
  verification/verification-plan.xml  - Test strategy, trace expectations, module and phase gates
  knowledge-graph/knowledge-graph.xml - Project-wide navigation graph
docs/
  AGENTS.md              - Semantic map (this file)
  HISTORY.md             - Хронология репозитория и журнал итераций (project-history)
scripts/
  _lib.sh, cmd_web.sh, cmd_help.sh, serve.sh, bench_openai.py, bench_load.py, …
configs/
  bootstrap.env       - минимальный --env-file для ./slgpu web up
  main.env            - шаблон импорта в UI (POST /app-config/install)
  models/             - README формата пресетов
  monitoring/         - *.tmpl (prometheus, loki, promtail, datasource) → render_monitoring_configs
    prometheus/prometheus.yml.tmpl, loki/loki-config.yaml.tmpl, promtail/promtail-config.yml.tmpl,
    grafana/provisioning/ (datasource.yml.tmpl + dashboards/json),
    grafana/templates/ (vllmdash2.json — ручной импорт), README.md, …
data/bench/
  ... results/{engine}/{timestamp}/ (summary.json; локально, не в git) ...
```

## Documentation Artifacts - Unique Tag Convention

In `grace/**/*.xml`, repeated entities must use their unique ID as the XML tag name instead of a generic tag with an `ID` attribute. This reduces closing-tag ambiguity and gives LLMs stronger anchors.

### Tag naming conventions

| Entity type | Anti-pattern | Correct (unique tags) |
|---|---|---|
| Module | `<Module ID="M-CONFIG">...</Module>` | `<M-CONFIG NAME="Config" TYPE="UTILITY">...</M-CONFIG>` |
| Verification module | `<Verification ID="V-M-AUTH">...</Verification>` | `<V-M-AUTH MODULE="M-AUTH">...</V-M-AUTH>` |
| Phase | `<Phase number="1">...</Phase>` | `<Phase-1 name="Foundation">...</Phase-1>` |
| Flow | `<Flow ID="DF-SEARCH">...</Flow>` | `<DF-SEARCH NAME="...">...</DF-SEARCH>` |
| Use case | `<UseCase ID="UC-001">...</UseCase>` | `<UC-001>...</UC-001>` |
| Step | `<step order="1">...</step>` | `<step-1>...</step-1>` |
| Export | `<export name="config" .../>` | `<export-config .../>` |
| Function | `<function name="search" .../>` | `<fn-search .../>` |
| Type | `<type name="SearchResult" .../>` | `<type-SearchResult .../>` |
| Class | `<class name="Error" .../>` | `<class-Error .../>` |

### What NOT to change
- `CrossLink` tags stay self-closing
- single-use structural wrappers like `<contract>`, `<inputs>`, `<outputs>`, `<annotations>`, `<test-files>`, `<module-checks>`, and `<phase-gates>` stay generic
- code-level markup already uses unique names and stays as-is

## Rules for Modifications

1. Read the MODULE_CONTRACT before editing any file.
2. After editing source or test files, update MODULE_MAP if exports or helper surfaces changed.
3. After adding or removing modules, update `grace/knowledge-graph/knowledge-graph.xml`.
4. After changing test files, commands, critical scenarios, or log markers, update `grace/verification/verification-plan.xml`.
5. After fixing bugs, add a CHANGE_SUMMARY entry and strengthen nearby verification if the old evidence was weak.
6. Never remove semantic markup anchors unless the structure is intentionally replaced with better anchors.
