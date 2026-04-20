# Мониторинг

- **Prometheus** (`127.0.0.1:9090`): скрейп `vllm:8111/metrics`, `sglang:8222/metrics`, `dcgm-exporter:9400`.
  - Когда контейнер vLLM или SGLang **не создан** (другой профиль compose), DNS-имя `vllm`/`sglang` отсутствует — target будет **DOWN** или с ошибкой lookup. Это ожидаемо для A/B; смотрите метрики активного движка.
- **Grafana** (`127.0.0.1:3000`): datasource Prometheus подключён автоматически.
- **Алерты**: [prometheus-alerts.yml](prometheus-alerts.yml) (пороги при необходимости ослабьте, если метрики в вашей версии vLLM называются иначе).

## Рекомендуемые дашборды (импорт в UI Grafana)

1. **NVIDIA DCGM** — dashboard ID [12239](https://grafana.com/grafana/dashboards/12239).
2. **vLLM** — поиск на grafana.com по `vllm` (ID зависят от версии; импорт через **Dashboards → Import**).

## Перезагрузка конфигурации Prometheus

После правки `prometheus.yml`:

```bash
curl -X POST http://127.0.0.1:9090/-/reload
```

(в compose включён `--web.enable-lifecycle`).
