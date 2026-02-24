"""UAT: Anti-hallucination guards for 'all' mode scans.

Tests that every scanning tool returns data_quality metadata, structured
errors on timeout, discovery_failed in region_metadata, and anti-hallucination
instructions in tool docstrings.
"""

import asyncio
import json
import time

PASS = 0
FAIL = 0
results = []


def record(test_id, name, passed, detail=""):
    global PASS, FAIL
    status = "PASS" if passed else "FAIL"
    if passed:
        PASS += 1
    else:
        FAIL += 1
    results.append((test_id, name, status, detail))
    print(f"  [{status}] {test_id}: {name}")
    if detail:
        print(f"         {detail}")


async def run_uat():
    from mcp_server.container import ServiceContainer

    container = ServiceContainer()
    await container.initialize()
    print("Container initialized.\n")

    # Wire up the stdio_server module-level container
    import mcp_server.stdio_server as srv

    srv._container = container

    # =====================================================================
    # UAT-ALL.01: check_tag_compliance with ["all"]
    # =====================================================================
    print("=" * 70)
    print('UAT-ALL.01: check_tag_compliance with ["all"]')
    print("=" * 70)
    start = time.time()
    raw = await srv.check_tag_compliance(resource_types=["all"], severity="all")
    elapsed = time.time() - start
    resp = json.loads(raw)

    dq = resp.get("data_quality")
    record("ALL.01a", "data_quality field present", dq is not None, f"Got: {dq}")
    record(
        "ALL.01b",
        "data_quality.status is complete or partial",
        dq and dq.get("status") in ("complete", "partial"),
        f"status={dq.get('status') if dq else 'missing'}",
    )
    record(
        "ALL.01c",
        "compliance_score is numeric",
        isinstance(resp.get("compliance_score"), (int, float)),
        f"score={resp.get('compliance_score')}",
    )
    record(
        "ALL.01d",
        "total_resources > 0",
        resp.get("total_resources", 0) > 0,
        f"total={resp.get('total_resources')}",
    )
    record("ALL.01e", "completed within 300s", elapsed < 300, f"elapsed={elapsed:.1f}s")

    # =====================================================================
    # UAT-ALL.02: find_untagged_resources with ["all"]
    # =====================================================================
    print()
    print("=" * 70)
    print('UAT-ALL.02: find_untagged_resources with ["all"]')
    print("=" * 70)
    start = time.time()
    raw = await srv.find_untagged_resources(resource_types=["all"])
    elapsed = time.time() - start
    resp = json.loads(raw)

    dq = resp.get("data_quality")
    record("ALL.02a", "data_quality field present", dq is not None, f"Got: {dq}")
    record(
        "ALL.02b",
        "data_quality.status is complete or partial",
        dq and dq.get("status") in ("complete", "partial"),
        f"status={dq.get('status') if dq else 'missing'}",
    )
    record(
        "ALL.02c",
        "total_untagged is numeric",
        isinstance(resp.get("total_untagged"), (int, float)),
        f"count={resp.get('total_untagged')}",
    )
    record("ALL.02d", "completed within 300s", elapsed < 300, f"elapsed={elapsed:.1f}s")

    # =====================================================================
    # UAT-ALL.03: get_cost_attribution_gap with ["all"]
    # =====================================================================
    print()
    print("=" * 70)
    print('UAT-ALL.03: get_cost_attribution_gap with ["all"]')
    print("=" * 70)
    start = time.time()
    raw = await srv.get_cost_attribution_gap(resource_types=["all"])
    elapsed = time.time() - start
    resp = json.loads(raw)

    has_error = "error" in resp
    if has_error:
        record(
            "ALL.03a",
            "tool returned structured error (timeout expected for large accounts)",
            resp.get("error") in ("timeout", "analysis_failed"),
            f"error={resp.get('error')}, msg={resp.get('message', '')[:80]}",
        )
        record(
            "ALL.03b",
            "error has suggestion field",
            "suggestion" in resp,
            f"suggestion present: {'suggestion' in resp}",
        )
    else:
        dq = resp.get("data_quality")
        record("ALL.03a", "data_quality field present", dq is not None, f"Got: {dq}")
        record(
            "ALL.03b",
            "data_quality.status is complete or partial",
            dq and dq.get("status") in ("complete", "partial"),
            f"status={dq.get('status') if dq else 'missing'}",
        )
        record(
            "ALL.03c",
            "total_spend is numeric",
            isinstance(resp.get("total_spend"), (int, float)),
            f"total_spend=${resp.get('total_spend', 0):.2f}",
        )
        record(
            "ALL.03d",
            "attribution_gap is numeric",
            isinstance(resp.get("attribution_gap"), (int, float)),
            f"gap=${resp.get('attribution_gap', 0):.2f}",
        )
    record("ALL.03e", "completed within 300s", elapsed < 300, f"elapsed={elapsed:.1f}s")

    # =====================================================================
    # UAT-ALL.04: generate_compliance_report with ["all"]
    # =====================================================================
    print()
    print("=" * 70)
    print('UAT-ALL.04: generate_compliance_report with ["all"]')
    print("=" * 70)
    start = time.time()
    raw = await srv.generate_compliance_report(resource_types=["all"], format="json")
    elapsed = time.time() - start
    resp = json.loads(raw)

    has_error = "error" in resp
    if has_error:
        record(
            "ALL.04a",
            "tool returned structured error",
            resp.get("error") in ("timeout", "scan_failed"),
            f"error={resp.get('error')}",
        )
    else:
        dq = resp.get("data_quality")
        record("ALL.04a", "data_quality field present", dq is not None, f"Got: {dq}")
        record("ALL.04b", "report has summary", "summary" in resp, f"keys={list(resp.keys())[:5]}")
    record("ALL.04c", "completed within 300s", elapsed < 300, f"elapsed={elapsed:.1f}s")

    # =====================================================================
    # UAT-ALL.05: export_violations_csv with ["all"]
    # =====================================================================
    print()
    print("=" * 70)
    print('UAT-ALL.05: export_violations_csv with ["all"]')
    print("=" * 70)
    start = time.time()
    raw = await srv.export_violations_csv(resource_types=["all"])
    elapsed = time.time() - start
    resp = json.loads(raw)

    has_error = "error" in resp
    if has_error:
        record(
            "ALL.05a",
            "tool returned structured error",
            resp.get("error") in ("timeout", "export_failed"),
            f"error={resp.get('error')}",
        )
    else:
        dq = resp.get("data_quality")
        record("ALL.05a", "data_quality field present", dq is not None, f"Got: {dq}")
        record("ALL.05b", "csv_data present", "csv_data" in resp, "")
    record("ALL.05c", "completed within 300s", elapsed < 300, f"elapsed={elapsed:.1f}s")

    # =====================================================================
    # UAT-ALL.06: detect_tag_drift with defaults
    # =====================================================================
    print()
    print("=" * 70)
    print("UAT-ALL.06: detect_tag_drift with defaults")
    print("=" * 70)
    start = time.time()
    raw = await srv.detect_tag_drift()
    elapsed = time.time() - start
    resp = json.loads(raw)

    dq = resp.get("data_quality")
    record("ALL.06a", "data_quality field present", dq is not None, f"Got: {dq}")
    record("ALL.06b", "completed within 300s", elapsed < 300, f"elapsed={elapsed:.1f}s")

    # =====================================================================
    # UAT-ALL.09: region_metadata includes discovery_failed
    # =====================================================================
    print()
    print("=" * 70)
    print("UAT-ALL.09: region_metadata includes discovery_failed")
    print("=" * 70)
    raw = await srv.check_tag_compliance(resource_types=["ec2:instance"])
    resp = json.loads(raw)
    rm = resp.get("region_metadata", {})
    record("ALL.09a", "region_metadata present", bool(rm), f"keys={list(rm.keys())}")
    record(
        "ALL.09b",
        "discovery_failed field present",
        "discovery_failed" in rm,
        f"discovery_failed={rm.get('discovery_failed')}",
    )

    # =====================================================================
    # UAT-ALL.10: tool docstrings contain anti-hallucination instructions
    # =====================================================================
    print()
    print("=" * 70)
    print("UAT-ALL.10: tool docstrings contain anti-hallucination instructions")
    print("=" * 70)
    tools_to_check = [
        ("check_tag_compliance", srv.check_tag_compliance),
        ("find_untagged_resources", srv.find_untagged_resources),
        ("get_cost_attribution_gap", srv.get_cost_attribution_gap),
        ("generate_compliance_report", srv.generate_compliance_report),
        ("detect_tag_drift", srv.detect_tag_drift),
        ("export_violations_csv", srv.export_violations_csv),
    ]
    for name, func in tools_to_check:
        doc = func.__doc__ or ""
        has_critical = "CRITICAL" in doc and "data_quality" in doc
        record(
            f"ALL.10.{name[:12]}",
            f"{name} has anti-hallucination docstring",
            has_critical,
            f"Has CRITICAL+data_quality: {has_critical}",
        )

    # =====================================================================
    # SUMMARY
    # =====================================================================
    print()
    print("=" * 70)
    print(f"UAT SUMMARY: {PASS} PASS / {FAIL} FAIL / {PASS + FAIL} TOTAL")
    print("=" * 70)
    for tid, name, status, detail in results:
        flag = "v" if status == "PASS" else "X"
        print(f"  [{flag}] {tid:20s} {name}")

    print(f'\nResult: {"ALL PASS" if FAIL == 0 else f"{FAIL} FAILURES"}\n')


if __name__ == "__main__":
    asyncio.run(run_uat())
