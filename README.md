# YaarWin Telegram Info Bot

## What it does

1. Login to the supplied demo account.
2. Open the Invitation Bonus Record page.
3. Accept a Telegram command such as:
   /info 123452
4. Find the UID on the currently visible record page and return the
   surrounding visible record text (including time/amount when those
   fields are visible).
5. /screenshot sends the current mobile-layout page screenshot.

## Telegram commands

/start
/setlogin NUMBER PASSWORD
/login
/info UID
/screenshot
/status
/stop

## Render

Use Docker runtime. Build Command and Start Command should be left blank
because Dockerfile handles installation and startup.

Environment variables:
BOT_TOKEN
ADMIN_CHAT_ID
DEMO_PHONE (optional)
DEMO_PASSWORD (optional)

The site can change its DOM/table structure. If /info cannot find the
UID even though it is visibly present, update the row/selector logic
against the current page HTML.

This project only reads and reports records. It does not place bets,
change balances, or modify transactions.
