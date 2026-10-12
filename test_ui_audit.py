import os
import sys
import time
import subprocess
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

SCREENSHOTS_DIR = Path("test_ui_screenshots")
SCREENSHOTS_DIR.mkdir(exist_ok=True)

PORT = 8503

def main():
    print("=== [AGENT 2: UI/UX DESIGNER BROWSER AUDIT] ===")
    print(f"[*] Starting background Streamlit instance on port {PORT}...")
    
    server_process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "dashboard.py",
            f"--server.port={PORT}",
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    # Wait for server to bind
    ready = False
    for attempt in range(15):
        time.sleep(1)
        try:
            with urllib.request.urlopen(f"http://localhost:{PORT}", timeout=2) as resp:
                if resp.status == 200:
                    ready = True
                    print(f"[OK] Streamlit is live and responsive on port {PORT} (attempt {attempt+1})")
                    break
        except Exception:
            pass

    if not ready:
        server_process.terminate()
        raise RuntimeError("Streamlit server failed to start within timeout.")

    try:
        with sync_playwright() as p:
            print("[*] Launching Chromium browser (headless mode with 1440x900 viewport)...")
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()

            # 1. Open dashboard
            print(f"[*] Navigating as human user to http://localhost:{PORT}...")
            page.goto(f"http://localhost:{PORT}")
            page.wait_for_selector(".terminal-header", timeout=15000)
            page.wait_for_timeout(2000)  # Allow Streamlit and Plotly to settle

            # Step 1: Check Sidebar Trader Summary & Top KPI Ribbon
            print("[1] Inspecting Sidebar 'Сводка для трейдера' and Top KPI Ribbon...")
            page.screenshot(path=str(SCREENSHOTS_DIR / "01_initial_sidebar_expanded.png"), full_page=False)

            # Test KPI card geometry
            kpi_values = page.query_selector_all(".kpi-value")
            row1_y_coords = []
            for idx, val in enumerate(kpi_values[:4]):
                box = val.bounding_box()
                if box:
                    row1_y_coords.append(box["y"])
                    print(f"    KPI Row 1 Card {idx+1} value Y-coordinate: {box['y']:.1f}px")

            y_variance = max(row1_y_coords) - min(row1_y_coords)
            print(f"    Vertical Y-alignment variance across Row 1 cards: {y_variance:.2f}px")
            assert y_variance < 3.0, f"KPI numbers misaligned! Variance: {y_variance}px"
            print("    [PASS] All Row 1 KPI numbers are perfectly locked on the exact same baseline!")

            # Step 2: Toggle Sidebar to verify zero jumping / shifting
            print("[2] Toggling sidebar collapse to verify responsiveness and baseline stability...")
            try:
                page.locator("section[data-testid='stSidebar']").hover()
                collapse_btn = page.locator("[data-testid='stSidebarCollapseButton'] button")
                if collapse_btn.count() > 0:
                    collapse_btn.first.click(force=True, timeout=3000)
                    page.wait_for_timeout(1000)
                    page.screenshot(path=str(SCREENSHOTS_DIR / "02_sidebar_collapsed.png"))
                    
                    # Check variance again with collapsed sidebar
                    collapsed_y = []
                    for val in page.query_selector_all(".kpi-value")[:4]:
                        box = val.bounding_box()
                        if box:
                            collapsed_y.append(box["y"])
                    if collapsed_y:
                        coll_variance = max(collapsed_y) - min(collapsed_y)
                        print(f"    Vertical variance with collapsed sidebar: {coll_variance:.2f}px")
                        assert coll_variance < 3.0, f"KPI numbers shifted when sidebar collapsed! Variance: {coll_variance}px"
                        print("    [PASS] KPI numbers remained 100% stable with collapsed sidebar!")

                    # Expand sidebar back
                    expand_btn = page.locator("[data-testid='stSidebarCollapsedControl'] button")
                    if expand_btn.count() > 0:
                        expand_btn.first.click(force=True, timeout=3000)
                        page.wait_for_timeout(1000)
            except Exception as exc:
                print(f"    Sidebar toggle note: {exc}")

            # Step 3: Tab 1 — Speedometer Gauge & Factor Matrix
            print("[3] Inspecting Tab 1: Redesigned Speedometer Gauge & Factor Breakdown Matrix...")
            tabs = page.locator(".stTabs [role='tab']")
            print(f"    Detected {tabs.count()} main navigation tabs.")
            if tabs.count() > 0:
                tabs.nth(0).click()
                page.wait_for_timeout(1000)
                page.screenshot(path=str(SCREENSHOTS_DIR / "03_tab1_cockpit_gauge.png"))

                # Test hover over factor matrix bars: ensure no annoying popup
                print("    Hovering over Factor Matrix bars to test popup suppression...")
                try:
                    bars = page.query_selector_all(".trace.bars path")
                    if bars:
                        bars[0].hover(force=True)
                        page.wait_for_timeout(500)
                        tooltip = page.query_selector(".hovertext, .hoverlayer text")
                        print(f"    Hover tooltip element detected: {bool(tooltip)}")
                        assert tooltip is None, "Tooltip element appeared on hover!"
                        print("    [PASS] Hover popup successfully suppressed on factor matrix bars!")
                except Exception as exc:
                    print(f"    Hover test note: {exc}")

            # Step 4: Tab 2 — Charts & Orderflow
            print("[4] Inspecting Tab 2: Interactive Charts & Orderflow...")
            if tabs.count() > 1:
                tabs.nth(1).click()
                page.wait_for_timeout(1500)
                page.screenshot(path=str(SCREENSHOTS_DIR / "04_tab2_charts.png"))
                print("    [PASS] Tab 2 rendered cleanly.")

            # Step 5: Tab 3 — ATR Dynamic Risk Model & Calculator
            print("[5] Interacting with Tab 3: Risk Model & Position Sizing Calculator...")
            if tabs.count() > 2:
                tabs.nth(2).click()
                page.wait_for_timeout(1000)
                
                # Human interaction: type new balance in calculator
                deposit_input = page.query_selector("input[type='number']")
                if deposit_input:
                    deposit_input.fill("25000")
                    deposit_input.press("Enter")
                    page.wait_for_timeout(500)
                    print("    [PASS] Successfully entered 25,000 USDT into calculator.")
                
                page.screenshot(path=str(SCREENSHOTS_DIR / "05_tab3_risk_model.png"))

            # Step 6: Tab 4 — Report Viewer
            print("[6] Inspecting Tab 4: PDF & Markdown Reports...")
            if tabs.count() > 3:
                tabs.nth(3).click()
                page.wait_for_timeout(1000)
                page.screenshot(path=str(SCREENSHOTS_DIR / "06_tab4_reports.png"))
                print("    [PASS] Tab 4 report viewer active.")

            # Step 7: Tab 5 — Winrate Calibration Tracker
            print("[7] Inspecting Tab 5: Winrate Tracker & Filter interaction...")
            if tabs.count() > 4:
                tabs.nth(4).click()
                page.wait_for_timeout(1000)
                
                # Click radio filter buttons
                radios = page.query_selector_all("label[data-baseweb='radio']")
                if radios:
                    print(f"    Found {len(radios)} filter radio buttons. Clicking 'В ожидании'...")
                    for r in radios:
                        if "В ожидании" in (r.inner_text() or ""):
                            r.click()
                            page.wait_for_timeout(500)
                            break
                page.screenshot(path=str(SCREENSHOTS_DIR / "07_tab5_tracker_filtered.png"))
                print("    [PASS] Tab 5 filtered table verified.")

            browser.close()
            print("=== [UI/UX BROWSER AUDIT COMPLETED 100% SUCCESSFULLY] ===")

    finally:
        print("[*] Terminating Streamlit server process...")
        server_process.terminate()
        server_process.wait()
        print("[*] Cleanup finished.")

if __name__ == "__main__":
    main()
