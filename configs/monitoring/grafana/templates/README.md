# Grafana — шаблоны вне auto-provisioning

- **`vllmdash2.json`** — эталонный дашборд vLLM V2 (Prometheus). Импорт: Grafana → **Dashboards → Import** (файл из этого каталога). Не подхватывается из `provisioning/dashboards/json/`, чтобы не дублировать панели при старте.

Сборка SGLang-дашборда из этого эталона: `python3 configs/monitoring/grafana/provisioning/dashboards/json/_build_sglangdash2.py`.
