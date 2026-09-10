UID Verification Bot — Login Final Build

Purpose:
- Log into the user's YaarWin account through the website's normal login flow.
- Observe the site's own POST /api/webapi/Login response.
- Verify success only when the API reports success AND the protected record page is accessible.
- Keep the browser session for later read-only UID record lookup.

Render:
- Background Worker
- Docker
- Dockerfile: ./Dockerfile
- Docker context: .
- No build/start command
- Environment:
  BOT_TOKEN
  ADMIN_CHAT_ID
  HEADLESS=true
  POLL_SECONDS=2

Telegram:
  /setlogin NUMBER PASSWORD
  /login
  /screenshot
  /status
  /info UID
  /stop

Important:
- No betting, staking, withdrawal, or wager actions.
- The bot does not hard-code passwords, cookies, authorization tokens, or session tokens.
- If the website itself returns an error such as "No operation permission",
  the bot reports that response instead of trying to bypass the site's controls.
