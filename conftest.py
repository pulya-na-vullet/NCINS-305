from __future__ import annotations

pytest_plugins = ["reporter"]

import os
from pathlib import Path

import pytest

from mock_server import KNOWN_FILE_ID, KNOWN_OPERATION_ID, MockNcinsServer
from ncins_client import NcinsClient, NcinsConfig

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
LIVE = os.getenv("NCINS_LIVE", "").strip().lower() in {"1", "true", "yes", "on"}
ROOT = Path(__file__).resolve().parent
SIGNED_SAMPLE_PDF = ROOT / "response.pdf"


def is_pdf(content: bytes) -> bool:
    return content[:4] == b"%PDF"


@pytest.fixture(scope="session")
def mock_base_url() -> str:
    server = MockNcinsServer()
    url = server.start()
    yield url
    server.stop()


@pytest.fixture
def client(mock_base_url: str, request: pytest.FixtureRequest) -> NcinsClient:
    """Клиент на локальный mock. Живой стенд — только тесты с маркером live."""
    ncins_client = NcinsClient(NcinsConfig.from_env(base_url=mock_base_url))
    request.node.http_calls = ncins_client.history
    return ncins_client


@pytest.fixture
def file_id(client: NcinsClient) -> str:
    """fileId из generate-form (NCINS-277), иначе известный пример из NCINS-305."""
    if client.config.file_id:
        return client.config.file_id

    response = client.generate_form(include_file_attributes=True)
    if response.status_code == 200:
        document_ids = response.json().get("documentIds") or []
        if document_ids:
            return str(document_ids[0])
    return KNOWN_FILE_ID


@pytest.fixture
def operation_id(client: NcinsClient) -> str:
    """operationId из generate-form — вход для download-signed (NCINS-306)."""
    if client.config.operation_id:
        return client.config.operation_id

    response = client.generate_form(include_file_attributes=True)
    if response.status_code == 200:
        oid = response.json().get("operationId")
        if oid:
            return str(oid)
    return KNOWN_OPERATION_ID
