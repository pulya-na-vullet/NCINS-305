"""Сбор результатов pytest и HTML/JSON/Markdown-отчёт NCINS-305."""

from __future__ import annotations

import html
import json
import os
import platform
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"

STATUS_LABELS = {
    "passed": "Успех",
    "failed": "Падение",
    "skipped": "Пропуск",
    "error": "Ошибка",
}


@dataclass
class HttpCallDump:
    method: str
    url: str
    request_headers: dict[str, str]
    request_body: Any
    status_code: int
    response_headers: dict[str, str]
    response_preview: str
    elapsed_ms: float


@dataclass
class TestResult:
    nodeid: str
    title: str
    suite: str
    status: str
    duration_s: float
    skip_reason: str = ""
    error: str = ""
    http_calls: list[HttpCallDump] = field(default_factory=list)


@dataclass
class RunReport:
    title: str
    started_at: str
    finished_at: str
    duration_s: float
    mode: str
    python: str
    platform: str
    total: int
    passed: int
    failed: int
    skipped: int
    errors: int
    tests: list[TestResult]


_collector: dict[str, Any] = {
    "started": None,
    "results": {},
}


def _title_of(item: Any) -> str:
    func = getattr(item, "function", None) or getattr(item, "obj", None)
    doc = (getattr(func, "__doc__", None) or "").strip()
    name = item.name
    param = name[name.find("[") :] if "[" in name else ""
    if doc:
        first = doc.splitlines()[0].strip()
        return f"{first} {param}".strip()
    return name


def _suite_of(nodeid: str, title: str) -> str:
    blob = f"{nodeid} {title}".lower()
    if "generate_form" in blob or "ncins-277" in blob:
        return "NCINS-277 · generate-form"
    if "test_download" in blob or "live_generate" in blob or "example_file" in blob:
        return "NCINS-305 · download"
    return "Клиент / инфраструктура"


def pytest_sessionstart(session: Any) -> None:
    _collector["started"] = datetime.now(timezone.utc)
    _collector["results"] = {}


def pytest_collection_modifyitems(items: list[Any]) -> None:
    for item in items:
        item._ncins_title = _title_of(item)
        item._ncins_suite = _suite_of(item.nodeid, item._ncins_title)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: Any, call: Any):
    outcome = yield
    report = outcome.get_result()
    current = _collector["results"].setdefault(
        item.nodeid,
        TestResult(
            nodeid=item.nodeid,
            title=getattr(item, "_ncins_title", item.name),
            suite=getattr(item, "_ncins_suite", "Прочее"),
            status="passed",
            duration_s=0.0,
        ),
    )
    if report.when == "call":
        current.duration_s += getattr(report, "duration", 0.0) or 0.0

    calls = getattr(item, "http_calls", None) or []
    if calls:
        current.http_calls = [
            HttpCallDump(
                method=c.method,
                url=c.url,
                request_headers=c.request_headers,
                request_body=c.request_body,
                status_code=c.status_code,
                response_headers=c.response_headers,
                response_preview=c.response_preview,
                elapsed_ms=c.elapsed_ms,
            )
            for c in calls
        ]

    if report.when != "call" and not (report.failed and report.when == "setup"):
        if report.skipped and report.when == "setup":
            current.status = "skipped"
            current.skip_reason = _skip_reason(report)
        return

    if report.skipped:
        current.status = "skipped"
        current.skip_reason = _skip_reason(report)
    elif report.failed:
        current.status = "failed" if report.when == "call" else "error"
        current.error = str(report.longrepr) if report.longrepr else "failed"
    elif report.passed and current.status not in {"failed", "error", "skipped"}:
        current.status = "passed"


def _skip_reason(report: Any) -> str:
    try:
        return str(report.longrepr[2]).replace("Skipped: ", "").strip()
    except Exception:
        return "skipped"


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    started = _collector["started"] or datetime.now(timezone.utc)
    finished = datetime.now(timezone.utc)
    tests = list(_collector["results"].values())
    passed = sum(1 for t in tests if t.status == "passed")
    failed = sum(1 for t in tests if t.status == "failed")
    skipped = sum(1 for t in tests if t.status == "skipped")
    errors = sum(1 for t in tests if t.status == "error")
    live = os.getenv("NCINS_LIVE", "").strip().lower() in {"1", "true", "yes", "on"}
    report = RunReport(
        title="NCINS-305 · Получение документа из AlfaCapture",
        started_at=started.astimezone().strftime("%d.%m.%Y %H:%M:%S %Z"),
        finished_at=finished.astimezone().strftime("%d.%m.%Y %H:%M:%S %Z"),
        duration_s=(finished - started).total_seconds(),
        mode="INT / live" if live else "mock (локальный контур)",
        python=sys.version.split()[0],
        platform=f"{platform.system()} {platform.release()}",
        total=len(tests),
        passed=passed,
        failed=failed,
        skipped=skipped,
        errors=errors,
        tests=tests,
    )
    write_reports(report)


def write_reports(report: RunReport) -> dict[str, Path]:
    REPORTS_DIR.mkdir(exist_ok=True)
    html_path = REPORTS_DIR / "NCINS-305-report.html"
    json_path = REPORTS_DIR / "NCINS-305-report.json"
    md_path = REPORTS_DIR / "NCINS-305-report.md"
    html_path.write_text(render_html(report), encoding="utf-8")
    json_path.write_text(
        json.dumps(_report_dict(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"html": html_path, "json": json_path, "md": md_path}


def _report_dict(report: RunReport) -> dict[str, Any]:
    data = asdict(report)
    return data


def render_markdown(report: RunReport) -> str:
    lines = [
        f"# {report.title}",
        "",
        f"- Режим: **{report.mode}**",
        f"- Старт: {report.started_at}",
        f"- Финиш: {report.finished_at}",
        f"- Длительность: {report.duration_s:.2f} с",
        f"- Python: {report.python} · {report.platform}",
        "",
        f"| Всего | Успех | Падение | Пропуск | Ошибка |",
        f"| ---: | ---: | ---: | ---: | ---: |",
        f"| {report.total} | {report.passed} | {report.failed} | {report.skipped} | {report.errors} |",
        "",
        "| Статус | Набор | Кейс | Время | Комментарий |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for test in report.tests:
        comment = test.skip_reason or (
            test.error.splitlines()[0] if test.error else ""
        )
        comment = comment.replace("|", "\\|")[:180]
        lines.append(
            f"| {STATUS_LABELS.get(test.status, test.status)} | {test.suite} | "
            f"{test.title} | {test.duration_s:.3f} с | {comment} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_html(report: RunReport) -> str:
    rows = "\n".join(_test_row(i, test) for i, test in enumerate(report.tests, 1))
    verdict = (
        "ПРОЙДЕНО"
        if report.failed == 0 and report.errors == 0
        else "ЕСТЬ ПАДЕНИЯ"
    )
    verdict_class = "ok" if verdict == "ПРОЙДЕНО" else "bad"
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(report.title)}</title>
  <style>
    :root {{
      --bg: #f4f6fb;
      --card: #fff;
      --ink: #1c2434;
      --muted: #5c6b80;
      --line: #e4e9f2;
      --pass: #1b7f4e;
      --pass-bg: #e8f6ee;
      --fail: #c62828;
      --fail-bg: #fdecea;
      --skip: #b78103;
      --skip-bg: #fff6e0;
      --accent: #1f4b99;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "PT Sans", Arial, sans-serif;
      background: var(--bg);
      color: var(--ink);
    }}
    header {{
      background: linear-gradient(120deg, #14233d, #1f4b99);
      color: #fff;
      padding: 28px 32px 24px;
    }}
    header h1 {{ margin: 0 0 8px; font-size: 22px; font-weight: 650; }}
    header p {{ margin: 4px 0; color: #d7e3fb; font-size: 14px; }}
    .badge {{
      display: inline-block;
      margin-top: 12px;
      padding: 6px 12px;
      border-radius: 999px;
      font-weight: 700;
      letter-spacing: .04em;
      font-size: 13px;
    }}
    .badge.ok {{ background: #1b7f4e; }}
    .badge.bad {{ background: #c62828; }}
    main {{ padding: 24px 32px 48px; max-width: 1200px; margin: 0 auto; }}
    .kpis {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 12px;
      margin-bottom: 20px;
    }}
    .kpi {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px 16px;
    }}
    .kpi .n {{ font-size: 28px; font-weight: 700; line-height: 1.1; }}
    .kpi .l {{ color: var(--muted); font-size: 12px; margin-top: 4px; text-transform: uppercase; letter-spacing: .06em; }}
    .kpi.passed .n {{ color: var(--pass); }}
    .kpi.failed .n {{ color: var(--fail); }}
    .kpi.skipped .n {{ color: var(--skip); }}
    .filters {{ margin: 8px 0 16px; display: flex; gap: 8px; flex-wrap: wrap; }}
    .filters button {{
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 8px;
      padding: 6px 12px;
      cursor: pointer;
      font: inherit;
    }}
    .filters button.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 12px;
      overflow: hidden;
    }}
    th, td {{ padding: 10px 12px; text-align: left; vertical-align: top; font-size: 14px; }}
    th {{ background: #eef2f8; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
    tr.case {{ cursor: pointer; border-top: 1px solid var(--line); }}
    tr.case:hover {{ background: #f7f9fc; }}
    .st {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-weight: 650;
      font-size: 12px;
    }}
    .st.passed {{ background: var(--pass-bg); color: var(--pass); }}
    .st.failed, .st.error {{ background: var(--fail-bg); color: var(--fail); }}
    .st.skipped {{ background: var(--skip-bg); color: var(--skip); }}
    tr.details td {{ background: #fafbfe; border-top: 0; }}
    tr.details.hidden {{ display: none; }}
    pre {{
      margin: 8px 0 0;
      padding: 10px 12px;
      background: #121826;
      color: #e8eefc;
      border-radius: 8px;
      overflow: auto;
      font-size: 12px;
      max-height: 280px;
    }}
    .http {{
      display: grid;
      gap: 12px;
      margin-top: 8px;
    }}
    .http article {{
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px 12px;
      background: #fff;
    }}
    .http h4 {{ margin: 0 0 6px; font-size: 13px; }}
    .muted {{ color: var(--muted); }}
    footer {{ margin-top: 18px; color: var(--muted); font-size: 12px; }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(report.title)}</h1>
    <p>Режим: {html.escape(report.mode)} · Python {html.escape(report.python)} · {html.escape(report.platform)}</p>
    <p>Старт {html.escape(report.started_at)} · финиш {html.escape(report.finished_at)} · {report.duration_s:.2f} с</p>
    <span class="badge {verdict_class}">{verdict}</span>
  </header>
  <main>
    <section class="kpis">
      <div class="kpi"><div class="n">{report.total}</div><div class="l">Всего</div></div>
      <div class="kpi passed"><div class="n">{report.passed}</div><div class="l">Успех</div></div>
      <div class="kpi failed"><div class="n">{report.failed}</div><div class="l">Падение</div></div>
      <div class="kpi skipped"><div class="n">{report.skipped}</div><div class="l">Пропуск</div></div>
      <div class="kpi"><div class="n">{report.duration_s:.2f}с</div><div class="l">Время</div></div>
    </section>
    <div class="filters">
      <button class="active" data-filter="all">Все</button>
      <button data-filter="passed">Успех</button>
      <button data-filter="failed">Падения</button>
      <button data-filter="skipped">Пропуски</button>
    </div>
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Статус</th>
          <th>Набор</th>
          <th>Кейс</th>
          <th>Время</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
    <footer>Сформировано app.py · клик по строке раскрывает HTTP-запросы и ошибку. Отчёт самодостаточный, без внешних скриптов.</footer>
  </main>
  <script>
    document.querySelectorAll("tr.case").forEach(row => {{
      row.addEventListener("click", () => {{
        const next = row.nextElementSibling;
        if (next && next.classList.contains("details")) next.classList.toggle("hidden");
      }});
    }});
    document.querySelectorAll(".filters button").forEach(btn => {{
      btn.addEventListener("click", () => {{
        document.querySelectorAll(".filters button").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        const f = btn.dataset.filter;
        document.querySelectorAll("tr.case").forEach(row => {{
          const show = f === "all" || row.dataset.status === f || (f === "failed" && row.dataset.status === "error");
          row.style.display = show ? "" : "none";
          const details = row.nextElementSibling;
          if (details && details.classList.contains("details")) {{
            details.style.display = show ? "" : "none";
            if (!show) details.classList.add("hidden");
          }}
        }});
      }});
    }});
  </script>
</body>
</html>
"""


def _test_row(index: int, test: TestResult) -> str:
    error_html = ""
    if test.error:
        error_html = f"<p><b>Ошибка</b></p><pre>{html.escape(test.error)}</pre>"
    if test.skip_reason:
        error_html += f"<p class='muted'>Пропуск: {html.escape(test.skip_reason)}</p>"
    http_html = _http_html(test.http_calls)
    details = error_html + http_html or "<p class='muted'>Нет дополнительных данных.</p>"
    return f"""
        <tr class="case" data-status="{html.escape(test.status)}">
          <td>{index}</td>
          <td><span class="st {html.escape(test.status)}">{html.escape(STATUS_LABELS.get(test.status, test.status))}</span></td>
          <td>{html.escape(test.suite)}</td>
          <td>{html.escape(test.title)}<div class="muted">{html.escape(test.nodeid)}</div></td>
          <td>{test.duration_s:.3f} с</td>
        </tr>
        <tr class="details hidden"><td colspan="5">{details}</td></tr>
    """


def _http_html(calls: list[HttpCallDump]) -> str:
    if not calls:
        return ""
    blocks = []
    for i, call in enumerate(calls, 1):
        req_headers = json.dumps(call.request_headers, ensure_ascii=False, indent=2)
        resp_headers = json.dumps(call.response_headers, ensure_ascii=False, indent=2)
        body = (
            json.dumps(call.request_body, ensure_ascii=False, indent=2)
            if not isinstance(call.request_body, str)
            else call.request_body
        )
        blocks.append(
            f"""
            <article>
              <h4>{i}. {html.escape(call.method)} {html.escape(call.url)} → {call.status_code} ({call.elapsed_ms:.0f} мс)</h4>
              <p class="muted">Запрос</p>
              <pre>{html.escape(req_headers)}\n\n{html.escape(str(body))}</pre>
              <p class="muted">Ответ</p>
              <pre>{html.escape(resp_headers)}\n\n{html.escape(call.response_preview)}</pre>
            </article>
            """
        )
    return "<div class='http'><p><b>HTTP</b></p>" + "".join(blocks) + "</div>"
