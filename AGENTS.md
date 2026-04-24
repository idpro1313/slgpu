# Инструкции для AI-агентов (slgpu)

Этот файл **входит в git** и должен читаться **в начале задачи**. Он задаёт обязательные действия и границы; детальная семантическая карта GRACE — в **`docs/AGENTS.md`**, если каталог **`docs/`** у вас есть локально (в репозиторий не коммитится).

---

## 1. Сначала прочитать

1. **[`README.md`](README.md)** — назначение, CLI, конфигурация, мониторинг, troubleshooting.
2. Релевантные к задаче файлы: обычно [`scripts/`](scripts/) (в т.ч. [`_lib.sh`](scripts/_lib.sh), `cmd_*.sh`, [`serve.sh`](scripts/serve.sh)), [`docker-compose.yml`](docker-compose.yml), [`main.env`](main.env), [`configs/models/`](configs/models/).

Если на диске есть **`docs/AGENTS.md`** — откройте его для ключевых слов, карт и конвенций GRACE. Если есть **`.cursor/rules/`** — следуйте правилам редактора.

---

## 2. Что в git, а чего в clone нет

| Путь | В репозитории | Заметка |
|------|----------------|---------|
| `slgpu`, `scripts/`, `configs/`, `docker-compose*.yml`, `monitoring/`, `bench/`, `main.env`, `README.md`, `VERSION` | да | основная рабочая область |
| `docs/`, `grace/`, `.cursor/`, `.kilo/` | **нет** (см. [`.gitignore`](.gitignore)) | копия с рабочей машины или создание вручную; без них полагайтесь на **этот** файл и `README.md` |
| `docs/HISTORY.md` (журнал сессий) | нет | ведите **локально**, если каталог `docs/` существует |

---

## 3. Обязательно делать

- **Соответствие коду существующему стилю** в затронутых файлах: те же соглашения имён, `set -euo pipefail` в bash, структура вызовов из [`_lib.sh`](scripts/_lib.sh).
- **Минимальный дифф**: менять только то, что нужно для запроса; не приводить «заодно» несвязанные модули.
- **Согласованность с Docker и пресетами**: новые переменные для инференса — через [`main.env`](main.env) + пресет + при необходимости блок `environment` в [`docker-compose.yml`](docker-compose.yml) (см. существующие `SLGPU_*`).
- **Версия и коммит** после осмысленного изменения:
  - единственный номер релиза — в **[`VERSION`](VERSION)** (SemVer);
  - поднимите `VERSION` (PATCH / MINOR / MAJOR по смыслу правки: баг/мелочь → PATCH, новая команда/пресет/дашборд → MINOR, ломающее CLI → MAJOR);
  - сообщение коммита: **`X.Y.Z: краткое описание на русском`**, в первой строке — **номер из `VERSION`**;
  - выполните **`git add` / `commit` / `push`**, если есть доступ (не оставляйте только инструкции пользователю).
- **Журнал (если есть `docs/HISTORY.md`)**: после завершения задачи кратко зафиксируйте: что сделано, почему, какие файлы.
- **Документация в репо**: при изменении поведения CLI, пресетов или compose обновите соответствующий раздел **`README.md`** и при необходимости [`configs/models/README.md`](configs/models/README.md) / [`monitoring/README.md`](monitoring/README.md).

---

## 4. Не делать

- **Не поднимать стенд** (Docker, vLLM, SGLang) **в среде агента** ради «проверки, что работает» — среда разработчика и GPU VM проекта с этим не совпадают. Проверка — статический анализ, чтение кода, линтер.
- **Не коммитить** секреты: реальные пароли, токены, заполненный `configs/secrets/hf.env` (в git только примеры).
- **Не добавлять** в git каталоги из `.gitignore` (`docs/`, `grace/`, …) без явного запроса владельца репозитория.

---

## 5. Точки входа по типу задач

| Тема | Куда смотреть |
|------|----------------|
| Команда `./slgpu` | [`slgpu`](slgpu), [`scripts/cmd_*.sh`](scripts/) |
| vLLM / SGLang аргументы | [`scripts/serve.sh`](scripts/serve.sh), [`docker-compose.yml`](docker-compose.yml) |
| Модель, TP, парсеры | [`configs/models/*.env`](configs/models/), [`configs/models/README.md`](configs/models/README.md) |
| Мониторинг | [`docker-compose.monitoring.yml`](docker-compose.monitoring.yml), [`monitoring/`](monitoring/) |
| Бенч | [`scripts/bench_openai.py`](scripts/bench_openai.py), [`scripts/bench_load.py`](scripts/bench_load.py) |
| История проекта (кратко) | [`HISTORY.md`](HISTORY.md) → ссылка на полный журнал в `docs/`, если он есть у вас |

---

## 6. Кратко о продукте

**slgpu** — сравнение **vLLM** и **SGLang** в Docker, OpenAI-совместимый API, бенчмарки, опционально Prometheus/Grafana. Целевое железо при разработке: **8× H200**, по умолчанию **TP=8**. Подробности — только в **`README.md`**.
