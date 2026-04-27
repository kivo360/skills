"""posthog_client.py — PostHog private API client for project management.

Uses httpx for synchronous HTTP requests to the PostHog API.
Supports both personal API key endpoints (organizations, projects) and
the public capture endpoint (event ingestion).

Config: reads posthog_api_key, posthog_project_id, posthog_host from Settings.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from config import get_settings

log = logging.getLogger(__name__)


class PostHogClient:
    """PostHog API client for organization/project management and event capture."""

    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.posthog_api_key
        self.project_id = settings.posthog_project_id
        self.host = settings.posthog_host.rstrip("/")
        self._client = httpx.Client(
            base_url=self.host,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make an HTTP request and return JSON response.

        Args:
            method: HTTP method (GET, POST, PATCH, etc.)
            path: API path (without base URL)
            **kwargs: Additional arguments for httpx request

        Returns:
            Parsed JSON response as dict

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses
        """
        try:
            response = self._client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            log.error(
                "PostHog API error: %s %s -> %s: %s",
                method,
                path,
                exc.response.status_code,
                exc.response.text,
            )
            raise
        except httpx.RequestError as exc:
            log.error("PostHog request error: %s %s -> %s", method, path, exc)
            raise

    # ── 1. ORGANIZATION ENDPOINTS ────────────────────────────────────────────

    def get_organization(self) -> dict[str, Any]:
        """Get current organization details.

        Returns:
            Organization data including id, name, slug, etc.
        """
        return self._request("GET", "/api/organizations/@current/")

    def list_projects(self) -> list[dict[str, Any]]:
        """List all projects in the current organization.

        Returns:
            List of project objects with id, name, api_token, etc.
        """
        data = self._request("GET", "/api/organizations/@current/projects/")
        return data.get("results", [])

    # ── 2. PROJECT ENDPOINTS ─────────────────────────────────────────────────

    def get_project(self, project_id: int | None = None) -> dict[str, Any]:
        """Get project details.

        Args:
            project_id: Project ID (defaults to configured project_id)

        Returns:
            Project data including id, name, settings, etc.
        """
        pid = project_id or self.project_id
        return self._request("GET", f"/api/organizations/@current/projects/{pid}/")

    def update_project(
        self,
        settings_dict: dict[str, Any],
        project_id: int | None = None,
    ) -> dict[str, Any]:
        """Update project settings.

        Args:
            settings_dict: Dictionary of settings to update
            project_id: Project ID (defaults to configured project_id)

        Returns:
            Updated project data
        """
        pid = project_id or self.project_id
        return self._request(
            "PATCH",
            f"/api/organizations/@current/projects/{pid}/",
            json=settings_dict,
        )

    # ── 3. ENVIRONMENT ENDPOINTS ───────────────────────────────────────────────

    def list_environments(
        self,
        project_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """List all environments for a project.

        Args:
            project_id: Project ID (defaults to configured project_id)

        Returns:
            List of environment objects
        """
        pid = project_id or self.project_id
        data = self._request("GET", f"/api/projects/{pid}/environments/")
        return data.get("results", [])

    def get_environment(
        self,
        env_id: str,
        project_id: int | None = None,
    ) -> dict[str, Any]:
        """Get environment details.

        Args:
            env_id: Environment ID
            project_id: Project ID (defaults to configured project_id)

        Returns:
            Environment data
        """
        pid = project_id or self.project_id
        return self._request("GET", f"/api/projects/{pid}/environments/{env_id}/")

    def update_environment(
        self,
        env_id: str,
        settings_dict: dict[str, Any],
        project_id: int | None = None,
    ) -> dict[str, Any]:
        """Update environment settings.

        Args:
            env_id: Environment ID
            settings_dict: Dictionary of settings to update
            project_id: Project ID (defaults to configured project_id)

        Returns:
            Updated environment data
        """
        pid = project_id or self.project_id
        return self._request(
            "PATCH",
            f"/api/projects/{pid}/environments/{env_id}/",
            json=settings_dict,
        )

    def get_event_ingestion_restrictions(
        self,
        env_id: str,
        project_id: int | None = None,
    ) -> dict[str, Any]:
        """Get event ingestion restrictions for an environment.

        Args:
            env_id: Environment ID
            project_id: Project ID (defaults to configured project_id)

        Returns:
            Ingestion restrictions configuration
        """
        pid = project_id or self.project_id
        return self._request(
            "GET",
            f"/api/projects/{pid}/environments/{env_id}/event_ingestion_restrictions/",
        )

    # ── 4. SESSION REPLAY ENDPOINTS ────────────────────────────────────────────

    def get_sessions(
        self,
        project_id: int | None = None,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        """Get session recordings for a project.

        Args:
            project_id: Project ID (defaults to configured project_id)
            **filters: Optional filters (person_id, after, before, etc.)

        Returns:
            List of session recording objects
        """
        pid = project_id or self.project_id
        params = {k: v for k, v in filters.items() if v is not None}
        data = self._request(
            "GET",
            f"/api/projects/{pid}/session_recordings/",
            params=params,
        )
        return data.get("results", [])

    # ── 5. EVENTS ENDPOINTS ──────────────────────────────────────────────────

    def get_events(
        self,
        project_id: int | None = None,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        """Get events for a project.

        Args:
            project_id: Project ID (defaults to configured project_id)
            **filters: Optional filters:
                - after: ISO timestamp
                - before: ISO timestamp
                - event: Event name filter
                - person_id: Person ID filter

        Returns:
            List of event objects
        """
        pid = project_id or self.project_id
        params = {k: v for k, v in filters.items() if v is not None}
        data = self._request("GET", f"/api/projects/{pid}/events/", params=params)
        return data.get("results", [])

    # ── 6. LOGS ENDPOINTS ────────────────────────────────────────────────────

    def get_logs(
        self,
        project_id: int | None = None,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        """Get plugin logs for a project.

        Args:
            project_id: Project ID (defaults to configured project_id)
            **filters: Optional filters (source, type, after, before, etc.)

        Returns:
            List of log entry objects
        """
        pid = project_id or self.project_id
        params = {k: v for k, v in filters.items() if v is not None}
        data = self._request("GET", f"/api/projects/{pid}/logs/", params=params)
        return data.get("results", [])

    # ── 7. EVENT CAPTURE (PUBLIC API) ────────────────────────────────────────

    def capture_event(
        self,
        event: str,
        distinct_id: str,
        properties: dict[str, Any] | None = None,
        project_id: int | None = None,
    ) -> dict[str, Any]:
        """Capture an event via the public ingestion API.

        Uses the project API key (different from personal API key).
        Note: This requires the project's API token, not the personal API key.

        Args:
            event: Event name
            distinct_id: Unique identifier for the user
            properties: Optional event properties
            project_id: Project ID (defaults to configured project_id)

        Returns:
            API response data
        """
        pid = project_id or self.project_id

        # Get project to find its API token for capture
        project = self.get_project(pid)
        api_token = project.get("api_token")

        if not api_token:
            raise ValueError(f"No api_token found for project {pid}")

        payload = {
            "api_key": api_token,
            "event": event,
            "distinct_id": distinct_id,
            "properties": properties or {},
        }

        # Capture endpoint uses different auth (project API key in body)
        response = self._client.post("/capture/", json=payload)
        response.raise_for_status()
        return response.json()

    # ── 8. HELPER METHODS ──────────────────────────────────────────────────────

    def enable_session_recording(
        self,
        project_id: int | None = None,
        sample_rate: str = "0.1",
    ) -> dict[str, Any]:
        """Enable session recording with specified sample rate.

        Args:
            project_id: Project ID (defaults to configured project_id)
            sample_rate: Recording sample rate (0.0 to 1.0 as string)

        Returns:
            Updated project data
        """
        return self.update_project(
            {
                "session_recording_opt_in": True,
                "session_recording_sample_rate": sample_rate,
            },
            project_id=project_id,
        )

    def configure_logs(
        self,
        project_id: int | None = None,
        enabled: bool = True,
        retention_days: int = 30,
    ) -> dict[str, Any]:
        """Configure plugin logs settings.

        Args:
            project_id: Project ID (defaults to configured project_id)
            enabled: Whether to enable logs
            retention_days: Log retention period in days

        Returns:
            Updated project data
        """
        return self.update_project(
            {
                "capture_plugin_logs": enabled,
                "plugin_logs_retention_days": retention_days,
            },
            project_id=project_id,
        )

    def toggle_feature_flags(
        self,
        project_id: int | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Enable or disable feature flags for a project.

        Args:
            project_id: Project ID (defaults to configured project_id)
            enabled: Whether to enable feature flags

        Returns:
            Updated project data
        """
        return self.update_project(
            {"enable_feature_flags": enabled},
            project_id=project_id,
        )

    def close(self) -> None:
        """Close the HTTP client connection."""
        self._client.close()

    def __enter__(self) -> PostHogClient:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()

    # ── 9. PERSON ENDPOINTS ───────────────────────────────────────────────────

    def list_persons(
        self,
        project_id: int | None = None,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        """List persons (users) for a project.

        Args:
            project_id: Project ID (defaults to configured project_id)
            **filters: Optional filters:
                - distinct_id: Filter by distinct ID
                - email: Filter by email address
                - limit: Maximum results to return

        Returns:
            List of person objects
        """
        pid = project_id or self.project_id
        params = {k: v for k, v in filters.items() if v is not None}
        data = self._request("GET", f"/api/projects/{pid}/persons/", params=params)
        return data.get("results", [])

    def get_person(
        self,
        person_id: str,
        project_id: int | None = None,
    ) -> dict[str, Any]:
        """Get a specific person by ID.

        Args:
            person_id: Person ID
            project_id: Project ID (defaults to configured project_id)

        Returns:
            Person data including properties, created_at, etc.
        """
        pid = project_id or self.project_id
        return self._request("GET", f"/api/projects/{pid}/persons/{person_id}/")

    def get_person_events(
        self,
        person_id: str,
        project_id: int | None = None,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        """Get events for a specific person.

        Args:
            person_id: Person ID
            project_id: Project ID (defaults to configured project_id)
            **filters: Optional filters (after, before, event, etc.)

        Returns:
            List of event objects for this person
        """
        pid = project_id or self.project_id
        params = {k: v for k, v in filters.items() if v is not None}
        data = self._request(
            "GET",
            f"/api/projects/{pid}/persons/{person_id}/events/",
            params=params,
        )
        return data.get("results", [])

    # ── 10. FEATURE FLAG ENDPOINTS ────────────────────────────────────────────

    def list_feature_flags(
        self,
        project_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """List all feature flags for a project.

        Args:
            project_id: Project ID (defaults to configured project_id)

        Returns:
            List of feature flag objects with key, active, filters, etc.
        """
        pid = project_id or self.project_id
        data = self._request("GET", f"/api/projects/{pid}/feature_flags/")
        return data.get("results", [])

    def get_feature_flag(
        self,
        flag_id: int,
        project_id: int | None = None,
    ) -> dict[str, Any]:
        """Get a specific feature flag by ID.

        Args:
            flag_id: Feature flag ID
            project_id: Project ID (defaults to configured project_id)

        Returns:
            Feature flag data
        """
        pid = project_id or self.project_id
        return self._request("GET", f"/api/projects/{pid}/feature_flags/{flag_id}/")

    def toggle_feature_flag(
        self,
        flag_id: int,
        active: bool = True,
        project_id: int | None = None,
    ) -> dict[str, Any]:
        """Enable or disable a feature flag.

        Args:
            flag_id: Feature flag ID
            active: Whether to enable (True) or disable (False) the flag
            project_id: Project ID (defaults to configured project_id)

        Returns:
            Updated feature flag data
        """
        pid = project_id or self.project_id
        return self._request(
            "PATCH",
            f"/api/projects/{pid}/feature_flags/{flag_id}/",
            json={"active": active},
        )

    # ── 11. COHORT ENDPOINTS ──────────────────────────────────────────────────

    def list_cohorts(
        self,
        project_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """List all cohorts for a project.

        Args:
            project_id: Project ID (defaults to configured project_id)

        Returns:
            List of cohort objects with name, count, filters, etc.
        """
        pid = project_id or self.project_id
        data = self._request("GET", f"/api/projects/{pid}/cohorts/")
        return data.get("results", [])

    def get_cohort(
        self,
        cohort_id: int,
        project_id: int | None = None,
    ) -> dict[str, Any]:
        """Get a specific cohort by ID.

        Args:
            cohort_id: Cohort ID
            project_id: Project ID (defaults to configured project_id)

        Returns:
            Cohort data including name, description, filters, count
        """
        pid = project_id or self.project_id
        return self._request("GET", f"/api/projects/{pid}/cohorts/{cohort_id}/")

    # ── 12. INSIGHT/DASHBOARD ENDPOINTS ───────────────────────────────────────

    def list_insights(
        self,
        project_id: int | None = None,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        """List all insights for a project.

        Args:
            project_id: Project ID (defaults to configured project_id)
            **filters: Optional filters (search, type, etc.)

        Returns:
            List of insight objects
        """
        pid = project_id or self.project_id
        params = {k: v for k, v in filters.items() if v is not None}
        data = self._request("GET", f"/api/projects/{pid}/insights/", params=params)
        return data.get("results", [])

    def list_dashboards(
        self,
        project_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """List all dashboards for a project.

        Args:
            project_id: Project ID (defaults to configured project_id)

        Returns:
            List of dashboard objects with name, description, tiles, etc.
        """
        pid = project_id or self.project_id
        data = self._request("GET", f"/api/projects/{pid}/dashboards/")
        return data.get("results", [])

    # ── 13. TESTING HELPERS ───────────────────────────────────────────────────

    def identify(
        self,
        distinct_id: str,
        properties: dict[str, Any] | None = None,
        project_id: int | None = None,
    ) -> dict[str, Any]:
        """Send an $identify event to associate properties with a user.

        Args:
            distinct_id: Unique identifier for the user
            properties: Optional person properties to set
            project_id: Project ID (defaults to configured project_id)

        Returns:
            API response data
        """
        pid = project_id or self.project_id

        # Get project to find its API token for capture
        project = self.get_project(pid)
        api_token = project.get("api_token")

        if not api_token:
            raise ValueError(f"No api_token found for project {pid}")

        payload = {
            "api_key": api_token,
            "event": "$identify",
            "distinct_id": distinct_id,
            "properties": {
                "$set": properties or {},
            },
        }

        response = self._client.post("/capture/", json=payload)
        response.raise_for_status()
        return response.json()

    def alias(
        self,
        distinct_id: str,
        alias: str,
        project_id: int | None = None,
    ) -> dict[str, Any]:
        """Send a $create_alias event to link two distinct IDs.

        Args:
            distinct_id: Primary distinct ID
            alias: Alias to create for this user
            project_id: Project ID (defaults to configured project_id)

        Returns:
            API response data
        """
        pid = project_id or self.project_id

        # Get project to find its API token for capture
        project = self.get_project(pid)
        api_token = project.get("api_token")

        if not api_token:
            raise ValueError(f"No api_token found for project {pid}")

        payload = {
            "api_key": api_token,
            "event": "$create_alias",
            "distinct_id": distinct_id,
            "properties": {
                "alias": alias,
            },
        }

        response = self._client.post("/capture/", json=payload)
        response.raise_for_status()
        return response.json()

    def batch_capture(
        self,
        events: list[dict[str, Any]],
        project_id: int | None = None,
    ) -> dict[str, Any]:
        """Send multiple events in a single batch request.

        Args:
            events: List of event dictionaries, each with:
                - event: Event name (required)
                - distinct_id: User ID (required)
                - properties: Optional event properties
                - timestamp: Optional ISO timestamp
            project_id: Project ID (defaults to configured project_id)

        Returns:
            API response data

        Raises:
            ValueError: If events list is empty
        """
        pid = project_id or self.project_id

        if not events:
            raise ValueError("Events list cannot be empty")

        # Get project to find its API token for capture
        project = self.get_project(pid)
        api_token = project.get("api_token")

        if not api_token:
            raise ValueError(f"No api_token found for project {pid}")

        # Format events for batch API
        batch_events = []
        for ev in events:
            batch_events.append({
                "event": ev["event"],
                "distinct_id": ev["distinct_id"],
                "properties": ev.get("properties", {}),
                "timestamp": ev.get("timestamp"),
            })

        payload = {
            "api_key": api_token,
            "batch": batch_events,
        }

        response = self._client.post("/batch/", json=payload)
        response.raise_for_status()
        return response.json()

    # ── 14. LIVE STREAM ───────────────────────────────────────────────────────

    def stream_events(
        self,
        project_id: int | None = None,
        interval: int = 5,
        max_events: int = 100,
        **filters: Any,
    ):
        """Generator that polls for new events and yields them.

        Useful for live debugging and monitoring event flow.

        Args:
            project_id: Project ID (defaults to configured project_id)
            interval: Seconds between polls (default: 5)
            max_events: Maximum total events to yield (default: 100)
            **filters: Optional filters passed to get_events (after, before, event, etc.)

        Yields:
            Event objects as they arrive

        Example:
            for event in client.stream_events(interval=3, max_events=50):
                print(f"New event: {event['event']} from {event['distinct_id']}")
        """
        import time

        pid = project_id or self.project_id
        seen_ids = set()
        events_yielded = 0

        while events_yielded < max_events:
            events = self.get_events(project_id=pid, limit=50, **filters)

            new_events = []
            for ev in events:
                ev_id = ev.get("id")
                if ev_id and ev_id not in seen_ids:
                    seen_ids.add(ev_id)
                    new_events.append(ev)

            # Yield new events in chronological order (oldest first)
            for ev in reversed(new_events):
                if events_yielded >= max_events:
                    break
                yield ev
                events_yielded += 1

            if events_yielded < max_events:
                time.sleep(interval)

if __name__ == "__main__":
    # Demo usage — requires POSTHOG_API_KEY in environment
    import os

    logging.basicConfig(level=logging.INFO)

    if not os.getenv("POSTHOG_API_KEY"):
        print("Set POSTHOG_API_KEY environment variable to run demo")
        exit(1)

    with PostHogClient() as client:
        # Organization info
        org = client.get_organization()
        print(f"Organization: {org.get('name')} ({org.get('id')})")

        # List projects
        projects = client.list_projects()
        print(f"\nProjects ({len(projects)}):")
        for p in projects:
            print(f"  - {p.get('name')} (ID: {p.get('id')})")

        # Current project
        if projects:
            project = client.get_project()
            print(f"\nCurrent project: {project.get('name')}")
            print(f"  API token: {project.get('api_token', 'N/A')[:20]}...")

        # List environments
        try:
            envs = client.list_environments()
            print(f"\nEnvironments ({len(envs)}):")
            for e in envs:
                print(f"  - {e.get('name')} (ID: {e.get('id')})")
        except httpx.HTTPStatusError as e:
            print(f"\nCould not list environments: {e}")

        # Recent events
        try:
            events = client.get_events(limit=5)
            print(f"\nRecent events ({len(events)}):")
            for ev in events[:5]:
                print(f"  - {ev.get('event')} @ {ev.get('timestamp', 'N/A')}")
        except httpx.HTTPStatusError as e:
            print(f"\nCould not fetch events: {e}")

    print("\n✅ Demo complete")


