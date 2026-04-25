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

- Ретенция и лимиты Loki: [`loki/loki-config.yaml`](loki/loki-config.yaml) (`retention_period` и др.).
- Datasource Loki в Grafana: provisioning, дашборд: **Grafana → Explore → Loki** (например запрос `{job="docker-logs"}`).
- Promtail читает **`/var/lib/docker/containers`** и `docker.sock` (Linux); на Docker Desktop / нестандартных путях может понадобиться правка.

**Если Loki (или Promtail) падает с `read .../loki-config.yaml: is a directory`:** на хосте по пути `configs/monitoring/loki/loki-config.yaml` иногда оказывается **каталог** (при отсутствии файла Docker раньше мог создать пустой каталог с этим именем). Compose монтирует **каталог** `loki/` → `/etc/loki` (аналогично `promtail/`). Скрипт **`./slgpu monitoring up`** / **`restart`** сам удаляет такой каталог и делает **`git checkout`** yaml из репо; вручную: `rm -rf configs/monitoring/loki/loki-config.yaml` (если каталог), `git checkout -- configs/monitoring/loki/loki-config.yaml`, снова **`./slgpu monitoring up`**.

**Если Prometheus падает с `mount ... not a directory` / file vs directory на `prometheus.yml`:** конфиги лежат в каталоге **`configs/monitoring/prometheus/`**, compose монтирует его в **`/etc/prometheus`**. Скрипт up/restart проверяет, что **`prometheus.yml`** и **`prometheus-alerts.yml`** — файлы; если на диске остались старые одноимённые **каталоги**, удалите их вручную и восстановите файлы из репо, затем снова **`./slgpu monitoring up`**.

**Если `monitoring up` запущен из web-UI и стек ломается (типично: `minio-bucket-init` → exit 126; `prometheus`/`loki` → restarting):** причина — рассогласование путей между web-контейнером и хостом. Внутри web репо смонтировано как `/slgpu`, а на хосте оно лежит в другом каталоге; `docker compose` внутри web передаёт docker daemon путь `/slgpu/configs/monitoring/...`, daemon живёт **на хосте** и под этим путём ничего не находит — создаёт **пустые каталоги** на месте файлов-конфигов и скриптов. Фикс: web должен монтировать репо **по тому же абсолютному пути, что и на хосте** (переменная `SLGPU_HOST_REPO`, см. [`scripts/cmd_web.sh`](../../scripts/cmd_web.sh) и [`docker/docker-compose.web.yml`](../../docker/docker-compose.web.yml)). Команды `./slgpu monitoring up|restart` дополнительно лечат каталоги-обманки на месте конфигов и скриптов (Loki, Promtail, Prometheus, Langfuse `minio-bucket-init.sh`, LiteLLM init/entrypoint/`config.yaml`) через `slgpu_ensure_config_yaml_is_file`.

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
