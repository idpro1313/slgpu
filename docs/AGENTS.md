# slgpu — семантическая карта

> Расположение: **docs/AGENTS.md**. Скопировано из **template** репозитория и адаптировано для **slgpu**.

# GRACE Framework - Project Engineering Protocol

## Keywords

slgpu, vllm, sglang, llm-inference, benchmark, docker-compose, gpu, h200, prometheus, grafana, dcgm, sg-lang, comparative-benchmark, openai-api

## Annotation

**slgpu** — стенд для сравнения движков LLM-инференса **vLLM** и **SGLang** на Linux-сервере с NVIDIA GPU. Единая точка входа `./slgpu` (bash). `docker-compose.yml` — vLLM/SGLang; **мониторинг** — `configs/monitoring/`, `docker-compose.monitoring.yml`, **`./slgpu monitoring up`**. Первый `monitoring up` на новом сервере выполняет одноразовый bootstrap (`minio-bucket-init`, `litellm-pg-init`; markers в `data/monitoring/.bootstrap`), последующие `up/restart` init-контейнеры не пересоздают. **Web UI** — **Develonica.LLM**, запуск **`./slgpu web up`**; frontend оформлен по брендовой рамке [`develonica.ru`](https://develonica.ru/) и [`Материалам бренда`](https://develonica.ru/company/guideline/): Gilroy-first, рубиновый акцент, молочно-белые поверхности, pill-навигация, стрелочный brand mark, SVG favicon; footer показывает версию из корневого `VERSION` через `/healthz` и копирайт `Igor Yatsishen, Develonica`. **Локальные данные на хосте** (модели, БД, TSDB) — в каталоге **`data/`** (см. `data/README.md`), пути в `main.env` по умолчанию `MODELS_DIR=./data/models`, `PRESETS_DIR=./data/presets`, `WEB_DATA_DIR=./data/web`, **`WEB_BIND=0.0.0.0`** (slgpu-web снаружи), **`WEB_MONITORING_HTTP_HOST=host.docker.internal`** (внутренние HTTP-пробы к Prometheus и др. из контейнера; внешние browser-ссылки задаются на странице `Настройки` через `/api/v1/settings/public-access`), `…_DATA_DIR=./data/monitoring/…`. Web entrypoint chown’ит `/data`, `${WEB_SLGPU_ROOT}/data/models` и `${WEB_SLGPU_ROOT}/data/presets` под uid 10001 перед запуском app, чтобы `slgpu pull` и экспорт пресетов из UI могли писать в bind mounts. Web-реестр моделей синхронизируется с фактическими папками `MODELS_DIR/<org>/<repo>`; в **`GET /api/v1/models`** (и карточке модели) поле **`pull_progress`** отражает активную задачу **`native.model.pull`** (прогресс/подпись из job). Модель можно редактировать (revision/notes) и удалять из реестра или вместе с локальной папкой весов внутри `MODELS_DIR`. Рабочие пресеты `data/presets/*.env` (не в git) — рецепты запуска; эталоны в `examples/presets/` (формат — `configs/models/README.md`). В UI пресетов — кнопка **«Загрузить шаблоны»** (`POST /api/v1/presets/import-templates`): копирование `examples/presets/*.env` в PRESETS_DIR без перезаписи существующих файлов и импорт в БД. Просмотр/редактирование через key/value, экспорт в `.env`, удаление записи/файла. **Dashboard** — блок **«Сервер»**: ОС/ядро, CPU, RAM, диск по корню репо, NVIDIA+CUDA через `nvidia-smi`, если бинарь доступен в контейнере web. Runtime/Dashboard показывают engine, запрошенный пресет, HF ID модели и TP из последнего web-запуска; Runtime дополнительно показывает хвост логов текущего vLLM/SGLang контейнера. Runtime/Monitoring UI показывают активную job и блокируют повторные конфликтующие кнопки; backend locks: `("engine","runtime")`, `("monitoring","stack")`. **Стек для web:** таблица **`stack_params`** в SQLite (строка на параметр, флаг секрета) + **`cfg.meta`**; импорт **`./slgpu web install`** или Настройки → установка из `main.env`; legacy JSON `cfg.stack`/`cfg.secrets` мигрируются при старте и обнуляются. Долгие операции — **`native.*`** (compose / `huggingface_hub`), не subprocess `./slgpu`. Порты мониторинга и LLM для проб берутся из слитого стека. **Бенчмарки:** UI-страница, API `/api/v1/bench/*`, артефакты **`data/bench/results/`**, пример **`data/bench/report.md`**. См. `web/CONTRACT.md`.

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
  ... cmd_*.sh, _lib.sh, bench_openai.py, bench_load.py with GRACE markup ...
configs/
  ... vllm/, sglang/, models/, secrets/ ...
monitoring/
  prometheus/ (prometheus.yml, prometheus-alerts.yml), grafana/provisioning/ (dashboards/json: slgpu-overview, sglang-dashboard-slgpu, sglangdash2-slgpu, vllmdash2; _build_sglangdash2.py), README.md, LOGS.md
bench/
  ... report.md, results/ ...
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
