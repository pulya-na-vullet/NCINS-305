"""
Тесты NCINS-306: POST /v1/doc/download-signed — получение подписанных документов.

operationId берётся из ответа generate-form (NCINS-277) либо из примера в Jira:
    "operationId": "6a8f275decea715b0ef88213"

Образец ответа — вложение response.pdf (согласие + отчёт о подписании).

Запуск mock (без VPN):
    pytest -q test_ncins_306.py

Запуск против стенда:
    NCINS_LIVE=1 pytest -q -m live test_ncins_306.py
"""

from __future__ import annotations

import pytest

from conftest import ARTIFACTS, LIVE, SIGNED_SAMPLE_PDF, is_pdf
from mock_server import SIGNED_PDF_BYTES, UNKNOWN_OPERATION_ID
from ncins_client import EXAMPLE_OPERATION_ID, NcinsClient


@pytest.mark.mock
def test_download_signed_generated_operation_returns_pdf(
    client: NcinsClient, operation_id: str
) -> None:
    """NCINS-306: скачать подписанный документ по operationId из generate-form."""
    response = client.download_signed(operation_id)

    assert response.status_code == 200, response.text
    content_type = response.headers.get("Content-Type", "")
    assert "application/pdf" in content_type, content_type
    assert is_pdf(response.content), response.content[:32]
    assert len(response.content) > 8

    ARTIFACTS.mkdir(exist_ok=True)
    out = ARTIFACTS / f"{operation_id}-signed.pdf"
    out.write_bytes(response.content)
    assert out.stat().st_size == len(response.content)


@pytest.mark.mock
def test_download_signed_example_operation_id_from_jira(client: NcinsClient) -> None:
    """NCINS-306: operationId из комментария Jira. На стенде операция могла истечь."""
    response = client.download_signed(EXAMPLE_OPERATION_ID)
    if LIVE and response.status_code in {404, 400}:
        pytest.skip(
            f"пример operationId из Jira недоступен: "
            f"{response.status_code} {response.text[:200]}"
        )
    assert response.status_code == 200, response.text
    assert is_pdf(response.content)


@pytest.mark.mock
def test_download_signed_matches_jira_attachment(client: NcinsClient) -> None:
    """NCINS-306: mock отдаёт тот же PDF, что приложен к задаче (response.pdf)."""
    response = client.download_signed(EXAMPLE_OPERATION_ID)
    assert response.status_code == 200, response.text
    assert is_pdf(response.content)
    assert response.content == SIGNED_PDF_BYTES
    if SIGNED_SAMPLE_PDF.is_file():
        assert response.content == SIGNED_SAMPLE_PDF.read_bytes()


@pytest.mark.mock
def test_download_signed_missing_operation_id_returns_400(client: NcinsClient) -> None:
    """NCINS-306: нет operationId — 400."""
    response = client.download_signed(operation_id=None, raw_json={})
    assert response.status_code == 400, response.text


@pytest.mark.mock
def test_download_signed_empty_operation_id_returns_400(client: NcinsClient) -> None:
    """NCINS-306: пустой operationId — 400."""
    response = client.download_signed("")
    assert response.status_code == 400, response.text


@pytest.mark.mock
def test_download_signed_null_operation_id_returns_400(client: NcinsClient) -> None:
    """NCINS-306: operationId=null — 400."""
    response = client.download_signed(operation_id=None, raw_json={"operationId": None})
    assert response.status_code == 400, response.text


@pytest.mark.mock
def test_download_signed_unknown_operation_id_returns_404(client: NcinsClient) -> None:
    """NCINS-306: неизвестный operationId — 404."""
    response = client.download_signed(UNKNOWN_OPERATION_ID)
    assert response.status_code == 404, response.text


@pytest.mark.mock
def test_download_signed_without_json_body_returns_400(client: NcinsClient) -> None:
    """NCINS-306: нет JSON-тела — 400."""
    response = client.download_signed(operation_id=None, send_json=False)
    assert response.status_code == 400, response.text


@pytest.mark.mock
def test_download_signed_get_not_allowed(
    client: NcinsClient, operation_id: str
) -> None:
    """NCINS-306: GET вместо POST — 404/405."""
    response = client.session.get(
        client._url("/v1/doc/download-signed"),
        params={"operationId": operation_id},
        timeout=client.config.timeout,
    )
    assert response.status_code in {404, 405}, response.text


@pytest.mark.live
@pytest.mark.skipif(not LIVE, reason="Задайте NCINS_LIVE=1 для стенда")
def test_live_download_signed(request: pytest.FixtureRequest) -> None:
    """E2E: generate-form → download-signed PDF (или NCINS_OPERATION_ID)."""
    client = NcinsClient()
    request.node.http_calls = client.history
    operation_id = client.config.operation_id
    if not operation_id:
        generate = client.generate_form(include_file_attributes=True)
        assert generate.status_code == 200, generate.text
        operation_id = str(generate.json().get("operationId") or "")
        assert operation_id, generate.text

    download = client.download_signed(operation_id)
    if download.status_code in {404, 400}:
        pytest.skip(
            "подписанный документ ещё не готов: "
            f"{download.status_code} {download.text[:200]}"
        )
    assert download.status_code == 200, download.text
    assert "application/pdf" in download.headers.get("Content-Type", "")
    assert is_pdf(download.content)

    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / f"{operation_id}-signed.pdf").write_bytes(download.content)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
