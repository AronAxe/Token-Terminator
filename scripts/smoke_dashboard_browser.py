"""Standalone Chromium QA with explicitly synthetic records; no remote requests."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from dashboard_fixtures import RATES, populate

from rtk_hermes_plus.dashboard import DashboardReader, DashboardServer, asset


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chromium", default=None)
    parser.add_argument(
        "--offline-dom",
        action="store_true",
        help="Render fixture data without browser navigation; not an HTTP/CSP test.",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tt-dashboard-qa-") as temp:
        home = Path(temp)
        first, *_ = populate(home)
        populate(
            home / "profiles" / "brain",
            "brain",
            model="fixture/model-b",
            billing="subscription",
            multiplier=2,
        )
        (home / "token-terminator/dashboard.json").write_text(
            json.dumps({"rates": RATES})
        )
        # Spread the four exact request identities across recorded UTC days.
        with sqlite3.connect(first.vault) as db:
            for i in range(4):
                db.execute(
                    "UPDATE request_token_metrics SET measured_at=date('now',?)||'T12:00:00+00:00' WHERE request_id=?",
                    (f"-{i * 3} days", f"r{i}"),
                )
        server = DashboardServer(DashboardReader(home), 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    executable_path=args.chromium, headless=True, args=["--no-sandbox"]
                )
                page = browser.new_page(
                    viewport={"width": 1440, "height": 1100}, locale="en-US"
                )
                errors = []
                outbound = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.on(
                    "request",
                    lambda r: (
                        outbound.append(r.url) if not r.url.startswith(url) else None
                    ),
                )
                if args.offline_dom:
                    html = (
                        asset("index.html")
                        .decode()
                        .replace(
                            '<link rel="stylesheet" href="dashboard.css">',
                            "<style>" + asset("dashboard.css").decode() + "</style>",
                        )
                        .replace('<script src="dashboard.js" defer></script>', "")
                    )
                    page.set_content(html)
                    page.evaluate(
                        "data => { window.__fixture=data;window.fetch=async()=>({ok:true,json:async()=>structuredClone(window.__fixture)}); }",
                        server.reader.read(),
                    )
                    page.add_script_tag(content=asset("dashboard.js").decode())
                else:
                    page.goto(url)
                page.wait_for_function(
                    "document.querySelector('#saved').textContent === '7,200'"
                )
                assert page.locator("#output").inner_text() == "600"
                assert page.locator("#profiles tr").count() == 2
                assert page.locator(".bar").count() == 14
                assert page.locator("#value").inner_text() == "$0.0288"
                # Clearly identify screenshots as QA data, not the user's usage.
                page.locator(".eyebrow").evaluate(
                    "e => e.textContent='SYNTHETIC QA DATA · NOT LIVE USAGE'"
                )
                page.screenshot(
                    path=str(args.output / "dashboard-desktop.png"), full_page=True
                )
                page.locator("#profile").select_option("brain")
                assert page.locator("#saved").inner_text() == "4,800"
                assert page.locator("#output").inner_text() == "400"
                assert "subscription" in page.locator("#value-caption").inner_text()
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                )
                page.screenshot(
                    path=str(args.output / "dashboard-mobile.png"), full_page=True
                )
                page.evaluate(
                    """() => { const d=structuredClone(state);d.profiles[0].label='<img src=x onerror=alert(1)>';d.profiles[0].models[0].model='<script>alert(1)</script>';selected='';render(d); }"""
                )
                assert page.locator("#profiles img,#models script").count() == 0
                assert "<img" in page.locator("#profiles").inner_text()
                if args.offline_dom:
                    page.evaluate(
                        "() => { window.fetch=async()=>{throw new Error('fixture offline');}; }"
                    )
                else:
                    page.route("**/api/v1/summary", lambda route: route.abort())
                page.evaluate("refresh()")
                page.wait_for_function(
                    "document.querySelector('#status').textContent.includes('last snapshot')"
                )
                assert "stale" in page.locator("#notice").inner_text()
                assert page.locator("#saved").inner_text() == "7,200"
                assert not errors, errors
                assert not outbound, outbound
                report = {
                    "fixture_data": True,
                    "standalone_chromium": True,
                    "http_and_csp_exercised": not args.offline_dom,
                    "desktop_and_mobile": True,
                    "profiles_filter": True,
                    "exact_totals": True,
                    "xss_rendering_safe": True,
                    "stale_state": True,
                    "browser_errors": errors,
                    "external_requests": outbound,
                }
                browser.close()
                (args.output / "browser-checks.json").write_text(
                    json.dumps(report, indent=2) + "\n"
                )
                print(json.dumps(report))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    main()
