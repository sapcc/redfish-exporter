"""
Run all five Redfish exporter endpoints for one target and save metric output to files.

Usage (exporter must already be running):
    python run_endpoint_tests.py --target <bmc-host-or-ip> --job <job-name>

Options:
    --target   BMC hostname or IP address
    --job      Job name as defined in config.yml
    --url      Exporter base URL (default: http://localhost:9220)
    --out      Output directory for metric files (default: test-reports)
"""
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ENDPOINTS = ["health", "performance", "firmware", "sensors", "bios"]
TIMEOUT = 120  # seconds per endpoint request


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test all Redfish exporter endpoints for a target and save metric output."
    )
    parser.add_argument("--target", required=True, help="BMC hostname or IP")
    parser.add_argument("--job",    required=True, help="Job name (must match a job in config.yml)")
    parser.add_argument("--url",    default="http://localhost:9220", metavar="URL",
                        help="Exporter base URL (default: %(default)s)")
    parser.add_argument("--out",    default="test-reports", metavar="DIR",
                        help="Output directory for metric files (default: %(default)s)")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Wait for the exporter to become reachable (it may still be starting up)
    print(f"Waiting for exporter at {base_url} ...", end="", flush=True)
    deadline = time.monotonic() + 30
    while True:
        try:
            requests.get(f"{base_url}/", timeout=2)
            print(" ready.")
            break
        except requests.exceptions.ConnectionError:
            if time.monotonic() > deadline:
                print()
                print(f"ERROR: Exporter did not become reachable within 30 s.")
                sys.exit(1)
            print(".", end="", flush=True)
            time.sleep(1)

    # Short server label for filenames: first segment of FQDN or the raw IP
    server_label = args.target.split(".")[0]
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    print(f"Exporter : {base_url}")
    print(f"Target   : {args.target}")
    print(f"Job      : {args.job}")
    print(f"Output   : {out_dir}/")
    print()
    print(f"{'Endpoint':<14}  {'Status':>6}  {'Time':>6}  {'Lines':>6}  File")
    print("-" * 72)

    results = []
    for endpoint in ENDPOINTS:
        url = f"{base_url}/{endpoint}?target={args.target}&job={args.job}"
        out_file = out_dir / f"{server_label}-{endpoint}-{timestamp}.txt"

        start = time.monotonic()
        try:
            resp = requests.get(url, timeout=TIMEOUT, verify=False)
            elapsed = time.monotonic() - start
            out_file.write_text(resp.text, encoding="utf-8")
            lines = resp.text.count("\n")
            status_str = str(resp.status_code)
            print(f"/{endpoint:<13}  {status_str:>6}  {elapsed:>5.1f}s  {lines:>6}  {out_file.name}")
            results.append((endpoint, True, resp.status_code, elapsed, out_file))
        except requests.exceptions.Timeout:
            elapsed = time.monotonic() - start
            print(f"/{endpoint:<13}  TIMEOUT  {elapsed:>5.1f}s")
            results.append((endpoint, False, 0, elapsed, None))
        except Exception as e:
            elapsed = time.monotonic() - start
            print(f"/{endpoint:<13}   ERROR  {elapsed:>5.1f}s  {e}")
            results.append((endpoint, False, 0, elapsed, None))

    print("-" * 72)
    passed = sum(1 for _, ok, *_ in results if ok)
    total_time = sum(elapsed for _, _, _, elapsed, _ in results)
    print(f"Done: {passed}/{len(ENDPOINTS)} OK  |  total {total_time:.1f}s")

    if passed < len(ENDPOINTS):
        failed = [ep for ep, ok, *_ in results if not ok]
        print(f"Failed endpoints: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
