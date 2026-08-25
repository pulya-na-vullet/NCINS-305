# NCINS-305 — тесты метода получения документа из AC

Python-скрипт для проверки **NCINS-305**: `POST /v1/doc/download` (получение документа из AlfaCapture через `ufr-eos-ul-ncins-core-api`).

Документ для скачивания создаётся методом **NCINS-277** `POST /v1/doc/generate-form` — так указано в комментарии к задаче.

## Что проверяется

| Кейс | Ожидание |
|---|---|
| Генерация ПФ с `fileAttributes` | `200`, непустой `documentIds` |
| Генерация ПФ без `fileAttributes` | `200` и id документа (требование NCINS-277) |
| Генерация без `customerData` / `managerData` / `groups` | `400` |
| Скачивание по `fileId` из `documentIds` | `200`, `Content-Type: application/pdf`, тело начинается с `%PDF` |
| `fileId` из комментария NCINS-305 | `200` + PDF (на стенде может истечь) |
| Нет / пустой / `null` `fileId` | `400` |
| `fileId` не UUID | `400` |
| Несуществующий UUID | `404` |
| GET вместо POST | `404` или `405` |

Эндпоинты из комментариев Jira:

```text
POST https://int.ufrulkint-api.moscow.alfaintra.net/ufr-eos-ul-ncins-core-api/v1/doc/generate-form
POST https://int.ufrulkint-api.moscow.alfaintra.net/ufr-eos-ul-ncins-core-api/v1/doc/download
```

Тело download:

```json
{ "fileId": "285946b0-002e-428c-b1e1-d5c558e81c24" }
```

## Запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Mock-контур (без VPN, по умолчанию):

```bash
pytest -q
# или
python test_ncins_305.py
```

Живой INT-стенд (нужен доступ к `*.alfaintra.net`):

```bash
cp .env.example .env   # при необходимости поправьте значения
export NCINS_LIVE=1
# опционально готовый fileId, без повторной генерации ПФ:
# export NCINS_FILE_ID=285946b0-002e-428c-b1e1-d5c558e81c24
pytest -q -m live
```

Скачанные PDF пишутся в `artifacts/`.

## Файлы

- `test_ncins_305.py` — набор тестов
- `ncins_client.py` — HTTP-клиент generate-form / download
- `mock_server.py` — локальная имитация API для офлайн-прогона
- `.env.example` — параметры стенда
