# GRACE — артефакты методологии

Каталог **`grace/`** хранит **общие (shared) XML-артефакты** методологии [GRACE](https://github.com/osovv/grace-marketplace) (Graph-RAG Anchored Code Engineering): контракты модулей, порядок реализации, верификация и граф навигации. Актуальная линейка навыков и CLI публикуется в репозитории marketplace (версия пакета см. в его `README.md` / `CHANGELOG.md`).

## Связь с upstream

- **Навыки:** `grace-init`, `grace-plan`, `grace-verification`, `grace-execute`, `grace-multiagent-execute`, `grace-refresh`, … — канонические описания в [skills/grace](https://github.com/osovv/grace-marketplace/tree/main/skills/grace).
- **CLI (опционально):** `bun add -g @osovv/grace-cli` → `grace lint --path <корень-проекта>` для проверки целостности артефактов и разметки; `grace module find|show`, `grace file show` — быстрый обзор модуля и файла.
- **Отличие этого workspace:** общие XML лежат под **`grace/**`** по этапам ЖЦ (не в `docs/*.xml`); семантическая карта репозитория — **`docs/AGENTS.md`**. В upstream quick start по-прежнему фигурируют пути `docs/*.xml` — при переносе проекта ориентируйтесь на таблицу ниже.

В upstream в `grace-init` дополнительно бывает шаблон **`operational-packets.xml`** (пакеты исполнения для волн агентов). Здесь он **не входит** в минимальный bootstrap; при необходимости возьмите шаблон из [grace-marketplace](https://github.com/osovv/grace-marketplace) и положите рядом с остальными артефактами или заведите под `grace/`, если команда договорится о едином месте.

## Структура (этапы ЖЦ)

| Этап ЖЦ | Каталог | Файл | Содержание |
|--------|---------|------|------------|
| Требования | `grace/requirements/` | `requirements.xml` | Акторы, сценарии, ограничения |
| Проектирование / план | `grace/plan/` | `development-plan.xml` | Модули M-*, фазы, потоки, `ExecutionPolicy` для multi-agent |
| Технологии | `grace/technology/` | `technology.xml` | Стек, тесты, формат якорей в коде |
| Верификация | `grace/verification/` | `verification-plan.xml` | Гейты, трассы V-*, сценарии |
| Граф знаний | `grace/knowledge-graph/` | `knowledge-graph.xml` | Узлы, рёбра, публичные аннотации |

**Частное (file-local)** — контракты, `MODULE_MAP`, семантические блоки, `CHANGE_SUMMARY` в исходниках; см. навык `$grace-explainer` и CLI `grace file show`.

Семантическая карта проекта и конвенции: **`docs/AGENTS.md`**. Журнал сессий: **`docs/HISTORY.md`**. Прочая Markdown-документация — в **`docs/`**.

**Observability (актуализация):** `grace/technology/technology.xml` → секция `Observability` / `grafana-provisioning` перечисляет JSON в `configs/monitoring/grafana/provisioning/dashboards/json/` (SGLang: `sglang-dashboard-slgpu`, `sglangdash2-slgpu`; vLLM: `vllmdash2`). При смене дашбордов синхронно обновляйте `grace/**` и UC-008 в `requirements.xml`.
