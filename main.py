#!/usr/bin/env python3
"""Enable or disable Facebook Ads campaigns on a weekly hourly schedule."""

import argparse
import json
import os
import sys
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from facebook_business.adobjects.campaign import Campaign
from facebook_business.api import FacebookAdsApi
from facebook_business.exceptions import FacebookRequestError

_RATE_LIMIT_CODES = {4, 17, 32, 613, 80000, 80001, 80002, 80003, 80004}

_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

_CREDENTIALS = ("FB_APP_ID", "FB_APP_SECRET", "FB_ACCESS_TOKEN")


def _credential(name):
    """Read a value from the environment, or from the file named by `<name>_FILE`."""
    value = os.environ.get(name, "").strip()
    if value:
        return value
    path = os.environ.get(f"{name}_FILE", "")
    if not path:
        return ""
    with open(path, encoding="utf-8") as handle:
        return handle.read().strip()


def _with_retry(fn, retries=3):
    for attempt in range(retries + 1):
        try:
            return fn()
        except FacebookRequestError as exc:
            if attempt == retries or exc.api_error_code() not in _RATE_LIMIT_CODES:
                raise
            wait = 2**attempt
            print(f"Rate limited (code {exc.api_error_code()}), retrying in {wait}s...", file=sys.stderr)
            time.sleep(wait)


def _day_index(name):
    key = str(name).strip().lower()
    if key not in _DAYS:
        raise ValueError(f"unknown day {name!r}, expected one of {', '.join(_DAYS)}")
    return _DAYS.index(key)


def _parse_time(value, is_end=False):
    text = str(value).strip()
    if is_end and text in ("24:00", "24"):
        return dtime(23, 59, 59, 999999)
    return dtime.fromisoformat(text)


def _parse_window(raw):
    missing = [key for key in ("weekday", "from", "until") if key not in raw]
    if missing:
        raise ValueError(f"window must have {', '.join(repr(k) for k in missing)}: {raw!r}")
    start = _parse_time(raw["from"])
    end = _parse_time(raw["until"], is_end=True)
    if end <= start:
        raise ValueError(f"window 'until' must be after 'from': {raw!r}")
    return {"weekday": _day_index(raw["weekday"]), "from": start, "until": end}


def _is_enabled(now, windows):
    current = now.time()
    return any(now.weekday() == w["weekday"] and w["from"] <= current < w["until"] for w in windows)


def _load_spec(path):
    with open(path, encoding="utf-8") as handle:
        spec = json.load(handle)
    if not spec.get("ad_account_id"):
        raise ValueError("spec must have 'ad_account_id'")
    if not spec.get("campaigns"):
        raise ValueError("spec must have at least one campaign")
    return spec


def main():
    parser = argparse.ArgumentParser(description="Enable/disable Facebook Ads campaigns on schedule")
    parser.add_argument("--spec", default="spec.json", help="Path to the JSON spec (default: spec.json)")
    parser.add_argument("--apply", action="store_true", help="Actually change campaign status (default: dry run)")
    args = parser.parse_args()

    dry_run = not args.apply

    try:
        creds = {name: _credential(name) for name in _CREDENTIALS}
    except OSError as exc:
        print(f"Error: cannot read credentials: {exc}", file=sys.stderr)
        sys.exit(1)
    missing = [name for name, value in creds.items() if not value]
    if missing:
        print(f"Error: missing credentials: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    try:
        spec = _load_spec(args.spec)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: cannot load spec {args.spec}: {exc}", file=sys.stderr)
        sys.exit(1)

    timezone = ZoneInfo(spec.get("timezone", "UTC"))
    now = datetime.now(timezone)
    account_id = str(spec["ad_account_id"]).removeprefix("act_")

    FacebookAdsApi.init(creds["FB_APP_ID"], creds["FB_APP_SECRET"], creds["FB_ACCESS_TOKEN"])

    print(
        f"{now.isoformat(timespec='minutes')} {timezone.key} "
        f"account=act_{account_id} campaigns={len(spec['campaigns'])} "
        f"mode={'apply' if not dry_run else 'dry-run'}",
        file=sys.stderr,
    )

    errors = 0
    for entry in spec["campaigns"]:
        campaign_id = str(entry.get("id", ""))
        if not campaign_id:
            print("Error: campaign entry without 'id'", file=sys.stderr)
            errors += 1
            continue
        try:
            windows = [_parse_window(w) for w in entry.get("windows", [])]
        except ValueError as exc:
            print(f"Error: campaign {campaign_id}: {exc}", file=sys.stderr)
            errors += 1
            continue
        if not windows:
            print(f"Error: campaign {campaign_id}: 'windows' must not be empty", file=sys.stderr)
            errors += 1
            continue

        want = "ACTIVE" if _is_enabled(now, windows) else "PAUSED"

        try:
            campaign = _with_retry(lambda: Campaign(campaign_id).api_get(fields=["id", "name", "status", "configured_status"]))
        except Exception as exc:
            print(f"Error: campaign {campaign_id}: cannot fetch: {exc}", file=sys.stderr)
            errors += 1
            continue

        name = campaign.get("name") or campaign_id
        current = campaign.get("configured_status") or campaign.get("status") or ""
        label = f"{name} (act_{account_id}:{campaign_id})"

        if current not in ("ACTIVE", "PAUSED"):
            print(f"skip     {label}: status is {current}", file=sys.stderr)
            continue

        if current == want:
            print(f"ok       {label}: {current}")
            continue

        if dry_run:
            print(f"would    {label}: {current} -> {want}")
            continue

        try:
            _with_retry(lambda: Campaign(campaign_id).api_update(params={"status": want}))
        except Exception as exc:
            print(f"Error: campaign {campaign_id}: cannot update: {exc}", file=sys.stderr)
            errors += 1
            continue
        print(f"updated  {label}: {current} -> {want}")

    if dry_run:
        print("Dry run only, pass --apply to change campaign status.", file=sys.stderr)

    if errors:
        print(f"Finished with {errors} error(s).", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
