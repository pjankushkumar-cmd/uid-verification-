UID Verification Bot — diagnostic login build

Render:
- Background Worker
- Docker
- Dockerfile: ./Dockerfile
- Docker context: .
- No build/start command
- Environment: BOT_TOKEN, ADMIN_CHAT_ID, HEADLESS=true, POLL_SECONDS=2

Telegram:
 /setlogin NUMBER PASSWORD
 /login
 /diagnose
 /info UID
 /screenshot
 /status
 /stop

This bot is read-only: it logs in and reads visible records; it does not place bets or submit wagers.
The /diagnose command reports the rendered Log in/Login element details without printing the password value.
