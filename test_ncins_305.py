"""
Тесты NCINS-305: POST /v1/doc/download — получение документа из AlfaCapture.

Документ создаётся методом генерации ПФ NCINS-277 (POST /v1/doc/generate-form),
как указано в комментарии к задаче.

Запуск mock (без VPN):
    pytest -q

Запуск против INT-стенда:
    NCINS_LIVE=1 pytest -q -m live
"""

from __future__ import annotations

import pytest

from conftest import ARTIFACTS, LIVE, is_pdf
from mock_server import PDF_BYTES, UNKNOWN_FILE_ID
from ncins_client import EXAMPLE_FILE_ID, NcinsClient, NcinsConfig


@pytest.mark.mock
def test_generate_form_returns_document_id(client: NcinsClient) -> None:
    """NCINS-277: генерация ПФ отдаёт documentIds — вход для download."""
    response = client.generate_form(include_file_attributes=True)

    assert response.status_code == 200, response.text
    assert "application/json" in response.headers.get("Content-Type", "")
    body = response.json()
    assert body.get("operationId"), body
    document_ids = body.get("documentIds")
    assert isinstance(document_ids, list) and document_ids, body


@pytest.mark.mock
def test_generate_form_without_file_attributes_returns_200(
    client: NcinsClient,
) -> None:
    """NCINS-277: без fileAttributes — 200 и id документа."""
    response = client.generate_form(include_file_attributes=False)

    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body.get("documentIds"), list), body
    assert body["documentIds"], "ожидается сгенерированный id документа"


@pytest.mark.mock
@pytest.mark.parametrize("missing", ["customerData", "managerData", "groups"])
def test_generate_form_missing_required_field_returns_400(
    client: NcinsClient, missing: str
) -> None:
    """NCINS-277: без обязательного поля — 400."""
    payload = client.config.generate_form_payload()
    del payload[missing]
    response = client.generate_form(payload=payload)
    assert response.status_code == 400, response.text


@pytest.mark.mock
def test_download_generated_document_returns_pdf(
    client: NcinsClient, file_id: str
) -> None:
    """Позитив: скачать документ, созданный generate-form."""
    response = client.download(file_id)

    assert response.status_code == 200, response.text
    content_type = response.headers.get("Content-Type", "")
    assert "application/pdf" in content_type, content_type
    assert is_pdf(response.content), response.content[:32]
    assert len(response.content) > 8

    ARTIFACTS.mkdir(exist_ok=True)
    out = ARTIFACTS / f"{file_id}.pdf"
    out.write_bytes(response.content)
    assert out.stat().st_size == len(response.content)


@pytest.mark.mock
def test_download_example_file_id_from_jira(client: NcinsClient) -> None:
    """fileId из комментария NCINS-305. На стенде документ мог истечь."""
    response = client.download(EXAMPLE_FILE_ID)
    if LIVE and response.status_code in {404, 400}:
        pytest.skip(
            f"пример fileId из Jira недоступен: {response.status_code} {response.text[:200]}"
        )
    assert response.status_code == 200, response.text
    assert is_pdf(response.content)


@pytest.mark.mock
def test_download_missing_file_id_returns_400(client: NcinsClient) -> None:
    """NCINS-305: нет fileId — 400."""
    response = client.download(file_id=None, raw_json={})
    assert response.status_code == 400, response.text


@pytest.mark.mock
def test_download_empty_file_id_returns_400(client: NcinsClient) -> None:
    """NCINS-305: пустой fileId — 400."""
    response = client.download("")
    assert response.status_code == 400, response.text


@pytest.mark.mock
def test_download_null_file_id_returns_400(client: NcinsClient) -> None:
    """NCINS-305: fileId=null — 400."""
    response = client.download(file_id=None, raw_json={"fileId": None})
    assert response.status_code == 400, response.text


@pytest.mark.mock
def test_download_invalid_uuid_returns_400(client: NcinsClient) -> None:
    """NCINS-305: fileId не UUID — 400."""
    response = client.download("not-a-uuid")
    assert response.status_code == 400, response.text


@pytest.mark.mock
def test_download_unknown_file_id_returns_404(client: NcinsClient) -> None:
    """NCINS-305: неизвестный UUID — 404."""
    response = client.download(UNKNOWN_FILE_ID)
    assert response.status_code == 404, response.text


@pytest.mark.mock
def test_download_without_json_body_returns_400(client: NcinsClient) -> None:
    """NCINS-305: нет JSON-тела — 400."""
    response = client.download(file_id=None, send_json=False)
    assert response.status_code == 400, response.text


@pytest.mark.mock
def test_download_get_not_allowed(client: NcinsClient, file_id: str) -> None:
    """NCINS-305: GET вместо POST — 404/405."""
    response = client.session.get(
        client._url("/v1/doc/download"),
        params={"fileId": file_id},
        timeout=client.config.timeout,
    )
    assert response.status_code in {404, 405}, response.text


@pytest.mark.live
@pytest.mark.skipif(not LIVE, reason="Задайте NCINS_LIVE=1 для стенда INT")
def test_live_generate_and_download(request: pytest.FixtureRequest) -> None:
    """E2E на INT: generate-form → download PDF."""
    client = NcinsClient()
    request.node.http_calls = client.history
    file_id = client.config.file_id
    if not file_id:
        generate = client.generate_form(include_file_attributes=True)
        assert generate.status_code == 200, generate.text
        document_ids = generate.json().get("documentIds") or []
        assert document_ids, generate.text
        file_id = str(document_ids[0])

    download = client.download(file_id)
    assert download.status_code == 200, download.text
    assert "application/pdf" in download.headers.get("Content-Type", "")
    assert is_pdf(download.content)

    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / f"{file_id}.pdf").write_bytes(download.content)


def test_mock_server_pdf_magic() -> None:
    """Служебное: mock отдаёт валидный PDF magic."""
    assert is_pdf(PDF_BYTES)


def test_client_builds_download_url() -> None:
    """Служебное: URL download/generate-form/download-signed не теряет префикс сервиса."""
    client = NcinsClient(
        NcinsConfig.from_env(base_url="http://example.local/ufr-eos-ul-ncins-core-api")
    )
    assert (
        client._url("/v1/doc/download")
        == "http://example.local/ufr-eos-ul-ncins-core-api/v1/doc/download"
    )
    assert (
        client._url("/v1/doc/generate-form")
        == "http://example.local/ufr-eos-ul-ncins-core-api/v1/doc/generate-form"
    )
    assert (
        client._url("/v1/doc/download-signed")
        == "http://example.local/ufr-eos-ul-ncins-core-api/v1/doc/download-signed"
    )
    payload = client.config.generate_form_payload()
    assert payload["customerData"]["cus"]
    assert payload["managerData"]["adLogin"]
    assert payload["groups"]
    assert payload["fileAttributes"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
