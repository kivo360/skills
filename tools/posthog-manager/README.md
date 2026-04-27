# PostHog Manager

PostHog admin client + CLI extracted from the hunternet project. Lets you
manage PostHog project settings, query events/sessions/logs, and capture
test events from the terminal — without leaving the CLI to use the
PostHog dashboard.

## Files

```
posthog-manager/
├── posthog_client.py    PostHog private API client (settings, events, capture)
├── posthog_manager.py   CLI wrapping the client — run this directly
├── config.py            pydantic-settings config (loads from .env.local)
└── README.md            this file
```

## Setup

```bash
pip install httpx pydantic-settings
# or with uv:  uv add httpx pydantic-settings
```

Create `.env.local` in this directory (or pass env vars directly):

```
POSTHOG_API_KEY=phx_...                    # Personal API key (project scope)
POSTHOG_PROJECT_ID=12345                   # Numeric project ID
POSTHOG_HOST=https://us.i.posthog.com      # Or eu.i.posthog.com / self-hosted
```

## Usage

```bash
# View project settings
python posthog_manager.py settings

# Update session-recording config
python posthog_manager.py update --session-recording --sample-rate 0.5

# List environments
python posthog_manager.py envs

# Recent events
python posthog_manager.py events --after 2024-01-01 --limit 50

# Sessions
python posthog_manager.py sessions

# Logs
python posthog_manager.py logs

# Capture a test event
python posthog_manager.py capture --event "test_event" --distinct-id "user_123"

# Restrictions
python posthog_manager.py restrictions

# Configure log retention
python posthog_manager.py configure-logs --enable --retention 30
```

## Notes

- `config.py` was lifted from hunternet's full app config — it carries env
  vars unrelated to PostHog (Google Ads, Stripe, etc.). You can trim it
  down to just the `posthog_*` fields if you want, or leave it as-is and
  ignore the unused fields. `pydantic_settings` `extra="ignore"` won't
  complain about unset values.
- The client uses the **personal API key** for management endpoints
  (organizations, projects, events) and the **project capture key** for
  event ingestion. Both come from the same Settings object.
- Originally lived at `hunternet/scripts/posthog_manager.py` +
  `hunternet/app/clients/posthog_client.py`. Imports have been flattened
  for standalone use.
