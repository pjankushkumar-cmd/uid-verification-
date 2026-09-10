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
logged_in = False

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
    global pw, browser, context, page, logged_in

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
    logged_in = False


async def first_visible(selectors):
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if await loc.count() and await loc.is_visible():
                return loc
        except Exception:
            pass
    return None


async def body_text():
    try:
        return await page.locator("body").inner_text(timeout=10000)
    except Exception:
        return ""


def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip().lower()


async def has_login_form():
    """True when the page still visibly looks like the login screen."""
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
    return bool(phone and password)


async def has_logout_marker():
    """Look for a normal authenticated/account UI marker."""
    selectors = [
        'text=/^logout$/i',
        'text=/^log out$/i',
        'text=/^sign out$/i',
        'text=/logout/i',
        'text=/log out/i',
        'text=/sign out/i',
        'button:has-text("Logout")',
        'button:has-text("Log out")',
        'button:has-text("Sign out")',
    ]

    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if await loc.count() and await loc.is_visible():
                return True
        except Exception:
            pass

    text = clean_text(await body_text())
    return bool(re.search(r"\b(logout|log out|sign out)\b", text))


async def verify_authenticated_session():
    """Verify the site accepted the credentials instead of trusting the click."""
    global logged_in

    # Give the SPA time to finish its API request/router transition.
    await page.wait_for_timeout(2500)

    current_url = page.url
    login_form = await has_login_form()
    logout_marker = await has_logout_marker()

    # If we are still on the login route and the login form remains, it failed.
    if login_form and "#/login" in current_url.lower():
        return False, "The site is still showing the login form. Credentials may be wrong or login was rejected."

    # Test an authenticated-only route. This is stronger than checking a button click.
    try:
        await page.goto(
            RECORD_URL,
            wait_until="domcontentloaded",
            timeout=60000
        )
        await page.wait_for_timeout(2500)
    except Exception as exc:
        return False, f"Could not open the protected record page: {type(exc).__name__}: {exc}"

    protected_url = page.url
    protected_has_login = await has_login_form()
    protected_text = clean_text(await body_text())
    protected_logout = await has_logout_marker()

    # A redirect back to #/login or a visible login form means the session did not authenticate.
    if "#/login" in protected_url.lower() or protected_has_login:
        return False, "The site redirected back to the login screen, so the account session was not authenticated."

    # If the protected page loads and shows account/logout markers, this is a strong success signal.
    # If there is no logout text, the protected route itself is still our primary verification.
    logged_in = True

    if protected_logout or logout_marker:
        return True, "Authenticated session verified; account UI/logout marker is visible."

    # Reject obvious access-denied/login text even if the URL did not redirect.
    if any(x in protected_text for x in [
        "please login",
        "please log in",
        "unauthorized",
        "not authorized",
        "session expired",
    ]):
        logged_in = False
        return False, "The protected page reports that authentication is required or the session expired."

    return True, "Authenticated session verified by successfully opening the protected record page."


async def ensure_login():
    global pw, browser, context, page, logged_in

    if not phone_value or not password_value:
        raise RuntimeError(
            "Login details missing. Use /setlogin NUMBER PASSWORD first."
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
        await page.screenshot(path="login_debug.png", full_page=True)
        raise RuntimeError("Login fields not detected. login_debug.png saved.")

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
        await page.screenshot(path="login_button_debug.png", full_page=True)
        raise RuntimeError("Login button not detected. login_button_debug.png saved.")

    await login_button.click()

    ok, reason = await verify_authenticated_session()
    if not ok:
        try:
            await page.screenshot(path="login_failed_debug.png", full_page=True)
        except Exception:
            pass
        logged_in = False
        raise RuntimeError(f"Login was NOT verified. {reason}")

    log.info("%s", reason)
    return reason


async def open_records():
    global logged_in

    if not page or not logged_in:
        await ensure_login()
        return

    await page.goto(
        RECORD_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )
    await page.wait_for_timeout(2000)

    # Re-check that the protected route did not throw us back to login.
    if "#/login" in page.url.lower() or await has_login_form():
        logged_in = False
        raise RuntimeError("The saved login session expired or the site redirected to login. Use /login again.")


async def read_record_text():
    return await page.locator("body").inner_text(timeout=15000)


def normalize(s):
    return re.sub(r"\s+", " ", s or "").strip()


def find_uid_rows(text, uid):
    lines = [normalize(x) for x in text.splitlines() if normalize(x)]
    target = str(uid).strip()

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

    out = [f"UID: {uid}", "", "Record:"]

    for n, match in enumerate(matches[:5], 1):
        out.append(f"{n}. {match}")

    out.append("")
    out.append(
        "Note: This is read-only information taken from the visible record page."
    )
    return "\n".join(out)


async def handle_command(chat_id, text):
    global phone_value, password_value, poll_task

    if not is_admin(chat_id):
        return

    parts = text.strip().split()
    if not parts:
        return

    command = parts[0].split("@")[0].lower()

    if command == "/start":
        await send(
            chat_id,
            "YaarWin UID Verification Bot\n\n"
            "/setlogin NUMBER PASSWORD\n"
            "/login - verify real login\n"
            "/info UID - read record\n"
            "/screenshot\n"
            "/status\n"
            "/stop"
        )

    elif command == "/setlogin":
        if len(parts) != 3:
            await send(chat_id, "Use:\n/setlogin NUMBER PASSWORD")
            return

        phone_value = parts[1]
        password_value = parts[2]

        # Force the next operation to establish a fresh authenticated session.
        await shutdown_browser()

        await send(
            chat_id,
            "Login details saved in memory.\nNow use /login to verify the website session."
        )

    elif command == "/login":
        try:
            reason = await ensure_login()
            await send(chat_id, f"Login verified successfully.\n\n{reason}")
        except Exception as exc:
            await send(
                chat_id,
                f"Login NOT verified.\n\n{type(exc).__name__}: {exc}\n\n"
                "A debug screenshot was saved on the bot server if the browser reached the page."
            )

    elif command == "/info":
        if len(parts) != 2:
            await send(chat_id, "Use:\n/info 123452")
            return

        uid = parts[1]

        try:
            matches, _ = await query_uid(uid)
            await send(chat_id, format_info(uid, matches))
        except Exception as exc:
            await send(
                chat_id,
                f"Info error:\n{type(exc).__name__}: {exc}"
            )

    elif command == "/screenshot":
        if not page:
            await send(chat_id, "Browser is not open. Use /login first.")
            return

        path = "record_mobile.png"

        try:
            await page.screenshot(path=path, full_page=False)

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
            f"Login details configured: {bool(phone_value and password_value)}\n"
            f"Login verified: {logged_in}\n"
            f"Current page: {page.url if page else '-'}"
        )

    elif command == "/stop":
        if poll_task and not poll_task.done():
            poll_task.cancel()
        poll_task = None
        await shutdown_browser()
        await send(chat_id, "Bot browser stopped.")


async def telegram_poll():
    offset = None

    # Clear any old queued updates before starting. This does not solve a second
    # running bot instance; only one getUpdates consumer can use a token at once.
    try:
        old = await tg("getUpdates", {
            "offset": -1,
            "timeout": 0,
            "allowed_updates": json.dumps(["message"])
        })
        if old.get("result"):
            offset = old["result"][-1]["update_id"] + 1
    except Exception:
        pass

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
            await asyncio.sleep(max(3, POLL_SECONDS))


async def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is missing.")

    if not ADMIN_CHAT_ID:
        raise SystemExit("ADMIN_CHAT_ID is missing.")

    log.info("YaarWin UID Verification Bot started")
    await telegram_poll()


if __name__ == "__main__":
    asyncio.run(main())
