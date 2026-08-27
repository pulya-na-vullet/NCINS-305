# NCINS-305 / NCINS-306 — проверка методов получения документов из AC

Единый запуск: **`python app.py`**.

Скрипт прогоняет:

- **NCINS-306** (`POST /v1/doc/download-signed`) — подписанные документы, **новые тесты**
- **NCINS-305** (`POST /v1/doc/download`) — документ из AlfaCapture
- **NCINS-277** (`POST /v1/doc/generate-form`) — источник `fileId` / `operationId`

и пишет отчёт, где блок NCINS-306 выделен отдельно.

## Запуск

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

Опции:

```bash
python3 app.py --open          # открыть HTML-отчёт
python3 app.py --live          # стенд (VPN / alfaintra)
python3 app.py --no-zip        # только тесты и отчёт, без архива
```

После прогона:

- `reports/NCINS-305-report.html` — основной отчёт (сводка, **отдельный блок NCINS-306**, остальные наборы, HTTP)
- `reports/NCINS-305-report.md` — тот же отчёт в Markdown
- `reports/NCINS-305-report.json` — машинный формат, ключ `suites`
- `reports/junit.xml` — JUnit
- `NCINS-305-tests.zip` — архив со скриптом, отчётом и исходниками

## Что проверяется

### NCINS-306 · download-signed (новые)

| Кейс | Ожидание |
|---|---|
| Скачивание по `operationId` из generate-form | `200`, PDF (`%PDF`) |
| `operationId` из комментария NCINS-306 | `200` + PDF |
| Ответ совпадает с вложением `response.pdf` | байты PDF |
| Нет / пустой / `null` `operationId` | `400` |
| Несуществующий `operationId` | `404` |
| GET вместо POST | `404` или `405` |

### NCINS-305 / NCINS-277

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
POST …/ufr-eos-ul-ncins-core-api/v1/doc/download-signed
```

Пример NCINS-306 (DEV):

```text
POST https://dev.ufrulkint-api.moscow.alfaintra.net/ufr-eos-ul-ncins-core-api/v1/doc/download-signed
{"operationId": "6a8f275decea715b0ef88213"}
```

Параметры живого стенда — в `.env.example` (скопируйте в `.env`).
