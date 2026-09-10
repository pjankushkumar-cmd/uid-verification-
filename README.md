UID Verification Bot — API-aware login build

This version keeps the site UI as the source of truth but waits for the site's
native Login form submission and observes the POST /api/webapi/Login response.
It does not hard-code credentials, session tokens, or authorization headers.

Render:
- Background Worker
- Docker
- Dockerfile: ./Dockerfile
- Docker context: .
- No build/start command
- BOT_TOKEN, ADMIN_CHAT_ID, HEADLESS=true, POLL_SECONDS=2

Telegram:
 /setlogin NUMBER PASSWORD
 /login
 /info UID
 /screenshot
 /status
 /stop

Read-only: no betting/staking actions.
