"""Локальный mock ncins-core-api для офлайн-прогона тестов NCINS-305 / NCINS-306."""

from __future__ import annotations

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj<<>>endobj\n"
    b"trailer<<>>\n"
    b"%%EOF\n"
)

KNOWN_FILE_ID = "285946b0-002e-428c-b1e1-d5c558e81c24"
UNKNOWN_FILE_ID = "00000000-0000-4000-8000-000000000000"
KNOWN_OPERATION_ID = "6a8f275decea715b0ef88213"
UNKNOWN_OPERATION_ID = "000000000000000000000000"

_SIGNED_SAMPLE = Path(__file__).resolve().parent / "response.pdf"
SIGNED_PDF_BYTES = (
    _SIGNED_SAMPLE.read_bytes() if _SIGNED_SAMPLE.is_file() else PDF_BYTES
)


class MockNcinsHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    generated_ids: set[str] = {KNOWN_FILE_ID}
    generated_operation_ids: set[str] = {KNOWN_OPERATION_ID}

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _read_json(self) -> Any:
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return "__invalid__"

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json")

    def _send_pdf(self, filename: str, content: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path.rstrip("/") == "/v1/doc/generate-form":
            self._handle_generate_form()
            return
        if path.rstrip("/") == "/v1/doc/download":
            self._handle_download()
            return
        if path.rstrip("/") == "/v1/doc/download-signed":
            self._handle_download_signed()
            return
        self._send_json(404, {"error": "not found", "path": path})

    def do_GET(self) -> None:  # noqa: N802
        self._send_json(405, {"error": "method not allowed"})

    def _handle_generate_form(self) -> None:
        payload = self._read_json()
        if payload == "__invalid__" or not isinstance(payload, dict):
            self._send_json(400, {"error": "invalid json"})
            return
        for required in ("customerData", "managerData", "groups"):
            if required not in payload:
                self._send_json(
                    400,
                    {"error": "bad request", "missing": required},
                )
                return
        if not payload.get("groups"):
            self._send_json(400, {"error": "bad request", "missing": "groups"})
            return

        file_id = str(uuid.uuid4())
        operation_id = uuid.uuid4().hex
        self.generated_ids.add(file_id)
        self.generated_operation_ids.add(operation_id)
        self._send_json(
            200,
            {
                "operationId": operation_id,
                "createdDate": 1787303150880,
                "documentIds": [file_id],
            },
        )

    def _handle_download(self) -> None:
        accept = (self.headers.get("Accept") or "").lower()
        content_type = (self.headers.get("Content-Type") or "").lower()
        if "application/json" not in content_type:
            self._send_json(400, {"error": "content-type must be application/json"})
            return

        payload = self._read_json()
        if payload == "__invalid__" or not isinstance(payload, dict):
            self._send_json(400, {"error": "invalid json"})
            return

        if "fileId" not in payload:
            self._send_json(400, {"error": "fileId is required"})
            return

        file_id = payload.get("fileId")
        if file_id is None or str(file_id).strip() == "":
            self._send_json(400, {"error": "fileId is required"})
            return

        file_id = str(file_id)
        try:
            uuid.UUID(file_id)
        except ValueError:
            self._send_json(400, {"error": "fileId must be uuid"})
            return

        if file_id not in self.generated_ids:
            self._send_json(404, {"error": "document not found", "fileId": file_id})
            return

        if "application/pdf" not in accept and "*/*" not in accept and accept:
            self._send_json(406, {"error": "not acceptable"})
            return

        self._send_pdf(f"{file_id}.pdf", PDF_BYTES)

    def _handle_download_signed(self) -> None:
        accept = (self.headers.get("Accept") or "").lower()
        content_type = (self.headers.get("Content-Type") or "").lower()
        if "application/json" not in content_type:
            self._send_json(400, {"error": "content-type must be application/json"})
            return

        payload = self._read_json()
        if payload == "__invalid__" or not isinstance(payload, dict):
            self._send_json(400, {"error": "invalid json"})
            return

        if "operationId" not in payload:
            self._send_json(400, {"error": "operationId is required"})
            return

        operation_id = payload.get("operationId")
        if operation_id is None or str(operation_id).strip() == "":
            self._send_json(400, {"error": "operationId is required"})
            return

        operation_id = str(operation_id).strip()
        if operation_id not in self.generated_operation_ids:
            self._send_json(
                404,
                {"error": "signed document not found", "operationId": operation_id},
            )
            return

        if "application/pdf" not in accept and "*/*" not in accept and accept:
            self._send_json(406, {"error": "not acceptable"})
            return

        self._send_pdf(f"{operation_id}-signed.pdf", SIGNED_PDF_BYTES)


class MockNcinsServer:
    def __init__(self) -> None:
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), MockNcinsHandler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._httpd.server_address[:2]
        return f"http://{host}:{port}"

    def start(self) -> str:
        MockNcinsHandler.generated_ids = {KNOWN_FILE_ID}
        MockNcinsHandler.generated_operation_ids = {KNOWN_OPERATION_ID}
        self._thread.start()
        return self.base_url

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
