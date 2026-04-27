#!/usr/bin/env python3
"""
PostHog management CLI — manage project settings, query events, and test
integrations without leaving the terminal.

Usage:
  uv run python scripts/posthog_manager.py settings
  uv run python scripts/posthog_manager.py update --session-recording --sample-rate 0.5
  uv run python scripts/posthog_manager.py envs
  uv run python scripts/posthog_manager.py events --after 2024-01-01 --limit 50
  uv run python scripts/posthog_manager.py sessions
  uv run python scripts/posthog_manager.py logs
  uv run python scripts/posthog_manager.py capture --event "test_event" --distinct-id "user_123"
  uv run python scripts/posthog_manager.py restrictions
  uv run python scripts/posthog_manager.py configure-logs --enable --retention 30

Notes:
- Requires POSTHOG_API_KEY and POSTHOG_PROJECT_ID in environment
- Uses the PostHog API (not the capture API) for management operations
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add this script's directory to path so it runs standalone
sys.path.insert(0, str(Path(__file__).resolve().parent))

from posthog_client import PostHogClient


# ─── helpers ─────────────────────────────────────────────────────────


def _print_table(headers: list[str], rows: list[list[str]], min_widths: list[int] | None = None) -> None:
    """Print a formatted table with auto-sized columns."""
    if not rows:
        print("(no data)")
        return

    # Calculate column widths
    widths = []
    for i, header in enumerate(headers):
        col_values = [row[i] for row in rows if i < len(row)]
        max_content = max(len(str(v)) for v in [header] + col_values)
        if min_widths and i < len(min_widths):
            max_content = max(max_content, min_widths[i])
        widths.append(max_content)

    # Print header
    header_line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(header_line)
    print("-" * len(header_line))

    # Print rows
    for row in rows:
        print("  ".join(str(v).ljust(w) for v, w in zip(row, widths)))


def _print_kv(data: dict[str, Any], title: str | None = None) -> None:
    """Print key-value pairs in a formatted way."""
    if title:
        print(f"\n=== {title} ===")

    max_key = max(len(k) for k in data.keys())
    for key, value in data.items():
        if isinstance(value, bool):
            display = "✓ enabled" if value else "✗ disabled"
        elif isinstance(value, (dict, list)):
            display = json.dumps(value, indent=2)
        else:
            display = str(value)
        print(f"  {key.ljust(max_key)}  {display}")


# ─── settings ─────────────────────────────────────────────────────────


def cmd_settings(client: PostHogClient, args: argparse.Namespace) -> None:
    """Show current project settings."""
    try:
        settings = client.get_project()

        print("\n=== PostHog Project Settings ===")
        print(f"  Project ID:    {client.project_id}")
        print(f"  Host:          {client.host}")

        # Core settings
        core = {
            "Name": settings.get("name", "N/A"),
            "Timezone": settings.get("timezone", "N/A"),
            "Created": settings.get("created_at", "N/A"),
        }
        _print_kv(core, "Core")

        # Session recording settings
        recording_config = settings.get("session_recording_opt_in", False)
        sample_rate = settings.get("session_recording_sample_rate")
        if sample_rate is None:
            sample_rate = 1.0
        recording_data = {
            "Session Recording": recording_config,
            "Sample Rate": f"{sample_rate * 100:.0f}%",
        }
        _print_kv(recording_data, "Session Recording")

        # Feature flags
        features = {
            "Surveys": settings.get("surveys_opt_in", False),
            "Heatmaps": settings.get("heatmaps_opt_in", False),
            "Autocapture": settings.get("autocapture_opt_in", True),
            "Anonymize IPs": settings.get("anonymize_ips", False),
        }
        _print_kv(features, "Features")

        # Data retention
        retention = settings.get("data_retention_days", "unlimited")
        retention_data = {
            "Data Retention": f"{retention} days" if retention != "unlimited" else "unlimited",
        }
        _print_kv(retention_data, "Retention")

        # Raw JSON if verbose
        if args.verbose:
            print("\n=== Raw Settings (JSON) ===")
            print(json.dumps(settings, indent=2))

    except Exception as e:
        print(f"Error fetching settings: {e}")
        sys.exit(1)


# ─── update ───────────────────────────────────────────────────────────


def cmd_update(client: PostHogClient, args: argparse.Namespace) -> None:
    """Update project settings."""
    updates: dict[str, Any] = {}

    # Build update payload from flags
    if args.session_recording is not None:
        updates["session_recording_opt_in"] = args.session_recording
    if args.sample_rate is not None:
        updates["session_recording_sample_rate"] = args.sample_rate
    if args.surveys is not None:
        updates["surveys_opt_in"] = args.surveys
    if args.heatmaps is not None:
        updates["heatmaps_opt_in"] = args.heatmaps
    if args.anonymize_ips is not None:
        updates["anonymize_ips"] = args.anonymize_ips
    if args.timezone:
        updates["timezone"] = args.timezone
    if args.name:
        updates["name"] = args.name

    if not updates:
        print("No updates specified. Use flags like --session-recording, --sample-rate, etc.")
        sys.exit(1)

    try:
        result = client.update_project(updates)
        print("✓ Settings updated successfully")

        # Show what changed
        for key, value in updates.items():
            display = f"{value * 100:.0f}%" if "rate" in key else ("enabled" if value is True else "disabled" if value is False else value)
            print(f"  {key}: {display}")

        if args.verbose:
            print("\n=== Response ===")
            print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"Error updating settings: {e}")
        sys.exit(1)


# ─── envs ─────────────────────────────────────────────────────────────


def cmd_envs(client: PostHogClient, args: argparse.Namespace) -> None:
    """List environments for the project."""
    try:
        envs = client.list_environments()

        if not envs:
            print("(no environments found)")
            return

        headers = ["ID", "Name", "API Key Prefix", "Created"]
        rows = []
        for env in envs:
            api_key = env.get("api_key", "")
            prefix = api_key[:8] + "..." if len(api_key) > 8 else api_key
            rows.append([
                env.get("id", "N/A"),
                env.get("name", "N/A"),
                prefix,
                env.get("created_at", "N/A")[:10] if env.get("created_at") else "N/A",
            ])

        print(f"\n=== Environments ({len(envs)} total) ===")
        _print_table(headers, rows, min_widths=[10, 20, 15, 12])

    except Exception as e:
        print(f"Error listing environments: {e}")
        sys.exit(1)


# ─── events ───────────────────────────────────────────────────────────


def cmd_events(client: PostHogClient, args: argparse.Namespace) -> None:
    """Query events from the project."""
    try:
        params: dict[str, Any] = {"limit": args.limit}

        if args.after:
            params["after"] = args.after
        if args.before:
            params["before"] = args.before
        if args.event:
            params["event"] = args.event

        events = client.get_events(**params)

        if not events:
            print("(no events found matching criteria)")
            return

        headers = ["Timestamp", "Event", "Distinct ID", "Properties"]
        rows = []
        for event in events[:args.limit]:
            props = event.get("properties", {})
            # Show a few key properties
            prop_summary = ", ".join(f"{k}={v}" for k, v in list(props.items())[:3])
            if len(props) > 3:
                prop_summary += f" (+{len(props) - 3} more)"

            rows.append([
                event.get("timestamp", "N/A")[:19] if event.get("timestamp") else "N/A",
                event.get("event", "N/A"),
                event.get("distinct_id", "N/A")[:20],
                prop_summary[:40] if prop_summary else "-",
            ])

        print(f"\n=== Events ({len(events)} found, showing {min(len(events), args.limit)}) ===")
        _print_table(headers, rows, min_widths=[19, 20, 22, 40])

        if args.verbose and events:
            print("\n=== First Event (JSON) ===")
            print(json.dumps(events[0], indent=2))

    except Exception as e:
        print(f"Error querying events: {e}")
        sys.exit(1)


# ─── sessions ─────────────────────────────────────────────────────────


def cmd_sessions(client: PostHogClient, args: argparse.Namespace) -> None:
    """List recent session recordings."""
    try:
        sessions = client.get_sessions(limit=args.limit)

        if not sessions:
            print("(no session recordings found)")
            return

        headers = ["ID", "Start", "Duration", "User", "Events"]
        rows = []
        for session in sessions:
            duration_sec = session.get("duration", 0)
            duration_str = f"{duration_sec // 60}m {duration_sec % 60}s" if duration_sec > 60 else f"{duration_sec}s"

            rows.append([
                session.get("id", "N/A")[:12],
                session.get("start_time", "N/A")[:19] if session.get("start_time") else "N/A",
                duration_str,
                session.get("distinct_id", "N/A")[:20],
                str(session.get("event_count", 0)),
            ])

        print(f"\n=== Session Recordings ({len(sessions)} found) ===")
        _print_table(headers, rows, min_widths=[12, 19, 10, 22, 8])

    except Exception as e:
        print(f"Error listing sessions: {e}")
        sys.exit(1)


# ─── logs ─────────────────────────────────────────────────────────────


def cmd_logs(client: PostHogClient, args: argparse.Namespace) -> None:
    """Show log configuration and recent logs."""
    try:
        config = client.get_project()

        print("\n=== Log Configuration ===")
        log_data = {
            "Project Logs Enabled": config.get("capture_console_log_opt_in", False),
            "Session Recording": config.get("session_recording_opt_in", False),
            "Autocapture": config.get("autocapture_opt_in", True),
        }
        _print_kv(log_data)

        if args.verbose:
            print("\n=== Raw Config (JSON) ===")
            print(json.dumps(config, indent=2))
    except Exception as e:
        message = str(e)
        if "404" in message or "Endpoint not found" in message:
            print("PostHog log management endpoint is not available on this project/plan.")
            print("Use `settings`, `events`, `sessions`, and `insights` for debugging instead.")
            return
        print(f"Error fetching logs: {e}")
        sys.exit(1)


# ─── capture ──────────────────────────────────────────────────────────


def cmd_capture(client: PostHogClient, args: argparse.Namespace) -> None:
    """Send a test event to PostHog."""
    try:
        event = args.event
        distinct_id = args.distinct_id

        # Parse properties JSON
        properties: dict[str, Any] = {}
        if args.properties:
            try:
                properties = json.loads(args.properties)
            except json.JSONDecodeError as e:
                print(f"Invalid JSON in --properties: {e}")
                sys.exit(1)

        # Add timestamp and test marker
        properties["$timestamp"] = datetime.now(UTC).isoformat()
        properties["test_event"] = True

        result = client.capture_event(
            event=event,
            distinct_id=distinct_id,
            properties=properties,
        )

        print("✓ Event captured successfully")
        print(f"  Event:        {event}")
        print(f"  Distinct ID:  {distinct_id}")
        print(f"  Properties:   {len(properties)} keys")

        if args.verbose:
            print("\n=== Response ===")
            print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"Error capturing event: {e}")
        sys.exit(1)


# ─── restrictions ─────────────────────────────────────────────────────


def cmd_restrictions(client: PostHogClient, args: argparse.Namespace) -> None:
    """Show event ingestion restrictions."""
    try:
        try:
            envs = client.list_environments()
        except Exception as env_error:
            env_message = str(env_error)
            if "403 Forbidden" in env_message or "permission_denied" in env_message or "Multiple environments per project are no longer available" in env_message:
                print("PostHog environments are not available on this project, so ingestion restrictions can't be queried here.")
                return
            raise
        if not envs:
            print("No PostHog environments available for ingestion restrictions.")
            return

        env_id = envs[0].get("id")
        restrictions = client.get_event_ingestion_restrictions(str(env_id))

        print("\n=== Event Ingestion Restrictions ===")

        # Rate limits
        rate_limits = restrictions.get("rate_limits", {})
        rate_data = {
            "Events/Second": rate_limits.get("events_per_second", "N/A"),
            "Burst Limit": rate_limits.get("burst_limit", "N/A"),
        }
        _print_kv(rate_data, "Rate Limits")

        # Size limits
        size_limits = restrictions.get("size_limits", {})
        size_data = {
            "Max Event Size": f"{size_limits.get('max_event_size_bytes', 0) / 1024:.0f} KB" if size_limits.get("max_event_size_bytes") else "N/A",
            "Max Batch Size": f"{size_limits.get('max_batch_size_bytes', 0) / 1024:.0f} KB" if size_limits.get("max_batch_size_bytes") else "N/A",
            "Max Events/Batch": size_limits.get("max_events_per_batch", "N/A"),
        }
        _print_kv(size_data, "Size Limits")

        # Blocked events
        blocked = restrictions.get("blocked_events", [])
        if blocked:
            print("\n  Blocked Event Types:")
            for event in blocked:
                print(f"    - {event}")

        if args.verbose:
            print("\n=== Raw Restrictions (JSON) ===")
            print(json.dumps(restrictions, indent=2))

    except Exception as e:
        message = str(e)
        if "permission_denied" in message or "Multiple environments per project are no longer available" in message:
            print("PostHog environments are not available on this project, so ingestion restrictions can't be queried here.")
            return
        print(f"Error fetching restrictions: {e}")
        sys.exit(1)


# ─── configure-logs ───────────────────────────────────────────────────


def cmd_configure_logs(client: PostHogClient, args: argparse.Namespace) -> None:
    """Configure log ingestion settings."""
    try:
        updates: dict[str, Any] = {}

        if args.enable is not None:
            updates["logs_enabled"] = args.enable
        if args.retention is not None:
            updates["logs_retention_days"] = args.retention

        if not updates:
            print("No configuration changes specified. Use --enable/--disable or --retention")
            sys.exit(1)

        result = client.configure_logs(enabled=args.enable, retention_days=args.retention)

        print("✓ Log configuration updated")
        for key, value in updates.items():
            display = "enabled" if value is True else "disabled" if value is False else value
            print(f"  {key}: {display}")

        if args.verbose:
            print("\n=== Response ===")
            print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"Error configuring logs: {e}")
        sys.exit(1)


# ─── persons ────────────────────────────────────────────────────────────

def cmd_persons(client: PostHogClient, args: argparse.Namespace) -> None:
    """List persons with optional search."""
    try:
        filters: dict[str, Any] = {"limit": args.limit}
        if args.search:
            if "@" in args.search:
                filters["email"] = args.search
            else:
                filters["distinct_id"] = args.search

        persons = client.list_persons(**filters)

        if not persons:
            print("(no persons found matching criteria)")
            return

        headers = ["ID", "Distinct ID", "Email", "Created", "Events"]
        rows = []
        for person in persons:
            props = person.get("properties", {})
            email = props.get("email", "N/A")
            distinct_ids = person.get("distinct_ids", [])
            distinct_id = distinct_ids[0] if distinct_ids else person.get("name", "N/A")
            rows.append([
                str(person.get("id", "N/A"))[:8],
                str(distinct_id)[:20],
                email[:25] if email else "N/A",
                person.get("created_at", "N/A")[:10] if person.get("created_at") else "N/A",
                str(person.get("event_count", 0)),
            ])

        print(f"\n=== Persons ({len(persons)} found) ===")
        _print_table(headers, rows, min_widths=[10, 22, 25, 12, 8])

        if args.verbose and persons:
            print("\n=== First Person (JSON) ===")
            print(json.dumps(persons[0], indent=2))

    except Exception as e:
        print(f"Error listing persons: {e}")
        sys.exit(1)


# ─── person ─────────────────────────────────────────────────────────────

def cmd_person(client: PostHogClient, args: argparse.Namespace) -> None:
    """Show person details and recent events."""
    try:
        person = None
        looks_like_person_id = "-" in args.person_id and len(args.person_id) >= 30

        if looks_like_person_id:
            person = client.get_person(args.person_id)
        else:
            for candidate in client.list_persons(limit=100):
                candidate_id = str(candidate.get("id", ""))
                candidate_name = str(candidate.get("name", ""))
                candidate_distinct_ids = [str(v) for v in candidate.get("distinct_ids", [])]
                candidate_email = str(candidate.get("properties", {}).get("email", ""))
                if (
                    candidate_id.startswith(args.person_id)
                    or candidate_name == args.person_id
                    or args.person_id in candidate_distinct_ids
                    or candidate_email == args.person_id
                ):
                    person = candidate
                    break

        if person is None:
            raise ValueError(f"No person found matching '{args.person_id}'")

        print("\n=== Person Details ===")
        print(f"  ID:            {person.get('id', 'N/A')}")
        distinct_ids = person.get("distinct_ids", [])
        primary_distinct_id = distinct_ids[0] if distinct_ids else person.get("name", "N/A")
        print(f"  Distinct ID:   {primary_distinct_id}")
        print(f"  Created:       {person.get('created_at', 'N/A')}")
        print(f"  Event Count:   {person.get('event_count', 0)}")

        props = person.get("properties", {})
        if props:
            print("\n  Properties:")
            for key, value in list(props.items())[:10]:
                print(f"    {key}: {value}")
            if len(props) > 10:
                print(f"    ... and {len(props) - 10} more")

        print("\n  Recent Events:")
        try:
            all_events = client.get_events(limit=50)
            events = [
                ev
                for ev in all_events
                if ev.get("distinct_id") == primary_distinct_id
            ][:10]
            if events:
                for ev in events[:5]:
                    ts = ev.get("timestamp", "N/A")
                    if ts:
                        ts = ts[:19]
                    print(f"    - {ev.get('event', 'N/A')} @ {ts}")
            else:
                print("    (no recent events)")
        except Exception as ev_e:
            print(f"    (could not fetch events: {ev_e})")

        if args.verbose:
            print("\n=== Raw Person Data (JSON) ===")
            print(json.dumps(person, indent=2))

    except Exception as e:
        print(f"Error fetching person: {e}")
        sys.exit(1)


# ─── flags ──────────────────────────────────────────────────────────────

def cmd_flags(client: PostHogClient, args: argparse.Namespace) -> None:
    """List feature flags."""
    try:
        flags = client.list_feature_flags()

        if not flags:
            print("(no feature flags found)")
            return

        headers = ["ID", "Key", "Active", "Type", "Created"]
        rows = []
        for flag in flags:
            filters = flag.get("filters", {})
            flag_type = "boolean"
            if filters.get("multivariate"):
                flag_type = "multivariate"
            elif filters.get("aggregation_group_type_index") is not None:
                flag_type = "group"
            rows.append([
                str(flag.get("id", "N/A")),
                flag.get("key", "N/A")[:25],
                "✓" if flag.get("active") else "✗",
                flag_type,
                flag.get("created_at", "N/A")[:10] if flag.get("created_at") else "N/A",
            ])

        active_count = sum(1 for f in flags if f.get("active"))
        print(f"\n=== Feature Flags ({len(flags)} total, {active_count} active) ===")
        _print_table(headers, rows, min_widths=[8, 25, 8, 12, 12])

        if args.verbose and flags:
            print("\n=== First Flag (JSON) ===")
            print(json.dumps(flags[0], indent=2))

    except Exception as e:
        print(f"Error listing flags: {e}")
        sys.exit(1)


# ─── toggle-flag ────────────────────────────────────────────────────────

def cmd_toggle_flag(client: PostHogClient, args: argparse.Namespace) -> None:
    """Enable or disable a feature flag."""
    try:
        active = args.enable if args.enable is not None else not args.disable
        result = client.toggle_feature_flag(args.flag_id, active=active)

        status = "enabled" if active else "disabled"
        print(f"✓ Feature flag {args.flag_id} {status}")

        if args.verbose:
            print("\n=== Response ===")
            print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"Error toggling flag: {e}")
        sys.exit(1)


# ─── cohorts ────────────────────────────────────────────────────────────

def cmd_cohorts(client: PostHogClient, args: argparse.Namespace) -> None:
    """List cohorts."""
    try:
        cohorts = client.list_cohorts()

        if not cohorts:
            print("(no cohorts found)")
            return

        headers = ["ID", "Name", "Count", "Type", "Created"]
        rows = []
        for cohort in cohorts:
            rows.append([
                str(cohort.get("id", "N/A")),
                cohort.get("name", "N/A")[:30],
                str(cohort.get("count", "N/A")),
                cohort.get("type", "N/A"),
                cohort.get("created_at", "N/A")[:10] if cohort.get("created_at") else "N/A",
            ])

        print(f"\n=== Cohorts ({len(cohorts)} total) ===")
        _print_table(headers, rows, min_widths=[8, 30, 10, 12, 12])

        if args.verbose and cohorts:
            print("\n=== First Cohort (JSON) ===")
            print(json.dumps(cohorts[0], indent=2))

    except Exception as e:
        print(f"Error listing cohorts: {e}")
        sys.exit(1)


# ─── insights ─────────────────────────────────────────────────────────────

def cmd_insights(client: PostHogClient, args: argparse.Namespace) -> None:
    """List insights."""
    try:
        insights = client.list_insights()

        if not insights:
            print("(no insights found)")
            return

        headers = ["ID", "Name", "Type", "Last Modified"]
        rows = []
        for insight in insights:
            query = insight.get("query", {})
            insight_type = query.get("kind", insight.get("filters", {}).get("insight", "unknown"))
            rows.append([
                str(insight.get("id", "N/A")),
                insight.get("name", "N/A")[:30],
                insight_type,
                insight.get("last_modified_at", "N/A")[:10] if insight.get("last_modified_at") else "N/A",
            ])

        print(f"\n=== Insights ({len(insights)} total) ===")
        _print_table(headers, rows, min_widths=[8, 30, 15, 15])

        if args.verbose and insights:
            print("\n=== First Insight (JSON) ===")
            print(json.dumps(insights[0], indent=2))

    except Exception as e:
        print(f"Error listing insights: {e}")
        sys.exit(1)


# ─── dashboards ───────────────────────────────────────────────────────────

def cmd_dashboards(client: PostHogClient, args: argparse.Namespace) -> None:
    """List dashboards."""
    try:
        dashboards = client.list_dashboards()

        if not dashboards:
            print("(no dashboards found)")
            return

        headers = ["ID", "Name", "Tiles", "Created"]
        rows = []
        for dash in dashboards:
            tiles = dash.get("tiles", [])
            rows.append([
                str(dash.get("id", "N/A")),
                dash.get("name", "N/A")[:30],
                str(len(tiles)),
                dash.get("created_at", "N/A")[:10] if dash.get("created_at") else "N/A",
            ])

        print(f"\n=== Dashboards ({len(dashboards)} total) ===")
        _print_table(headers, rows, min_widths=[8, 30, 8, 12])

        if args.verbose and dashboards:
            print("\n=== First Dashboard (JSON) ===")
            print(json.dumps(dashboards[0], indent=2))

    except Exception as e:
        print(f"Error listing dashboards: {e}")
        sys.exit(1)


# ─── stream ───────────────────────────────────────────────────────────────

def cmd_stream(client: PostHogClient, args: argparse.Namespace) -> None:
    """Stream live events from PostHog."""
    print("\n=== Live Event Stream ===")
    print(f"Polling every {args.interval}s, max {args.max_events} events")
    print("Press Ctrl+C to stop\n")

    try:
        count = 0
        for event in client.stream_events(interval=args.interval, max_events=args.max_events):
            count += 1
            ts = event.get("timestamp", "N/A")
            if ts:
                ts = ts[:19]
            print(f"[{count}] {ts} | {event.get('event', 'N/A')} | {event.get('distinct_id', 'N/A')[:20]}")

            if args.verbose:
                props = event.get("properties", {})
                if props:
                    for k, v in list(props.items())[:3]:
                        print(f"      {k}: {v}")

        print(f"\n✓ Stream complete ({count} events)")

    except KeyboardInterrupt:
        print(f"\n\n✓ Stream stopped by user ({count} events received)")
    except Exception as e:
        print(f"\nError streaming events: {e}")
        sys.exit(1)


# ─── identify ─────────────────────────────────────────────────────────────

def cmd_identify(client: PostHogClient, args: argparse.Namespace) -> None:
    """Send an identify event to PostHog."""
    try:
        properties = {}
        if args.properties:
            try:
                properties = json.loads(args.properties)
            except json.JSONDecodeError as e:
                print(f"Invalid JSON in --properties: {e}")
                sys.exit(1)

        result = client.identify(
            distinct_id=args.distinct_id,
            properties=properties,
        )

        print("✓ Identify event sent")
        print(f"  Distinct ID:  {args.distinct_id}")
        print(f"  Properties:   {len(properties)} keys")

        if args.verbose:
            print("\n=== Response ===")
            print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"Error sending identify: {e}")
        sys.exit(1)


# ─── batch ────────────────────────────────────────────────────────────────

def cmd_batch(client: PostHogClient, args: argparse.Namespace) -> None:
    """Generate and send batch test events."""
    import time

    try:
        events = []
        base_time = time.time()

        for i in range(args.count):
            event = {
                "event": args.event,
                "distinct_id": f"test_user_{i % 10}_{base_time}",
                "properties": {
                    "test": True,
                    "batch_index": i,
                    "load_test": True,
                },
                "timestamp": None,
            }
            events.append(event)

        result = client.batch_capture(events)

        print("✓ Batch capture complete")
        print(f"  Events sent:  {args.count}")
        print(f"  Event name: {args.event}")

        if args.verbose:
            print("\n=== Response ===")
            print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"Error sending batch: {e}")
        sys.exit(1)
# ─── main ─────────────────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # Global verbose flag
    p.add_argument("-v", "--verbose", action="store_true", help="Show verbose output including raw JSON")

    # settings
    sub.add_parser("settings", help="show current project settings")

    # update
    u = sub.add_parser("update", help="update project settings")
    u.add_argument("--session-recording", action="store_true", dest="session_recording", help="enable session recording")
    u.add_argument("--no-session-recording", action="store_false", dest="session_recording", help="disable session recording")
    u.add_argument("--sample-rate", type=float, help="session recording sample rate (0.0-1.0)")
    u.add_argument("--surveys", action="store_true", dest="surveys", help="enable surveys")
    u.add_argument("--no-surveys", action="store_false", dest="surveys", help="disable surveys")
    u.add_argument("--heatmaps", action="store_true", dest="heatmaps", help="enable heatmaps")
    u.add_argument("--no-heatmaps", action="store_false", dest="heatmaps", help="disable heatmaps")
    u.add_argument("--anonymize-ips", action="store_true", dest="anonymize_ips", help="enable IP anonymization")
    u.add_argument("--no-anonymize-ips", action="store_false", dest="anonymize_ips", help="disable IP anonymization")
    u.add_argument("--timezone", help="set project timezone (e.g., America/New_York)")
    u.add_argument("--name", help="set project name")

    # envs
    sub.add_parser("envs", help="list environments for the project")

    # events
    e = sub.add_parser("events", help="query events from the project")
    e.add_argument("--after", help="filter events after this date (YYYY-MM-DD)")
    e.add_argument("--before", help="filter events before this date (YYYY-MM-DD)")
    e.add_argument("--event", help="filter by specific event name")
    e.add_argument("--limit", type=int, default=50, help="maximum events to show (default: 50)")

    # sessions
    s = sub.add_parser("sessions", help="list recent session recordings")
    s.add_argument("--limit", type=int, default=20, help="maximum sessions to show (default: 20)")

    # logs
    sub.add_parser("logs", help="show log configuration")

    # capture
    c = sub.add_parser("capture", help="send a test event to PostHog")
    c.add_argument("--event", required=True, help="event name to capture")
    c.add_argument("--distinct-id", required=True, help="distinct ID for the event")
    c.add_argument("--properties", help='JSON string of properties (e.g., \'{"foo": "bar"}\')')

    # restrictions
    sub.add_parser("restrictions", help="show event ingestion restrictions")

    # configure-logs
    cl = sub.add_parser("configure-logs", help="configure log ingestion")
    cl.add_argument("--enable", action="store_true", dest="enable", help="enable log ingestion")
    cl.add_argument("--disable", action="store_false", dest="enable", help="disable log ingestion")
    cl.add_argument("--retention", type=int, help="log retention in days")

    # persons
    prs = sub.add_parser("persons", help="list persons (users)")
    prs.add_argument("--search", help="search by email or distinct_id")
    prs.add_argument("--limit", type=int, default=50, help="maximum results (default: 50)")

    # person
    ppr = sub.add_parser("person", help="show person details and events")
    ppr.add_argument("person_id", help="person ID to look up")

    # flags
    sub.add_parser("flags", help="list feature flags")

    # toggle-flag
    tf = sub.add_parser("toggle-flag", help="enable or disable a feature flag")
    tf.add_argument("flag_id", type=int, help="feature flag ID")
    tf.add_argument("--enable", action="store_true", help="enable the flag")
    tf.add_argument("--disable", action="store_true", help="disable the flag")

    # cohorts
    sub.add_parser("cohorts", help="list cohorts")

    # insights
    sub.add_parser("insights", help="list insights")

    # dashboards
    sub.add_parser("dashboards", help="list dashboards")

    # stream
    stm = sub.add_parser("stream", help="stream live events (Ctrl+C to stop)")
    stm.add_argument("--interval", type=int, default=5, help="poll interval in seconds (default: 5)")
    stm.add_argument("--max", type=int, default=100, dest="max_events", help="max events to stream (default: 100)")

    # identify
    idf = sub.add_parser("identify", help="send an identify event")
    idf.add_argument("--distinct-id", required=True, help="distinct ID for the user")
    idf.add_argument("--properties", help='JSON properties (e.g., \'{"plan": "pro"}\')')

    # batch
    bch = sub.add_parser("batch", help="send batch test events")
    bch.add_argument("--count", type=int, default=100, help="number of events (default: 100)")
    bch.add_argument("--event", default="test_load", help="event name (default: test_load)")

    args = p.parse_args()

    # Initialize client (reads from environment)
    try:
        client = PostHogClient()
    except Exception as e:
        print(f"Error initializing PostHog client: {e}")
        print("Ensure POSTHOG_API_KEY and POSTHOG_PROJECT_ID are set in your environment")
        sys.exit(1)

    # Dispatch to command handler
    commands = {
        "settings": cmd_settings,
        "update": cmd_update,
        "envs": cmd_envs,
        "events": cmd_events,
        "sessions": cmd_sessions,
        "logs": cmd_logs,
        "capture": cmd_capture,
        "restrictions": cmd_restrictions,
        "configure-logs": cmd_configure_logs,
        "persons": cmd_persons,
        "person": cmd_person,
        "flags": cmd_flags,
        "toggle-flag": cmd_toggle_flag,
        "cohorts": cmd_cohorts,
        "insights": cmd_insights,
        "dashboards": cmd_dashboards,
        "stream": cmd_stream,
        "identify": cmd_identify,
        "batch": cmd_batch,
    }

    commands[args.cmd](client, args)


if __name__ == "__main__":
    main()
