# UID Verification Bot — Read Only

This build is intentionally limited to:
- normal YaarWin website login
- keeping the authenticated browser session
- opening the Invitation Bonus / Record page
- `/info UID` read-only lookup
- screenshots/status/diagnostics

It contains no betting, staking, wager, deposit, or withdrawal actions.

## Render
Use a Background Worker with Docker:
- Dockerfile: `./Dockerfile`
- Docker context: `.`
- Build/start commands: leave blank

Environment:
- `BOT_TOKEN`
- `ADMIN_CHAT_ID`
- `HEADLESS=true`
- `POLL_SECONDS=2`

## Telegram
`/setlogin NUMBER PASSWORD`
`/login`
`/info UID`
`/screenshot`
`/diagnose`
`/status`
`/stop`

## Important
The login is performed through the site's normal browser flow. If YaarWin returns a server-side response such as `No operation permission`, this build reports that rejection and does not bypass it or fabricate authorization.


## Login behavior
The bot uses YaarWin's normal website login flow and keeps the authenticated
browser session available for read-only `/info UID` lookups. If the server
returns an authorization/permission error, the bot reports it rather than
attempting to bypass the site's controls.


## Login update
The browser context is configured to more closely match the normal mobile
Chrome environment shown in the successful browser request (locale, timezone,
viewport, mobile/touch mode and Chrome user-agent). The bot still uses the
website's normal login flow and does not inject or reuse live tokens/cookies.
