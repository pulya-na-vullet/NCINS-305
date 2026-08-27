"""Сбор результатов pytest и HTML/JSON/Markdown-отчёт NCINS-305 / NCINS-306."""

from __future__ import annotations

import html
import json
import os
import platform
import sys
from collections import defaultdict
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

SUITE_306 = "NCINS-306 · download-signed"
SUITE_305 = "NCINS-305 · download"
SUITE_277 = "NCINS-277 · generate-form"
SUITE_INFRA = "Клиент / инфраструктура"

SUITE_ORDER = [SUITE_306, SUITE_305, SUITE_277, SUITE_INFRA]

SUITE_META = {
    SUITE_306: {
        "heading": "NCINS-306 · Получение подписанных документов",
        "subtitle": "POST /v1/doc/download-signed — новые тесты по задаче 306",
        "highlight": True,
    },
    SUITE_305: {
        "heading": "NCINS-305 · Получение документа из AC",
        "subtitle": "POST /v1/doc/download",
        "highlight": False,
    },
    SUITE_277: {
        "heading": "NCINS-277 · Создание печатной формы",
        "subtitle": "POST /v1/doc/generate-form",
        "highlight": False,
    },
    SUITE_INFRA: {
        "heading": "Клиент / инфраструктура",
        "subtitle": "URL, mock PDF, служебные проверки",
        "highlight": False,
    },
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
    if (
        "download_signed" in blob
        or "ncins-306" in blob
        or "ncins_306" in blob
        or "live_download_signed" in blob
    ):
        return SUITE_306
    if "generate_form" in blob or "ncins-277" in blob:
        return SUITE_277
    if "test_download" in blob or "live_generate" in blob or "example_file" in blob:
        return SUITE_305
    return SUITE_INFRA


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


def _sorted_tests(tests: list[TestResult]) -> list[TestResult]:
    rank = {name: i for i, name in enumerate(SUITE_ORDER)}
    return sorted(
        tests,
        key=lambda t: (rank.get(t.suite, 99), t.nodeid),
    )


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    started = _collector["started"] or datetime.now(timezone.utc)
    finished = datetime.now(timezone.utc)
    tests = _sorted_tests(list(_collector["results"].values()))
    passed = sum(1 for t in tests if t.status == "passed")
    failed = sum(1 for t in tests if t.status == "failed")
    skipped = sum(1 for t in tests if t.status == "skipped")
    errors = sum(1 for t in tests if t.status == "error")
    live = os.getenv("NCINS_LIVE", "").strip().lower() in {"1", "true", "yes", "on"}
    report = RunReport(
        title="NCINS-305 / NCINS-306 · документы из AlfaCapture",
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
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for test in report.tests:
        grouped[test.suite].append(asdict(test))
    data["suites"] = {
        suite: grouped.get(suite, []) for suite in SUITE_ORDER if suite in grouped
    }
    return data


def _grouped(tests: list[TestResult]) -> dict[str, list[TestResult]]:
    buckets: dict[str, list[TestResult]] = defaultdict(list)
    for test in tests:
        buckets[test.suite].append(test)
    return buckets


def _suite_counts(tests: list[TestResult]) -> dict[str, int]:
    return {
        "total": len(tests),
        "passed": sum(1 for t in tests if t.status == "passed"),
        "failed": sum(1 for t in tests if t.status == "failed"),
        "skipped": sum(1 for t in tests if t.status == "skipped"),
        "errors": sum(1 for t in tests if t.status == "error"),
    }


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
    ]
    grouped = _grouped(report.tests)
    index = 1
    for suite in SUITE_ORDER:
        suite_tests = grouped.get(suite) or []
        if not suite_tests:
            continue
        meta = SUITE_META[suite]
        counts = _suite_counts(suite_tests)
        marker = " ★ НОВЫЕ ТЕСТЫ" if meta["highlight"] else ""
        lines.extend(
            [
                f"## {meta['heading']}{marker}",
                "",
                f"*{meta['subtitle']}*",
                "",
                f"Кейсов: **{counts['total']}** · успех {counts['passed']} · "
                f"падение {counts['failed']} · пропуск {counts['skipped']}",
                "",
                "| # | Статус | Кейс | Время | Комментарий |",
                "| ---: | --- | --- | ---: | --- |",
            ]
        )
        for test in suite_tests:
            comment = test.skip_reason or (
                test.error.splitlines()[0] if test.error else ""
            )
            comment = comment.replace("|", "\\|")[:180]
            lines.append(
                f"| {index} | {STATUS_LABELS.get(test.status, test.status)} | "
                f"{test.title} | {test.duration_s:.3f} с | {comment} |"
            )
            index += 1
        lines.append("")
    return "\n".join(lines)


def render_html(report: RunReport) -> str:
    grouped = _grouped(report.tests)
    highlight_html = _suite_block(
        SUITE_306, grouped.get(SUITE_306) or [], start_index=1
    )
    other_start = 1 + len(grouped.get(SUITE_306) or [])
    other_parts = []
    cursor = other_start
    for suite in SUITE_ORDER:
        if suite == SUITE_306:
            continue
        suite_tests = grouped.get(suite) or []
        if not suite_tests:
            continue
        other_parts.append(_suite_block(suite, suite_tests, start_index=cursor))
        cursor += len(suite_tests)

    counts_306 = _suite_counts(grouped.get(SUITE_306) or [])
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
      --new: #8a4b08;
      --new-bg: #fff4d6;
      --new-line: #e0b34a;
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
      margin-right: 8px;
      padding: 6px 12px;
      border-radius: 999px;
      font-weight: 700;
      letter-spacing: .04em;
      font-size: 13px;
    }}
    .badge.ok {{ background: #1b7f4e; }}
    .badge.bad {{ background: #c62828; }}
    .badge.new {{ background: #d29a1a; color: #1c1404; }}
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
    .kpi.new {{
      border: 2px solid var(--new-line);
      background: var(--new-bg);
    }}
    .kpi.new .n {{ color: var(--new); }}
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
    .filters button.filter-306.active {{ background: #8a4b08; border-color: #8a4b08; }}
    .suite-block {{ margin: 0 0 28px; }}
    .suite-block.highlight {{
      border: 2px solid var(--new-line);
      border-radius: 16px;
      padding: 16px 16px 8px;
      background: linear-gradient(180deg, #fff8e6 0%, #ffffff 48px);
      box-shadow: 0 8px 24px rgba(138, 75, 8, 0.08);
    }}
    .suite-head {{
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      gap: 10px 16px;
      margin: 4px 0 12px;
    }}
    .suite-head h2 {{ margin: 0; font-size: 18px; }}
    .suite-head .sub {{ color: var(--muted); font-size: 13px; }}
    .pill-new {{
      display: inline-block;
      background: #8a4b08;
      color: #fff8e6;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: .08em;
      padding: 3px 8px;
      border-radius: 999px;
      text-transform: uppercase;
    }}
    .suite-stats {{ color: var(--muted); font-size: 13px; margin-left: auto; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 12px;
      overflow: hidden;
    }}
    .highlight table {{ border-color: var(--new-line); }}
    th, td {{ padding: 10px 12px; text-align: left; vertical-align: top; font-size: 14px; }}
    th {{ background: #eef2f8; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
    .highlight th {{ background: #f6e7c4; color: var(--new); }}
    tr.case {{ cursor: pointer; border-top: 1px solid var(--line); }}
    tr.case:hover {{ background: #f7f9fc; }}
    .highlight tr.case:hover {{ background: #fff6dc; }}
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
    h3.rest {{ margin: 28px 0 12px; font-size: 16px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(report.title)}</h1>
    <p>Режим: {html.escape(report.mode)} · Python {html.escape(report.python)} · {html.escape(report.platform)}</p>
    <p>Старт {html.escape(report.started_at)} · финиш {html.escape(report.finished_at)} · {report.duration_s:.2f} с</p>
    <span class="badge {verdict_class}">{verdict}</span>
    <span class="badge new">NCINS-306 · {counts_306["total"]} новых тестов</span>
  </header>
  <main>
    <section class="kpis">
      <div class="kpi"><div class="n">{report.total}</div><div class="l">Всего</div></div>
      <div class="kpi passed"><div class="n">{report.passed}</div><div class="l">Успех</div></div>
      <div class="kpi failed"><div class="n">{report.failed}</div><div class="l">Падение</div></div>
      <div class="kpi skipped"><div class="n">{report.skipped}</div><div class="l">Пропуск</div></div>
      <div class="kpi new"><div class="n">{counts_306["total"]}</div><div class="l">NCINS-306 новые</div></div>
      <div class="kpi"><div class="n">{report.duration_s:.2f}с</div><div class="l">Время</div></div>
    </section>
    <div class="filters">
      <button class="active" data-filter="all">Все</button>
      <button class="filter-306" data-filter="suite" data-suite="{html.escape(SUITE_306)}">NCINS-306 новые</button>
      <button data-filter="suite" data-suite="{html.escape(SUITE_305)}">NCINS-305</button>
      <button data-filter="suite" data-suite="{html.escape(SUITE_277)}">NCINS-277</button>
      <button data-filter="passed">Успех</button>
      <button data-filter="failed">Падения</button>
      <button data-filter="skipped">Пропуски</button>
    </div>
    {highlight_html}
    <h3 class="rest rest-heading">Остальные наборы</h3>
    {"".join(other_parts)}
  </main>
  <script>
    document.querySelectorAll("tr.case").forEach(row => {{
      row.addEventListener("click", () => {{
        const next = row.nextElementSibling;
        if (next && next.classList.contains("details")) next.classList.toggle("hidden");
      }});
    }});
    const applyFilter = (btn) => {{
      document.querySelectorAll(".filters button").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const f = btn.dataset.filter;
      const suite = btn.dataset.suite || "";
      document.querySelectorAll("tr.case").forEach(row => {{
        let show = true;
        if (f === "suite") show = row.dataset.suite === suite;
        else if (f === "passed" || f === "skipped") show = row.dataset.status === f;
        else if (f === "failed") show = row.dataset.status === "failed" || row.dataset.status === "error";
        row.style.display = show ? "" : "none";
        const details = row.nextElementSibling;
        if (details && details.classList.contains("details")) {{
          details.style.display = show ? "" : "none";
          if (!show) details.classList.add("hidden");
        }}
      }});
      document.querySelectorAll(".suite-block").forEach(block => {{
        const anyVisible = [...block.querySelectorAll("tr.case")].some(r => r.style.display !== "none");
        block.style.display = anyVisible ? "" : "none";
      }});
      const rest = document.querySelector(".rest-heading");
      if (rest) {{
        const othersVisible = [...document.querySelectorAll(".suite-block:not(.highlight)")].some(b => b.style.display !== "none");
        rest.style.display = othersVisible ? "" : "none";
      }}
    }};
    document.querySelectorAll(".filters button").forEach(btn => {{
      btn.addEventListener("click", () => applyFilter(btn));
    }});
  </script>
</body>
</html>
"""


def _suite_block(
    suite: str,
    tests: list[TestResult],
    start_index: int,
) -> str:
    if not tests:
        return ""
    meta = SUITE_META[suite]
    counts = _suite_counts(tests)
    highlight_class = " highlight" if meta["highlight"] else ""
    new_pill = '<span class="pill-new">Новые тесты</span>' if meta["highlight"] else ""
    rows = "\n".join(
        _test_row(start_index + i, test) for i, test in enumerate(tests)
    )
    return f"""
    <section class="suite-block{highlight_class}" data-suite-block="{html.escape(suite)}">
      <div class="suite-head">
        {new_pill}
        <h2>{html.escape(meta["heading"])}</h2>
        <span class="sub">{html.escape(meta["subtitle"])}</span>
        <span class="suite-stats">{counts["total"]} кейсов · успех {counts["passed"]} · падение {counts["failed"]} · пропуск {counts["skipped"]}</span>
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
    </section>
    """


def _test_row(index: int, test: TestResult) -> str:
    error_html = ""
    if test.error:
        error_html = f"<p><b>Ошибка</b></p><pre>{html.escape(test.error)}</pre>"
    if test.skip_reason:
        error_html += f"<p class='muted'>Пропуск: {html.escape(test.skip_reason)}</p>"
    http_html = _http_html(test.http_calls)
    details = error_html + http_html
    return f"""
        <tr class="case" data-status="{html.escape(test.status)}" data-suite="{html.escape(test.suite)}">
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
