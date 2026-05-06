# Собрать логи всех контейнеров в одно место

Сейчас в slgpu у сервисов задан драйвер **`json-file`** с ротацией (см. `logging` в [`docker/docker-compose.llm.yml`](../../docker/docker-compose.llm.yml) и [`docker/docker-compose.monitoring.yml`](../../docker/docker-compose.monitoring.yml)). Физически это **отдельные файлы** на диске Docker:  
`/var/lib/docker/containers/<container_id>/<container_id>-json.log` — «одна папка», но не один файл и неудобно для поиска.

Ниже — как получить **единую точку просмотра** или **единый поток** на хосте.

---

## 1. Журнал systemd — `journald` (просто на Linux)

Все логи контейнеров попадают в **journal**, смотрите одной командой:

1. На хосте задайте драйвер по умолчанию в **`/etc/docker/daemon.json`** (создайте или дополните; после правок: `systemctl restart docker`):

```json
{
  "log-driver": "journald",
  "log-opts": {
    "tag": "{{.Name}}"
  }
}
```

2. Пересоздайте контейнеры (старые продолжат писать старым драйвером, пока не `up` заново):  
   `./slgpu down` / `./slgpu monitoring down` и снова `up`.

3. Просмотр:

```bash
journalctl -u docker -f
journalctl CONTAINER_NAME=vllm -f
journalctl -f   # часто видны записи с именем контейнера в MESSAGE
```

**Минус:** объём journal на диске нужно учитывать (`/etc/systemd/journald.conf`, `SystemMaxUse=`).

---

## 2. Syslog на хосте — один файл или удалённый сервер

В `daemon.json`:

```json
{
  "log-driver": "syslog",
  "log-opts": {
    "syslog-address": "unixgram:///dev/log",
    "tag": "{{.Name}}"
  }
}
```

Дальше настраиваете **rsyslog** / **syslog-ng**: отфильтровать по `tag` и писать, например, в `/var/log/docker/all.log` или слать на центральный syslog. Это уже политика хоста, не репозитория slgpu.

---

## 3. Loki + Promtail + Grafana (включено в slgpu)

Репозиторий поднимает **Loki** и **Promtail** вместе с Prometheus/Grafana: [`docker/docker-compose.monitoring.yml`](../../docker/docker-compose.monitoring.yml), данные Loki на хосте: **`LOKI_DATA_DIR`** (по умолчанию `data/monitoring/loki` в `main.env`), позиции Promtail: **`PROMTAIL_DATA_DIR`**. Подъём: **`./slgpu monitoring up`**, права: **`./slgpu monitoring fix-perms`**.

- Ретенция и лимиты Loki: [`loki/loki-config.yaml.tmpl`](loki/loki-config.yaml.tmpl) (`retention_period` и др.). В шаблоне slgpu хранение и глубина запросов заданы на **120 дней** (**`retention_period: 2880h`**, **`max_query_lookback: 2880h`**). Для **`/loki/api/v1/query_range`** важен **`limits_config.max_entries_limit_per_query`**: дефолт Loki — **5000 строк**; без поднятия лимита запрос с `limit=8000` (как у «Отчёты логов» в web) даёт **400**. В шаблоне slgpu задано **25000**; после изменения нужен **`native.monitoring` restart/up** чтобы перерендерился `${WEB_DATA_DIR}/.slgpu/monitoring/loki-config.yaml`. Параметр **`direction`** в HTTP API только **`backward`**/**`forward`** (нижний регистр; не `BACKWARD`).
- Datasource Loki в Grafana: provisioning, дашборд: **Grafana → Explore → Loki** (например запрос `{job="docker-logs"}`). **8.6+:** дополнительные метки у строк из Docker SD: **`container_id`**, **`docker_image`**, **`slgpu_slot`**, **`slgpu_engine`**, **`slgpu_preset`**, **`slgpu_run_id`** (для слотов inference — лейблы `com.develonica.slgpu.*` и уникальный **`run_id`** при каждом запуске контейнера); они используются в LogQL и в API выгрузки **`/api/v1/log-exports`**.
- Promtail читает **`/var/lib/docker/containers`** и `docker.sock` (Linux); на Docker Desktop / нестандартных путях может понадобиться правка.

**Если Loki (или Promtail) падает с `read .../loki-config.yaml: is a directory`:** на хосте по пути `configs/monitoring/loki/loki-config.yaml` иногда оказывается **каталог** (при отсутствии файла Docker раньше мог создать пустой каталог с этим именем). Compose монтирует **каталог** `loki/` → `/etc/loki` (аналогично `promtail/`). Скрипт **`./slgpu monitoring up`** / **`restart`** сам удаляет такой каталог и делает **`git checkout`** yaml из репо; вручную: `rm -rf configs/monitoring/loki/loki-config.yaml` (если каталог), `git checkout -- configs/monitoring/loki/loki-config.yaml`, снова **`./slgpu monitoring up`**.

**Если Prometheus падает с `mount ... not a directory` / file vs directory на `prometheus.yml`:** конфиги лежат в каталоге **`configs/monitoring/prometheus/`**, compose монтирует его в **`/etc/prometheus`**. Если на диске остались старые одноимённые **каталоги** на месте файлов-конфигов, удалите их вручную и восстановите файлы из репо, затем перезапустите стек из UI.

**Если стек, поднятый из web-UI, ломается (типично: `minio-bucket-init` → exit 126; `prometheus`/`loki` → restarting):** причина — рассогласование путей между web-контейнером и хостом. Внутри web репо смонтировано как `/slgpu`, а на хосте оно лежит в другом каталоге; `docker compose` внутри web передаёт docker daemon путь `/slgpu/configs/monitoring/...`, daemon живёт **на хосте** и под этим путём ничего не находит — создаёт **пустые каталоги** на месте файлов-конфигов и скриптов. Фикс: web должен монтировать репо **по тому же абсолютному пути, что и на хосте** (переменная `SLGPU_HOST_REPO`, см. [`scripts/cmd_web.sh`](../../scripts/cmd_web.sh) и [`docker/docker-compose.web.yml`](../../docker/docker-compose.web.yml)).

**`native.monitoring.fix-perms`** (UI «Стек мониторинга» → «Чинить права»): backend выполняет `mkdir -p` / `chown -R` через короткоживущий root-helper контейнер (`docker run --rm -u 0:0 -v ...`) — работает и на хосте от обычного пользователя, и из web (через `docker.sock`). Образ-помощник — параметр **`SLGPU_BENCH_CHOWN_IMAGE`** (по умолчанию `alpine:latest`); при оффлайн-стенде задайте уже доступный локально образ с `sh` и `chown`.

Готовые примеры (общие, без slgpu):

- [Grafana Docker driver → Loki](https://grafana.com/docs/loki/latest/send-data/docker-driver/) — драйвер `loki` у контейнеров, логи сразу в Loki;
- [Run Loki in Docker](https://grafana.com/docs/loki/latest/get-started/) — стек `loki` + `promtail` в отдельном `docker-compose`.

Это отдельный кусок инфраструктуры: тома под Loki, ресурсы, бэкап. В репозиторий slgpu по умолчанию не входит, чтобы не раздувать обязательный `monitoring up`.

---

## 4. Внешняя облачная/корпоративная система

**Vector**, **Fluent Bit**, **Filebeat** (sidecar или агент на хосте) читают **docker logs** (`json-file` или `journald`) и шлют в Elasticsearch, OpenSearch, cloud logging и т.д. — удобно, если у вас уже есть стек.

---

## Кратко

| Цель | Подход |
|------|--------|
| Один **текстовый поток** на сервере | `log-driver: journald` + `journalctl` |
| Один **файл/фильтр** на хосте | `log-driver: syslog` + rsyslog/syslog-ng |
| Один **интерфейс поиска** (как дашборды) | Loki + Grafana |
| **Enterprise** / облако | Vector / Fluent Bit / Beats → ваш backend |

**Важно:** смена `daemon.json` действует на **новые** контейнеры после `restart docker`; существующие лучше пересоздать через compose `up` / `up -d --force-recreate`.
