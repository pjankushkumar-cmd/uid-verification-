# YaarWin UID Verification Bot

Read-only Telegram bot for logging into the supplied website account and reading visible Invitation Bonus records.

## Important login change

The bot no longer treats a login-button click as a successful login. After clicking Login it:

1. waits for the SPA transition;
2. checks that the login form is gone;
3. opens the protected Invitation Bonus Record route;
4. verifies the site did not redirect back to `#/login`;
5. checks for obvious authentication/session errors;
6. uses the authenticated record page as the final verification signal.

If verification fails, Telegram receives **Login NOT verified** instead of a false success message. A debug screenshot is also saved in the container when possible.

## Render

Create a **Background Worker** using Docker.

- Dockerfile: `./Dockerfile`
- Docker context: `.`
- Build command: leave blank
- Start command: leave blank (Dockerfile CMD starts the bot)

Environment variables:

- `BOT_TOKEN` = Telegram bot token
- `ADMIN_CHAT_ID` = your Telegram chat ID
- `HEADLESS` = `true`
- `POLL_SECONDS` = `2`

## Telegram commands

`/start`

`/setlogin NUMBER PASSWORD`

`/login` - performs real login verification

`/info UID` - reads matching visible record text

`/screenshot` - sends current browser screenshot

`/status`

`/stop`

Credentials are kept only in process memory by this version. Avoid posting sensitive credentials anywhere except the bot chat you control.

This bot is read-only: it does not place bets, submit transactions, or modify records.
