"""Клиент ncins-core-api для NCINS-305 / NCINS-277."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

GENERATE_FORM_PATH = "/v1/doc/generate-form"
DOWNLOAD_PATH = "/v1/doc/download"

DEFAULT_BASE_URL = (
    "https://int.ufrulkint-api.moscow.alfaintra.net/ufr-eos-ul-ncins-core-api"
)
EXAMPLE_FILE_ID = "285946b0-002e-428c-b1e1-d5c558e81c24"


def load_dotenv(path: str = ".env") -> None:
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class NcinsConfig:
    base_url: str
    timeout: float
    verify_ssl: bool
    user_id: str
    customer_id: str
    client_type: str
    channel_id: str
    cus: str
    manager_ad_login: str
    manager_fio: str
    manager_position: str
    manager_branch_name: str
    manager_branch_code: str
    group: str
    file_id: str | None

    @classmethod
    def from_env(cls, base_url: str | None = None) -> "NcinsConfig":
        file_id = os.getenv("NCINS_FILE_ID", "").strip() or None
        return cls(
            base_url=(base_url or os.getenv("NCINS_BASE_URL") or DEFAULT_BASE_URL).rstrip(
                "/"
            ),
            timeout=float(os.getenv("NCINS_TIMEOUT", "60")),
            verify_ssl=_env_bool("NCINS_VERIFY_SSL", default=False),
            user_id=os.getenv("NCINS_A_USER_ID", "123456"),
            customer_id=os.getenv("NCINS_A_CUSTOMER_ID", "123456"),
            client_type=os.getenv("NCINS_A_CLIENT_TYPE", "UL"),
            channel_id=os.getenv("NCINS_A_CHANNEL_ID", "NIB"),
            cus=os.getenv("NCINS_CUS", "UAAAJ7"),
            manager_ad_login=os.getenv("NCINS_MANAGER_AD_LOGIN", "eosManager"),
            manager_fio=os.getenv(
                "NCINS_MANAGER_FIO", "Акрилов Эдуард Петрович"
            ),
            manager_position=os.getenv(
                "NCINS_MANAGER_POSITION",
                "Менеджер отделения по обслуживанию ЮЛ",
            ),
            manager_branch_name=os.getenv("NCINS_MANAGER_BRANCH_NAME", "0262"),
            manager_branch_code=os.getenv("NCINS_MANAGER_BRANCH_CODE", "MONY"),
            group=os.getenv("NCINS_GROUP", "UFCASH_DEPUTY_HEAD"),
            file_id=file_id,
        )

    def ufr_headers(self) -> dict[str, str]:
        return {
            "A-userId": self.user_id,
            "A-customerId": self.customer_id,
            "A-clientType": self.client_type,
            "A-channelId": self.channel_id,
        }

    def generate_form_payload(self, include_file_attributes: bool = True) -> dict[str, Any]:
        """Тело из комментария NCINS-277 (curl generate-form)."""
        payload: dict[str, Any] = {
            "customerData": {"cus": self.cus},
            "managerData": {
                "adLogin": self.manager_ad_login,
                "operatorFio": self.manager_fio,
                "operatorPosition": self.manager_position,
                "operatorBranchName": self.manager_branch_name,
                "operatorBranchCode": self.manager_branch_code,
            },
            "groups": [self.group],
        }
        if include_file_attributes:
            payload["fileAttributes"] = [
                {
                    "contractNumber": "TEST-NCINS-305",
                    "currentDate": "2026-06-09",
                    "paymentAccount": "40702810900000000001",
                    "beginDate": "2026-06-09",
                    "endDate": "2026-06-09",
                    "insuranceSum": 100000.00,
                    "insurancePremium": 10000.00,
                    "cadastralNumber": "77:01:0001001:1234",
                    "area": 50,
                    "realEstateAddress": "г. Москва, ул. Тестовая, д. 1",
                    "realEstateType": "office",
                    "employee": {
                        "employeeFIO": "Иванов Иван Иванович",
                        "employeeEmail": "ivanov@example.ru",
                        "employeePhoneNumber": "79999999999",
                        "employeeBirthDate": "1990-01-15",
                    },
                }
            ]
        return payload


class NcinsClient:
    def __init__(self, config: NcinsConfig | None = None) -> None:
        self.config = config or NcinsConfig.from_env()
        self.session = requests.Session()
        self.session.verify = self.config.verify_ssl
        self.session.headers.update(self.config.ufr_headers())

    def _url(self, path: str) -> str:
        return f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}"

    def generate_form(
        self,
        payload: dict[str, Any] | None = None,
        include_file_attributes: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> requests.Response:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)
        body = payload if payload is not None else self.config.generate_form_payload(
            include_file_attributes=include_file_attributes
        )
        return self.session.post(
            self._url(GENERATE_FORM_PATH),
            json=body,
            headers=headers,
            timeout=self.config.timeout,
        )

    def download(
        self,
        file_id: Any,
        extra_headers: dict[str, str] | None = None,
        raw_json: dict[str, Any] | None = None,
        send_json: bool = True,
    ) -> requests.Response:
        """POST /v1/doc/download — метод NCINS-305."""
        headers = {
            "Accept": "application/pdf",
            "Content-Type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)

        if raw_json is not None:
            body = raw_json
        elif file_id is None and send_json:
            body = {}
        else:
            body = {"fileId": file_id}

        kwargs: dict[str, Any] = {
            "headers": headers,
            "timeout": self.config.timeout,
        }
        if send_json:
            kwargs["json"] = body
        return self.session.post(self._url(DOWNLOAD_PATH), **kwargs)
