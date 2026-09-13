"""
Production Readiness Test for ultra_enricher.py — SEQUENTIAL mode, no hang risk.
Tests: accuracy on known names, edge case stability, error handling, field validation.
"""
import asyncio
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)

import ultra_enricher as ue

KNOWN_LEADS = [
    ("444racingco.com",      "hello@444racingco.com",      "444 Racing Co",      "graveson"),
    ("aajewelry.com",        "info@aajewelry.com",         "A&A Jewelry Supply", ("abraugh", "larocca")),
    ("42birds.com",          "hello@42birds.com",           "42 Birds",           "shapiro"),
    ("4seasonscoffee.com",   "info@4seasonscoffee.com",    "4 Seasons Coffee",   ("hutchinson", "nelson")),
    ("3wishescosmetics.com", "info@3wishescosmetics.com",  "3 Wishes Cosmetics", "reed"),
    ("5mmpaper.com",         "info@5mmpaper.com",          "5mm Paper",          "claesen"),
    ("abayabuth.com",        "info@abayabuth.com",         "AbayaButh",          "buth"),
    ("2beaches.store",       "hello@2beaches.store",       "2Beaches",           "cartwright"),
]

EDGE_CASES = [
    ("",                       "",                           "",               None),  # empty
    ("a4c.com",                "info@a4c.com",               "A4C",            None),  # short stem
    ("2m2.com.tw",             "info@2m2.com.tw",            "2M2",            None),  # Chinese
    ("nonexistent999abc.com",  "x@nonexistent999abc.com",    "Ghost Store",    None),  # dead domain
    ("a4c.com",                "john.smith@a4c.com",         "A4C",            "smith"),  # first.last DNA
]

REQUIRED_FIELDS = [
    'Exec_Name','Exec_First','Exec_Last','Exec_Email','Exec_Confidence',
    'Exec_Source','Exec_Source_Chain','Exec_Title','Exec_Gravatar',
    'Exec_Email_Pattern','Exec_Reg_Country',
]

async def test_one(domain, email, store, expected, label=""):
    lead = {
        'Domain': domain, 'Email': email, 'Store_Name': store,
        'Secondary_Email': '', 'Instagram': '', 'Facebook': ''
    }
    t0 = time.time()
    sem = asyncio.Semaphore(5)
    try:
        if ue.HAS_CURL:
            from curl_cffi.requests import AsyncSession
            async with AsyncSession(impersonate="chrome124", curl_options=ue.CURL_V4_OPTIONS) as client:
                r = await asyncio.wait_for(
                    ue.ultra_enrich_lead(client, lead, sem, timeout=5.0),
                    timeout=30.0  # 30s cap per lead
                )
        else:
            import httpx
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                r = await asyncio.wait_for(
                    ue.ultra_enrich_lead(client, lead, sem, timeout=5.0),
                    timeout=30.0
                )
        elapsed = time.time() - t0

        # Field presence check
        missing = [f for f in REQUIRED_FIELDS if f not in r]
        # Banned word check
        name = r.get('Exec_Name', '').strip()
        banned_in_name = [p for p in name.lower().split() if p in ue.BANNED_WORDS] if name else []

        issues = []
        if missing: issues.append(f"MISSING:{missing}")
        if banned_in_name: issues.append(f"BANNED_WORD:{banned_in_name}")
        if elapsed > 28: issues.append(f"SLOW:{elapsed:.0f}s")

        if expected:
            if isinstance(expected, (list, tuple)):
                match = any(e.lower() in name.lower() for e in expected)
            else:
                match = expected.lower() in name.lower()
        else:
            match = None
        status = "PASS" if (match or match is None) else "FAIL"
        issue_str = f" !! {issues}" if issues else ""

        print(f"  [{status}] {elapsed:4.1f}s | {domain or '(empty)':<32} "
              f"name={name!r:<22} conf={r.get('Exec_Confidence',''):<10} "
              f"src={r.get('Exec_Source','')[:18]}{issue_str}")
        return status, elapsed, issues

    except asyncio.TimeoutError:
        elapsed = time.time() - t0
        print(f"  [TIMEOUT] {elapsed:.0f}s | {domain!r} — HARD TIMEOUT (>30s)")
        return "TIMEOUT", elapsed, ["TIMEOUT"]
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  [ERROR] {elapsed:.0f}s | {domain!r} — {type(e).__name__}: {e}")
        return "ERROR", elapsed, [str(e)]

async def main():
    http_lib = "curl_cffi" if ue.HAS_CURL else "httpx"
    sem = asyncio.Semaphore(5)
    all_results = []

    print(f"[INFO] HTTP: {http_lib} | Semaphore: 5 (Clean Session per Lead)")
    print("=" * 90)
    print("KNOWN-NAME ACCURACY (sequential)")
    print("=" * 90)
    for domain, email, store, expected in KNOWN_LEADS:
        status, elapsed, issues = await test_one(domain, email, store, expected)
        all_results.append((status, elapsed, issues, domain))
        await asyncio.sleep(0.5)

    print()
    print("=" * 90)
    print("EDGE CASE STABILITY")
    print("=" * 90)
    for domain, email, store, expected in EDGE_CASES:
        status, elapsed, issues = await test_one(domain, email, store, expected, "edge")
        all_results.append((status, elapsed, issues, domain))
        await asyncio.sleep(0.3)

    print()
    print("=" * 90)
    print("PRODUCTION READINESS VERDICT")
    print("=" * 90)
    errors   = [r for r in all_results if r[0] in ("ERROR","TIMEOUT")]
    fails    = [r for r in all_results if r[0] == "FAIL"]
    issues   = [r for r in all_results if r[2]]
    known_pass = [r for r in all_results[:len(KNOWN_LEADS)] if r[0] == "PASS"]
    acc = len(known_pass) / len(KNOWN_LEADS) * 100
    avg_t = sum(r[1] for r in all_results) / len(all_results)

    print(f"  Accuracy:    {len(known_pass)}/{len(KNOWN_LEADS)} = {acc:.0f}%")
    print(f"  Errors:      {len(errors)}")
    print(f"  Field issues:{len(issues)}")
    print(f"  Avg time:    {avg_t:.1f}s/lead")

    if errors:
        print(f"\n  ERRORS/TIMEOUTS:")
        for s, t, i, d in errors:
            print(f"    [{s}] {d}: {i}")
    if fails:
        print(f"\n  ACCURACY FAILURES:")
        for s, t, i, d in fails:
            print(f"    {d}")

    print()
    if len(errors) == 0 and acc >= 70:
        print("  ✅  PRODUCTION READY — deploy to GitHub!")
    elif len(errors) == 0:
        print(f"  ⚠️   No errors but accuracy {acc:.0f}% < 70% — review")
    else:
        print(f"  ❌  {len(errors)} error(s) found — fix before deploy")

asyncio.run(main())
