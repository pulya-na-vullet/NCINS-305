#!/usr/bin/env python3
"""Единая точка запуска тестов NCINS-305 / NCINS-306: прогон, отчёт, архив."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import webbrowser
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"
ARCHIVE_NAME = "NCINS-305-tests.zip"

SKIP_IN_ZIP = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".idea",
    ".vscode",
    "artifacts",
    ARCHIVE_NAME,
    ".env",
}


def ensure_deps() -> None:
    try:
        import pytest  # noqa: F401
        import requests  # noqa: F401
    except ImportError:
        req = ROOT / "requirements.txt"
        print("Устанавливаю зависимости из requirements.txt …")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", str(req)]
        )


def run_tests(live: bool) -> int:
    import pytest

    if live:
        os.environ["NCINS_LIVE"] = "1"
    REPORTS.mkdir(exist_ok=True)
    junit = REPORTS / "junit.xml"
    args = [
        str(ROOT / "test_ncins_306.py"),
        str(ROOT / "test_ncins_305.py"),
        "-v",
        "--tb=short",
        f"--junitxml={junit}",
        "-p",
        "no:cacheprovider",
    ]
    print()
    print("=== Прогон тестов NCINS-306 + NCINS-305 ===")
    print("Режим:", "INT / live" if live else "mock")
    print()
    return pytest.main(args)


def print_summary() -> Path | None:
    html_path = REPORTS / "NCINS-305-report.html"
    md_path = REPORTS / "NCINS-305-report.md"
    json_path = REPORTS / "NCINS-305-report.json"
    print()
    print("=== Отчёт ===")
    for path in (html_path, md_path, json_path, REPORTS / "junit.xml"):
        if path.exists():
            print(f"  {path.relative_to(ROOT)}")
    if md_path.exists():
        print()
        print(md_path.read_text(encoding="utf-8"))
    return html_path if html_path.exists() else None


def _should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if parts & SKIP_IN_ZIP:
        return True
    if path.suffix == ".pyc":
        return True
    if path.name == ARCHIVE_NAME:
        return True
    return False


def make_archive() -> Path:
    out = ROOT / ARCHIVE_NAME
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT)
            if _should_skip(rel):
                continue
            arcname = str(Path("NCINS-305") / rel)
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            if mtime.year < 1980:
                mtime = datetime.now()
            info = zipfile.ZipInfo(filename=arcname, date_time=mtime.timetuple()[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, path.read_bytes())
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="NCINS-305 / NCINS-306: запуск тестов, HTML-отчёт и zip-архив."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Прогнать E2E против INT-стенда (нужен доступ к alfaintra).",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Открыть HTML-отчёт в браузере после прогона.",
    )
    parser.add_argument(
        "--no-zip",
        action="store_true",
        help="Не собирать zip-архив.",
    )
    return parser.parse_args()


def main() -> int:
    os.chdir(ROOT)
    args = parse_args()
    ensure_deps()
    exit_code = run_tests(live=args.live)
    html_path = print_summary()
    if html_path and args.open:
        webbrowser.open(html_path.as_uri())
    if not args.no_zip:
        archive = make_archive()
        print()
        print("=== Архив ===")
        print(f"  {archive} ({archive.stat().st_size} байт)")
        print(f"  {datetime.now():%d.%m.%Y %H:%M:%S}")
    print()
    if exit_code == 0:
        print("Итог: ПРОЙДЕНО")
    else:
        print("Итог: ЕСТЬ ПАДЕНИЯ / ОШИБКИ")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
