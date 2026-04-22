# Мониторинг

- **Prometheus** (`127.0.0.1:9090`): скрейп `vllm:8111/metrics`, `sglang:8222/metrics`, `dcgm-exporter:9400`, **`node-exporter:9100`** (job **`node-exporter`** — метрики хоста).
  - Когда контейнер vLLM или SGLang **не создан** (другой профиль compose), DNS-имя `vllm`/`sglang` отсутствует — target будет **DOWN** или с ошибкой lookup. Это ожидаемо для A/B; смотрите метрики активного движка.
- **Grafana** (`127.0.0.1:3000`): datasource Prometheus подключён автоматически.
- **Алерты**: [prometheus-alerts.yml](prometheus-alerts.yml) (пороги при необходимости ослабьте, если метрики в вашей версии vLLM называются иначе).

## Рекомендуемые дашборды (импорт в UI Grafana)

1. **NVIDIA DCGM** — dashboard ID [12239](https://grafana.com/grafana/dashboards/12239).
2. **Node Exporter Full** (хост: CPU, RAM, диск, сеть) — dashboard ID [**1860**](https://grafana.com/grafana/dashboards/1860).  
   - **Dashboards → Import →** вставьте `1860` → Load.  
   - Datasource: **Prometheus** (как в provisioning, uid `prometheus`).  
   - Убедитесь, что контейнер **`node-exporter`** запущен (`docker compose up -d node-exporter` или через `./slgpu up …`).  
   - В выпадающих списках вверху дашборда выберите **Datasource: Prometheus**, **job = `node-exporter`**, **instance** — обычно **`host`** (так задан label в [`prometheus.yml`](prometheus.yml)); в других ревизиях дашборда может быть `node-exporter:9100`.
3. **vLLM** — поиск на grafana.com по `vllm` (ID зависят от версии; импорт через **Dashboards → Import**).

### Node Exporter Full «не работает» / пустые графики

1. **Цель Prometheus в состоянии UP.** Откройте `http://127.0.0.1:9090/targets` (или ваш `PROMETHEUS_BIND`). Строка **`node-exporter`** должна быть **UP**. Если **DOWN** — контейнер не запущен (`docker compose ps node-exporter`), нет сети с Prometheus или порт `9100` недоступен из контейнера `prometheus`.
2. **Метрики реально есть.** В Prometheus → **Graph**: запрос `up{job="node-exporter"}` должен вернуть **1**. Если пусто — скрейп не доходит до дашборда Grafana.
3. **Переменные дашборда.** У импортированного **1860** вверху страницы выберите **job = `node-exporter`** и подходящий **instance** (в этом репозитории по умолчанию **`host`**). Если оставить другой job (например случайно `prometheus`), почти все панели будут пустыми.
4. **Datasource при импорте.** При импорте укажите **Prometheus** (в provisioning он уже есть, uid **`prometheus`**). Если выбрать «не тот» источник или отключённый — данных не будет.
5. **Время на графике.** Установите диапазон **Last 15 minutes** (или больше), если только что подняли стек.
6. **Версия дашборда.** На grafana.com у **1860** несколько ревизий; при полном «No data» попробуйте импортировать **последнюю ревизию** или дропдаун **job** переключите на все доступные значения по очереди.

После смены [`prometheus.yml`](prometheus.yml) перезагрузите конфиг (см. ниже) или `docker compose up -d prometheus`.

## Перезагрузка конфигурации Prometheus

После правки `prometheus.yml`:

```bash
curl -X POST http://127.0.0.1:9090/-/reload
```

(в compose включён `--web.enable-lifecycle`).

## Диск заполнился: `no space left on device` / ошибки WAL Prometheus

Сообщения вида `write /prometheus/wal/...: no space left on device` значат, что **на хосте или в разделе Docker закончилось свободное место**. Prometheus не может писать WAL и TSDB — скрейпы и правила падают.

**Что сделать на сервере:**

1. Посмотреть место: `df -h`, `docker system df` (образы, build cache, тома).
2. Освободить диск: удалить неиспользуемые образы/кэш (`docker system prune` — осторожно), почистить логи, перенести модели/данные на другой раздел.
3. Ограничить рост TSDB в `.env`: уменьшить **`PROMETHEUS_RETENTION_TIME`** (например `7d`) и/или задать **`PROMETHEUS_RETENTION_SIZE`** (например `20GB`). Перезапустить контейнер Prometheus: `docker compose up -d prometheus`.

Данные Prometheus хранятся в именованном томе **`prometheus-data`** (путь на хосте: `docker volume inspect slgpu_prometheus-data`).

## Сообщения в логах Grafana (часто безвредны)

| Сообщение | Смысл |
|-----------|--------|
| `migrations completed` / `Created default admin` | Первый запуск: встроенная SQLite создала БД и пользователя `admin` — норма. |
| `plugin xychart is already registered` | Известная коллизия встроенного и подгружаемого плагина в части сборок Grafana; дашборды обычно работают. |
| `Failed to read plugin provisioning ... plugins` / `alerting` | Раньше не было пустых каталогов в `provisioning/` — в репозитории добавлены `plugins/` и `alerting/`, после `git pull` и пересоздания контейнера строки пропадают. |
| `Database locked, sleeping then retrying` | SQLite под нагрузкой; Grafana ретраит. Если повторяется часто — для продакшена лучше вынести БД Grafana в PostgreSQL. |
