# NCINS-305 — проверка метода получения документа из AC

Единый запуск: **`python app.py`**.

Скрипт прогоняет тесты NCINS-305 (`POST /v1/doc/download`) и связанный NCINS-277 (`POST /v1/doc/generate-form`), пишет отчёт и собирает zip.

## Запуск

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

Опции:

```bash
python3 app.py --open          # открыть HTML-отчёт
python3 app.py --live          # INT-стенд (VPN / alfaintra)
python3 app.py --no-zip        # только тесты и отчёт, без архива
```

После прогона:

- `reports/NCINS-305-report.html` — основной отчёт (сводка, кейсы, HTTP)
- `reports/NCINS-305-report.md` — тот же отчёт в Markdown
- `reports/NCINS-305-report.json` — машинный формат
- `reports/junit.xml` — JUnit
- `NCINS-305-tests.zip` — архив со скриптом, отчётом и исходниками

## Что проверяется

| Кейс | Ожидание |
|---|---|
| Генерация ПФ с `fileAttributes` | `200`, непустой `documentIds` |
| Генерация ПФ без `fileAttributes` | `200` и id документа |
| Генерация без `customerData` / `managerData` / `groups` | `400` |
| Скачивание по `fileId` из `documentIds` | `200`, PDF (`%PDF`) |
| `fileId` из комментария NCINS-305 | `200` + PDF |
| Нет / пустой / `null` `fileId` | `400` |
| `fileId` не UUID | `400` |
| Несуществующий UUID | `404` |
| GET вместо POST | `404` или `405` |

Эндпоинты из комментариев Jira:

```text
POST …/ufr-eos-ul-ncins-core-api/v1/doc/generate-form
POST …/ufr-eos-ul-ncins-core-api/v1/doc/download
```

Параметры живого стенда — в `.env.example` (скопируйте в `.env`).
