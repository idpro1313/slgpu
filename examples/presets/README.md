# Примеры пресетов (в git)

Файлы здесь — **эталонные копии** для нового стенда. Рабочий каталог CLI и Web UI — **`data/presets/`** (по умолчанию `PRESETS_DIR=./data/presets` в `main.env`); он **не отслеживается** git’ом для `*.env`, чтобы локальные правки на сервере не мешали `git pull`.

Первичная заливка на чистом клоне:

```bash
cp -n examples/presets/*.env data/presets/
```

(`-n` не перезаписывает уже созданные на сервере файлы.)

Формат полей: [`configs/models/README.md`](../configs/models/README.md).
