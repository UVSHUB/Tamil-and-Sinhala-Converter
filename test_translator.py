"""
SinTam Voice Translator — Automated Test Suite
================================================
Validates backend connectivity, WebSocket messaging, and language-switching
capabilities of the real-time translation gateway.

Usage
-----
    # Run with defaults (localhost:8000, target=Tamil)
    python test_translator.py

    # Custom server address and initial target language
    python test_translator.py --host 16.171.141.51 --port 8000 --target Sinhala

    # Generate a JSON report file for supervisor / admin review
    python test_translator.py --report

    # Specify a custom output report path
    python test_translator.py --report --output results/test_report.json

All results are printed to the console AND, when --report is used,
written to a timestamped JSON file that can be handed to an admin.
"""

import argparse
import asyncio
import json
import sys
import os
from datetime import datetime, timezone

try:
    import websockets
except ImportError:
    print("[ERROR] 'websockets' package is required.")
    print("Run:  pip install websockets")
    sys.exit(1)


# ── Colour helpers (graceful fallback on unsupported terminals) ────────────
try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init()
    GREEN = Fore.GREEN
    RED = Fore.RED
    YELLOW = Fore.YELLOW
    CYAN = Fore.CYAN
    RESET = Style.RESET_ALL
    BOLD = Style.BRIGHT
except ImportError:
    GREEN = RED = YELLOW = CYAN = RESET = BOLD = ""


# ── Test result container ─────────────────────────────────────────────────
class TestResult:
    """Stores the outcome of a single test case."""

    def __init__(self, test_id: int, name: str):
        self.test_id = test_id
        self.name = name
        self.status = "SKIP"        # PASS / FAIL / SKIP
        self.message = ""
        self.server_response = None
        self.duration_ms = 0.0

    def to_dict(self) -> dict:
        return {
            "test_id": self.test_id,
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "server_response": self.server_response,
            "duration_ms": round(self.duration_ms, 2),
        }


# ── Individual test cases ─────────────────────────────────────────────────
async def test_health_endpoint(host: str, port: int) -> TestResult:
    """TC-1: Verify the REST health-check endpoint is reachable."""
    import urllib.request
    result = TestResult(1, "Health endpoint reachable")
    t0 = asyncio.get_event_loop().time()
    try:
        url = f"http://{host}:{port}/api/v1/health"
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode())
        result.server_response = data
        if data.get("status") == "healthy":
            result.status = "PASS"
            result.message = "Backend is healthy and GEMINI_API_KEY is configured." if data.get("gemini_live_configured") else "Backend healthy but GEMINI_API_KEY is NOT configured."
        else:
            result.status = "FAIL"
            result.message = f"Unexpected health payload: {data}"
    except Exception as ex:
        result.status = "FAIL"
        result.message = f"Could not reach health endpoint: {ex}"
    result.duration_ms = (asyncio.get_event_loop().time() - t0) * 1000
    return result


async def test_ws_connection(ws_url: str) -> TestResult:
    """TC-2: Verify WebSocket connection and initial status message."""
    result = TestResult(2, "WebSocket connection established")
    t0 = asyncio.get_event_loop().time()
    try:
        async with websockets.connect(ws_url, open_timeout=5) as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            payload = json.loads(msg)
            result.server_response = payload
            if payload.get("type") == "status" and "Active" in payload.get("payload", {}).get("message", ""):
                result.status = "PASS"
                result.message = "Received engine-active confirmation from server."
            else:
                result.status = "FAIL"
                result.message = f"Unexpected initial message: {msg}"
    except ConnectionRefusedError:
        result.status = "FAIL"
        result.message = "Connection refused. Is the backend running?"
    except Exception as ex:
        result.status = "FAIL"
        result.message = f"WebSocket error: {ex}"
    result.duration_ms = (asyncio.get_event_loop().time() - t0) * 1000
    return result


async def test_lang_detection_state(ws_url: str) -> TestResult:
    """TC-3: Verify initial language detection broadcast."""
    result = TestResult(3, "Initial language detection state received")
    t0 = asyncio.get_event_loop().time()
    try:
        async with websockets.connect(ws_url, open_timeout=5) as ws:
            # Skip the status message
            await asyncio.wait_for(ws.recv(), timeout=5.0)
            # Read the lang_detected message
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            payload = json.loads(msg)
            result.server_response = payload
            if payload.get("type") == "lang_detected":
                result.status = "PASS"
                result.message = f"Auto-Detect → {payload['payload'].get('target', '?')}"
            else:
                result.status = "FAIL"
                result.message = f"Expected lang_detected, got: {payload.get('type')}"
    except Exception as ex:
        result.status = "FAIL"
        result.message = f"Error: {ex}"
    result.duration_ms = (asyncio.get_event_loop().time() - t0) * 1000
    return result


async def test_language_switch(ws_url: str, switch_to: str) -> TestResult:
    """TC-4: Verify on-the-fly language switching via set_target."""
    result = TestResult(4, f"Language switch to {switch_to}")
    t0 = asyncio.get_event_loop().time()
    try:
        async with websockets.connect(ws_url, open_timeout=5) as ws:
            # Consume initial messages (status + lang_detected)
            await asyncio.wait_for(ws.recv(), timeout=5.0)
            await asyncio.wait_for(ws.recv(), timeout=5.0)

            # Send set_target command
            await ws.send(json.dumps({"type": "set_target", "target": switch_to}))

            # Expect status acknowledgement
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            payload = json.loads(msg)
            result.server_response = payload
            expected_msg = f"Output language switched to {switch_to}"
            if payload.get("type") == "status" and expected_msg in payload.get("payload", {}).get("message", ""):
                result.status = "PASS"
                result.message = f"Server confirmed switch to {switch_to}."
            else:
                result.status = "FAIL"
                result.message = f"Unexpected response: {msg}"
    except Exception as ex:
        result.status = "FAIL"
        result.message = f"Error: {ex}"
    result.duration_ms = (asyncio.get_event_loop().time() - t0) * 1000
    return result


async def test_bidirectional_switch(ws_url: str) -> TestResult:
    """TC-5: Verify switching Tamil→Sinhala→Tamil in a single session."""
    result = TestResult(5, "Bidirectional language switching (Tamil→Sinhala→Tamil)")
    t0 = asyncio.get_event_loop().time()
    try:
        async with websockets.connect(ws_url, open_timeout=5) as ws:
            # Consume initial messages
            await asyncio.wait_for(ws.recv(), timeout=5.0)
            await asyncio.wait_for(ws.recv(), timeout=5.0)

            # Switch to Sinhala
            await ws.send(json.dumps({"type": "set_target", "target": "Sinhala"}))
            r1 = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
            await asyncio.wait_for(ws.recv(), timeout=5.0)  # consume lang_detected

            # Switch back to Tamil
            await ws.send(json.dumps({"type": "set_target", "target": "Tamil"}))
            r2 = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))

            result.server_response = {"switch_1": r1, "switch_2": r2}
            if "Sinhala" in r1.get("payload", {}).get("message", "") and \
               "Tamil" in r2.get("payload", {}).get("message", ""):
                result.status = "PASS"
                result.message = "Both direction switches confirmed in single session."
            else:
                result.status = "FAIL"
                result.message = "One or both switches did not confirm correctly."
    except Exception as ex:
        result.status = "FAIL"
        result.message = f"Error: {ex}"
    result.duration_ms = (asyncio.get_event_loop().time() - t0) * 1000
    return result


# ── Report generator ──────────────────────────────────────────────────────
def generate_report(results: list[TestResult], args, output_path: str | None) -> dict:
    """Generates a structured JSON report and optionally writes it to disk."""
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    skipped = sum(1 for r in results if r.status == "SKIP")

    report = {
        "project": "SinTam Voice Translator",
        "test_suite": "Automated Backend Validation",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "server": f"{args.host}:{args.port}",
        "initial_target_language": args.target,
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "verdict": "ALL PASSED" if failed == 0 else "FAILURES DETECTED",
        },
        "test_cases": [r.to_dict() for r in results],
    }

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    return report


# ── Console printer ───────────────────────────────────────────────────────
def print_results(results: list[TestResult]):
    """Pretty-prints all test results to the console."""
    print(f"\n{'='*70}")
    print(f"  {BOLD}SinTam Voice Translator — Test Results{RESET}")
    print(f"{'='*70}\n")

    for r in results:
        if r.status == "PASS":
            icon = f"{GREEN}✓ PASS{RESET}"
        elif r.status == "FAIL":
            icon = f"{RED}✗ FAIL{RESET}"
        else:
            icon = f"{YELLOW}○ SKIP{RESET}"

        print(f"  {icon}  TC-{r.test_id}: {r.name}")
        print(f"         {r.message}")
        print(f"         {CYAN}({r.duration_ms:.0f}ms){RESET}\n")

    passed = sum(1 for r in results if r.status == "PASS")
    total = len(results)
    verdict_color = GREEN if passed == total else RED
    print(f"{'='*70}")
    print(f"  {verdict_color}{BOLD}Result: {passed}/{total} tests passed{RESET}")
    print(f"{'='*70}\n")


# ── Main orchestrator ─────────────────────────────────────────────────────
async def run_all_tests(args):
    ws_url = f"ws://{args.host}:{args.port}/ws/translate-auto?target={args.target}"
    opposite_lang = "Sinhala" if args.target.lower() == "tamil" else "Tamil"

    print(f"\n{BOLD}Server:{RESET}  {args.host}:{args.port}")
    print(f"{BOLD}Target:{RESET}  {args.target}")
    print(f"{BOLD}WS URL:{RESET}  {ws_url}\n")

    results: list[TestResult] = []

    # TC-1: Health check
    print(f"  {YELLOW}Running TC-1: Health endpoint...{RESET}")
    results.append(await test_health_endpoint(args.host, args.port))

    # TC-2: WebSocket connection
    print(f"  {YELLOW}Running TC-2: WebSocket connection...{RESET}")
    results.append(await test_ws_connection(ws_url))

    # TC-3: Initial language detection
    print(f"  {YELLOW}Running TC-3: Language detection state...{RESET}")
    results.append(await test_lang_detection_state(ws_url))

    # TC-4: Language switch
    print(f"  {YELLOW}Running TC-4: Language switch to {opposite_lang}...{RESET}")
    results.append(await test_language_switch(ws_url, opposite_lang))

    # TC-5: Bidirectional switching
    print(f"  {YELLOW}Running TC-5: Bidirectional switching...{RESET}")
    results.append(await test_bidirectional_switch(ws_url))

    # Print console results
    print_results(results)

    # Generate report file if requested
    if args.report:
        output_path = args.output or f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report = generate_report(results, args, output_path)
        print(f"  {GREEN}Report saved to: {output_path}{RESET}\n")
        return report
    else:
        generate_report(results, args, None)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="SinTam Voice Translator — Automated Test Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_translator.py
  python test_translator.py --host 16.171.141.51 --port 8000 --target Sinhala
  python test_translator.py --report --output results/admin_report.json
        """,
    )
    parser.add_argument(
        "--host", default="localhost",
        help="Backend server host address (default: localhost)",
    )
    parser.add_argument(
        "--port", type=int, default=8000,
        help="Backend server port (default: 8000)",
    )
    parser.add_argument(
        "--target", default="Tamil", choices=["Tamil", "Sinhala"],
        help="Initial target translation language (default: Tamil)",
    )
    parser.add_argument(
        "--report", action="store_true",
        help="Generate a JSON report file for admin/supervisor review",
    )
    parser.add_argument(
        "--output", default=None,
        help="Custom path for the JSON report file (default: auto-timestamped)",
    )

    args = parser.parse_args()
    asyncio.run(run_all_tests(args))


if __name__ == "__main__":
    main()
