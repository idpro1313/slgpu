# slgpu — семантическая карта

> Расположение: **docs/AGENTS.md**. Скопировано из **template** репозитория и адаптировано для **slgpu**.

# GRACE Framework - Project Engineering Protocol

## Keywords

slgpu, vllm, sglang, llm-inference, benchmark, docker-compose, gpu, h200, prometheus, grafana, dcgm, sg-lang, comparative-benchmark, openai-api

## Annotation

**slgpu** — стенд для сравнения движков LLM-инференса **vLLM** и **SGLang** на Linux-сервере с NVIDIA GPU.

- **CLI (хост):** **`./slgpu help`** и **`./slgpu web up|down|restart|logs|build|install`**; env-файл `docker compose` — **`configs/bootstrap.env`** (минимум для подъёма web). LLM/мониторинг/proxy — из **slgpu-web** (`native.*` jobs, Docker API), не из host `./slgpu` (кроме web).
- **Web UI — Develonica.LLM:** импорт стека: **`POST /api/v1/app-config/install`** читает **`configs/main.env`** (это **только** шаблон импорта — backend больше не сидит БД при старте) и импортирует пресеты с диска в БД. Стек в рантайме — **только SQLite** (`stack_params`), без кодовых дефолтов и без `${VAR:-...}` в compose-YAML. Все имена сервисов / контейнеров / внутренних портов / сети / образов параметризованы через реестр (`SLGPU_NETWORK_NAME`, `WEB_DOCKER_IMAGE`, `*_SERVICE_NAME`, `*_CONTAINER_NAME`, `*_INTERNAL_PORT`); конфиги мониторинга — из `*.tmpl` в `configs/monitoring/...` рендерятся в `${WEB_DATA_DIR}/.slgpu/monitoring/` (`render_monitoring_configs`). **5.2.1:** в `*.tmpl` запрещено оставлять буквальные `${VAR}` в комментариях — `string.Template.substitute` не различает комментарий и тело и падает с `KeyError`; страница **«Настройки»** показывает **все ключи реестра** (со столбцом «Описание / для чего»), подсвечивает **красным** незаполненные обязательные параметры (`!allow_empty && required_for≠∅ && value===''`). **5.2.2:** реестр `_STACK_KEY_REGISTRY` и UI «Настройки» приведены 1-в-1 к разделам **`configs/main.env` (1..8)** — `network` / `web` / `paths` / `images` / `inference` / `monitoring` / `proxy` / `secrets`; `registry_to_public()` отдаёт ключи в порядке вставки (без алфавитной сортировки), фронт идёт по тому же порядку без своего sort'а. Чекбокс «секрет» больше не вырывает строку в группу `secrets` — секрет остаётся в своём смысловом разделе (как в main.env, где `GRAFANA_ADMIN_PASSWORD` — в «Мониторинг», `LANGFUSE_SALT` — в «Прокси»). **5.2.3:** для `is_secret`-ключей фронт читает маску `data.secrets[k] === "***"` от `mask_secrets()` и хранит её во флаге `StackRow.secretSet`; `isMissingRequired(meta, value, secretSet)` для `is_secret && secretSet` возвращает `false` — строка с уже сохранённым в БД секретом **не** подсвечивается красным даже при пустом поле «Значение». В поле value такой строки placeholder показывает `••••••••` с пометкой «значение задано в БД (скрыто)»; пустой ввод при сохранении трактуется как «не менять» (см. `buildStackPatch`: `if (v) secrets[r.k] = v`). Визуал в духе [`develonica.ru`](https://develonica.ru/) / [гайдлайна](https://develonica.ru/company/guideline/): **`IBM Plex Sans`**, **`Finlandica`**, палитра **`#59AFFF`** / **`#0A5AA4`**; footer — **`VERSION`** через **`/healthz`**, копирайт `Igor Yatsishen, Develonica`.
- **Данные на хосте** — в **`data/`** (`data/README.md`): по умолчанию `MODELS_DIR=./data/models`, `PRESETS_DIR=./data/presets`, `WEB_DATA_DIR=./data/web`, **`WEB_BIND=0.0.0.0`**, **`WEB_MONITORING_HTTP_HOST=host.docker.internal`** (пробы из контейнера web); публичный host для ссылок в браузере — **`/api/v1/settings/public-access`**. Entrypoint web chown’ит `/data`, `…/data/models`, `…/data/presets`, `…/data/bench` под uid приложения.
- **Модели и пресеты:** реестр в БД синхронизируется с **`MODELS_DIR/<org>/<repo>`**; **`pull_progress`** в **`GET /api/v1/models`** — активная **`native.model.pull`**. Пресеты: рабочие **`data/presets/*.env`**, эталоны **`examples/presets/`**, формат — **[`configs/models/README.md`](../configs/models/README.md)**; **UI** — CRUD, клон, **«Выгрузить в .env»** из карточки (`POST /presets/{id}/export`). В **v5.0.0** сняты **`POST /presets/sync`** и **`/import-templates`**. **Логи Docker (все слоты/мониторинг):** **`GET /api/v1/docker/containers`**, **`…/docker/containers/{id|name}/logs`**, **`/docker/engine-events`**, **`/docker/daemon-log`**; UI **`/docker-logs`**. **Логи приложения (таблица `app_log_event` в SQLite):** **`GET /api/v1/app-logs/events`**; опцион. файл `app.log` при `WEB_LOG_FILE_ENABLED`; UI **`/app-logs`**.
- **Инференс (slots-only, 4.0.0+):** только **`native.slot.*`** и lock **`("engine","slot:{key}")`**; страница **`/runtime`** — слоты из **`GET /api/v1/runtime/snapshot`**, создание **`POST /api/v1/runtime/slots`**, GPU — **`GET /api/v1/gpu/state`**, **`/gpu/availability`**. **Лог слота:** **`GET /api/v1/runtime/slots/{key}/logs?tail=1..2000`**, в UI — выбор tail (не более 2000 строк). **Stop** при активной job — **`POST .../down?force=1`**. Нет **`native.llm.*`** и глобального lock **`("engine","runtime")`**. Лента **Задачи** / **`GET /jobs/{id}`**: для **`native.*`** при **running** лог подтягивается в БД периодически (в т.ч. **docker pull** по слоям до `containers.run`).
- **Стек в web:** **`stack_params`** + **`cfg.meta`**, операции мониторинга и бенча через **`native.*`** jobs (**docker compose** из backend). **Monitoring/proxy:** снимок **`${WEB_DATA_DIR}/.slgpu/compose-service.env`** пишется **из БД** (`sync_merged_flat`); compose с очищенным process env. См. [configs/monitoring/README.md](../configs/monitoring/README.md). **LiteLLM:** ключ из **«Публичный доступ»** → **`LITELLM_MASTER_KEY`**.
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
