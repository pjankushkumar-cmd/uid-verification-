
import asyncio
import json
import logging
import os
import re
from pathlib import Path

import aiohttp
from playwright.async_api import async_playwright

LOGIN_URL = "https://yaarwin.app/#/login"
RECORD_URL = "https://yaarwin.app/#/main/InvitationBonus/Record"

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
DEMO_PHONE = os.getenv("DEMO_PHONE", "")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "")

HEADLESS = os.getenv("HEADLESS", "true").lower() != "false"
POLL_SECONDS = float(os.getenv("POLL_SECONDS", "2"))

phone_value = DEMO_PHONE
password_value = DEMO_PASSWORD

pw = None
browser = None
context = None
page = None
poll_task = None

log = logging.getLogger("yaarwin-info-bot")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


def is_admin(chat_id):
    try:
        return int(chat_id) == int(ADMIN_CHAT_ID)
    except Exception:
        return False


async def tg(method, data=None):
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    timeout = aiohttp.ClientTimeout(total=45)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, data=data or {}) as response:
            body = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"Telegram API {response.status}: {body}")
            return json.loads(body)


async def send(chat_id, text):
    await tg("sendMessage", {
        "chat_id": str(chat_id),
        "text": text
    })


async def shutdown_browser():
    global pw, browser, context, page

    try:
        if context:
            await context.close()
    except Exception:
        pass

    try:
        if browser:
            await browser.close()
    except Exception:
        pass

    try:
        if pw:
            await pw.stop()
    except Exception:
        pass

    pw = browser = context = page = None


async def first_visible(selectors):
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if await loc.count() and await loc.is_visible():
                return loc
        except Exception:
            pass
    return None


async def ensure_login():
    global pw, browser, context, page

    if not phone_value or not password_value:
        raise RuntimeError(
            "Demo login missing. Use /setlogin NUMBER PASSWORD first."
        )

    await shutdown_browser()

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=HEADLESS,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu"
        ]
    )

    context = await browser.new_context(
        viewport={"width": 390, "height": 844},
        device_scale_factor=2,
        is_mobile=True,
        has_touch=True
    )

    page = await context.new_page()

    await page.goto(
        LOGIN_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )
    await page.wait_for_timeout(2500)

    phone = await first_visible([
        'input[type="tel"]',
        'input[placeholder*="phone" i]',
        'input[placeholder*="mobile" i]',
        'input[placeholder*="number" i]',
        'input[name*="phone" i]',
        'input[name*="mobile" i]',
        'input[name*="username" i]',
    ])

    password = await first_visible([
        'input[type="password"]',
        'input[placeholder*="password" i]',
        'input[name*="password" i]',
    ])

    if not phone or not password:
        await page.screenshot(
            path="login_debug.png",
            full_page=True
        )
        raise RuntimeError(
            "Login fields not detected. login_debug.png saved."
        )

    await phone.fill(phone_value)
    await password.fill(password_value)

    login_button = await first_visible([
        'button[type="submit"]',
        'input[type="submit"]',
    ])

    if not login_button:
        try:
            loc = page.get_by_role(
                "button",
                name=re.compile(r"login|log in|sign in", re.I)
            ).first
            if await loc.count() and await loc.is_visible():
                login_button = loc
        except Exception:
            pass

    if not login_button:
        await page.screenshot(
            path="login_button_debug.png",
            full_page=True
        )
        raise RuntimeError(
            "Login button not detected. login_button_debug.png saved."
        )

    await login_button.click()
    await page.wait_for_timeout(4500)

    log.info("Login completed")


async def open_records():
    if not page:
        await ensure_login()

    await page.goto(
        RECORD_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )
    await page.wait_for_timeout(2500)


async def read_record_text():
    return await page.locator("body").inner_text(timeout=15000)


def normalize(s):
    return re.sub(r"\s+", " ", s or "").strip()


def find_uid_rows(text, uid):
    lines = [normalize(x) for x in text.splitlines() if normalize(x)]
    target = str(uid).strip()

    # First try rows/lines containing the exact UID.
    matches = []
    for i, line in enumerate(lines):
        if target in line:
            left = max(0, i - 1)
            right = min(len(lines), i + 3)
            matches.append(" | ".join(lines[left:right]))

    return matches


async def query_uid(uid):
    await open_records()

    text = await read_record_text()
    matches = find_uid_rows(text, uid)

    if not matches:
        # Try the page's visible text with a more permissive whitespace pattern.
        compact = normalize(text)
        if str(uid) in compact:
            pos = compact.find(str(uid))
            matches = [compact[max(0, pos - 180):pos + 420]]

    return matches, text


def format_info(uid, matches):
    if not matches:
        return (
            f"UID: {uid}\n"
            f"Status: Record not found on the current page."
        )

    out = [
        f"UID: {uid}",
        "",
        "Record:",
    ]

    for n, match in enumerate(matches[:5], 1):
        out.append(f"{n}. {match}")

    out.append("")
    out.append(
        "Note: The bot returns the visible record text from the site; "
        "field names depend on the site's current page layout."
    )

    return "\n".join(out)


async def handle_command(chat_id, text):
    global phone_value, password_value

    if not is_admin(chat_id):
        return

    parts = text.strip().split()

    if not parts:
        return

    command = parts[0].split("@")[0].lower()

    if command == "/start":
        await send(
            chat_id,
            "YaarWin Info Bot\n\n"
            "/setlogin NUMBER PASSWORD\n"
            "/login\n"
            "/info UID\n"
            "/screenshot\n"
            "/status\n"
            "/stop"
        )

    elif command == "/setlogin":
        if len(parts) != 3:
            await send(
                chat_id,
                "Use:\n/setlogin DEMO_NUMBER DEMO_PASSWORD"
            )
            return

        phone_value = parts[1]
        password_value = parts[2]

        await send(
            chat_id,
            "Demo login saved in memory.\nUse /login to test it."
        )

    elif command == "/login":
        try:
            await ensure_login()
            await send(
                chat_id,
                "Login successful."
            )
        except Exception as exc:
            await send(
                chat_id,
                f"Login error:\n{type(exc).__name__}: {exc}"
            )

    elif command == "/info":
        if len(parts) != 2:
            await send(
                chat_id,
                "Use:\n/info 123452"
            )
            return

        uid = parts[1]

        try:
            matches, _ = await query_uid(uid)
            await send(
                chat_id,
                format_info(uid, matches)
            )
        except Exception as exc:
            await send(
                chat_id,
                f"Info error:\n{type(exc).__name__}: {exc}"
            )

    elif command == "/screenshot":
        if not page:
            await send(
                chat_id,
                "Browser is not open. Use /login first."
            )
            return

        path = "record_mobile.png"

        try:
            await page.screenshot(
                path=path,
                full_page=False
            )

            with open(path, "rb") as photo:
                form = aiohttp.FormData()
                form.add_field("chat_id", str(chat_id))
                form.add_field(
                    "photo",
                    photo,
                    filename="record_mobile.png",
                    content_type="image/png"
                )

                await tg("sendPhoto", form)
        except Exception as exc:
            await send(
                chat_id,
                f"Screenshot error:\n{type(exc).__name__}: {exc}"
            )

    elif command == "/status":
        await send(
            chat_id,
            "Status\n\n"
            f"Browser open: {bool(page)}\n"
            f"Login configured: {bool(phone_value and password_value)}"
        )

    elif command == "/stop":
        global poll_task
        if poll_task and not poll_task.done():
            poll_task.cancel()
        poll_task = None
        await shutdown_browser()
        await send(chat_id, "Bot browser stopped.")


async def telegram_poll():
    offset = None

    while True:
        try:
            params = {
                "timeout": 25,
                "allowed_updates": json.dumps(["message"])
            }

            if offset is not None:
                params["offset"] = offset

            result = await tg("getUpdates", params)

            for item in result.get("result", []):
                offset = item["update_id"] + 1

                message = item.get("message") or {}
                chat = message.get("chat") or {}
                chat_id = chat.get("id")
                text = message.get("text", "")

                if chat_id and text:
                    await handle_command(chat_id, text)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("Telegram polling error: %s", exc)
            await asyncio.sleep(3)


async def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is missing.")

    if not ADMIN_CHAT_ID:
        raise SystemExit("ADMIN_CHAT_ID is missing.")

    log.info("YaarWin Info Bot started")
    await telegram_poll()


if __name__ == "__main__":
    asyncio.run(main())
