import asyncio, json, logging, os, re
import aiohttp
from playwright.async_api import async_playwright

LOGIN_URL = "https://yaarwin.app/#/login"
RECORD_URL = "https://yaarwin.app/#/main/InvitationBonus/Record"

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
HEADLESS = os.getenv("HEADLESS", "true").lower() != "false"
POLL_SECONDS = float(os.getenv("POLL_SECONDS", "2"))

phone_value = ""
password_value = ""
pw = browser = context = page = None
logged_in = False
LOGIN_API_DIAG = "not observed"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("uid-bot")

def norm(s): return re.sub(r"\s+", " ", s or "").strip()

def is_admin(chat_id):
    try: return int(chat_id) == int(ADMIN_CHAT_ID)
    except: return False

async def tg(method, data=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.post(url, data=data or {}) as r:
            body = await r.text()
            if r.status >= 400: raise RuntimeError(f"Telegram API {r.status}: {body}")
            return json.loads(body)

async def send(chat_id, text):
    await tg("sendMessage", {"chat_id": str(chat_id), "text": text})

async def close_browser():
    global pw, browser, context, page, logged_in
    for obj, method in [(context, "close"), (browser, "close"), (pw, "stop")]:
        try:
            if obj: await getattr(obj, method)()
        except: pass
    pw = browser = context = page = None
    logged_in = False

async def visible(selectors):
    for sel in selectors:
        try:
            loc = page.locator(sel)
            for i in range(min(await loc.count(), 10)):
                x = loc.nth(i)
                if await x.is_visible(): return x
        except: pass
    return None

async def body():
    try: return await page.locator("body").inner_text(timeout=15000)
    except: return ""

async def login_form():
    p = await visible(['input[type="tel"]','input[placeholder*="phone" i]',
                       'input[placeholder*="mobile" i]','input[placeholder*="number" i]',
                       'input[name*="phone" i]','input[name*="mobile" i]',
                       'input[name*="username" i]'])
    pwf = await visible(['input[type="password"]','input[placeholder*="password" i]',
                         'input[name*="password" i]'])
    return bool(p and pwf)

async def screenshot(path="/tmp/debug.png"):
    try:
        await page.screenshot(path=path, full_page=True)
        return path
    except: return None


async def login_diagnostics():
    """Collect safe UI diagnostics without exposing the password value."""
    try:
        info = await page.evaluate("""
        () => {
          const all = [...document.querySelectorAll('*')];
          const hits = all.filter(el => {
            const t = (el.innerText || el.value || '').trim().toLowerCase();
            return t === 'log in' || t === 'login';
          }).slice(0, 10);

          return hits.map((el, i) => {
            const r = el.getBoundingClientRect();
            return {
              i,
              tag: el.tagName,
              text: (el.innerText || el.value || '').trim().slice(0,80),
              type: el.getAttribute('type'),
              role: el.getAttribute('role'),
              cls: typeof el.className === 'string' ? el.className.slice(0,200) : '',
              disabled: !!el.disabled,
              x: Math.round(r.x), y: Math.round(r.y),
              w: Math.round(r.width), h: Math.round(r.height),
              visible: !!(r.width && r.height)
            };
          });
        }
        """)
        log.info("LOGIN UI DIAGNOSTICS: %s", json.dumps(info, ensure_ascii=False))
        return info
    except Exception as e:
        log.warning("Login diagnostics failed: %s", e)
        return []

async def click_login():
    candidates = [
        page.get_by_role("button", name=re.compile(r"^\s*log\s*in\s*$", re.I)),
        page.get_by_text("Log in", exact=True),
        page.locator('button:has-text("Log in")'),
        page.locator('[role="button"]:has-text("Log in")'),
        page.locator('button[type="submit"]'),
        page.locator('input[type="submit"]'),
        page.locator('a:has-text("Log in")')
    ]
    await login_diagnostics()

    btn = None
    for loc in candidates:
        try:
            for i in range(min(await loc.count(), 20)):
                x = loc.nth(i)
                if await x.is_visible():
                    btn = x; break
            if btn: break
        except: pass
    if not btn:
        await screenshot("/tmp/login_button_not_found.png")
        raise RuntimeError("Visible 'Log in' button was not detected.")

    try: await btn.scroll_into_view_if_needed()
    except: pass
    await page.wait_for_timeout(500)

    # Prefer a real click; then force/mouse/DOM fallbacks.
    for mode in ("normal", "force"):
        try:
            await btn.click(timeout=15000, force=(mode=="force"))
            await page.wait_for_timeout(1200)
            log.info("Login click: %s", mode)
            return
        except Exception as e:
            log.info("Login %s click failed: %s", mode, e)

    try:
        box = await btn.bounding_box()
        if box:
            x, y = box["x"]+box["width"]/2, box["y"]+box["height"]/2
            await page.mouse.move(x, y, steps=5)
            await page.mouse.down(); await page.wait_for_timeout(100); await page.mouse.up()
            log.info("Login click: mouse")
            return
    except Exception as e: log.info("Mouse click failed: %s", e)

    try:
        await btn.evaluate("""el => {
            const r=el.getBoundingClientRect(), o={bubbles:true,cancelable:true,composed:true,
            view:window,clientX:r.left+r.width/2,clientY:r.top+r.height/2};
            try { el.dispatchEvent(new PointerEvent("pointerdown",o)); } catch(e){}
            el.dispatchEvent(new MouseEvent("mousedown",o));
            try { el.dispatchEvent(new PointerEvent("pointerup",o)); } catch(e){}
            el.dispatchEvent(new MouseEvent("mouseup",o));
            el.dispatchEvent(new MouseEvent("click",o));
            if (typeof el.click==="function") el.click();
        }""")
        log.info("Login click: DOM")
    except Exception as e:
        await screenshot("/tmp/login_click_failed.png")
        raise RuntimeError(f"Could not activate Log in control: {e}")

async def verify():
    global logged_in
    await page.wait_for_timeout(5000)
    if await login_form():
        return False, "The site is still showing the login form."
    await page.goto(RECORD_URL, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(3500)
    if "#/login" in page.url.lower() or await login_form():
        logged_in = False
        return False, "Protected page redirected back to login."
    text = (await body()).lower()
    for marker in ("please login","please log in","unauthorized","not authorized","session expired","login required"):
        if marker in text:
            logged_in = False
            return False, f"Protected page says: {marker}"
    logged_in = True
    return True, "Authenticated session verified by the protected record page."

async def do_login():
    global pw, browser, context, page
    if not phone_value or not password_value:
        raise RuntimeError("Login details missing. Use /setlogin NUMBER PASSWORD first.")
    await close_browser()
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=HEADLESS, args=[
        "--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--disable-setuid-sandbox"])
    context = await browser.new_context(
        viewport={"width": 390, "height": 844},
        screen={"width": 390, "height": 844},
        device_scale_factor=2,
        is_mobile=True,
        has_touch=True,
        locale="en-US",
        timezone_id="Asia/Kolkata",
        user_agent=(
            "Mozilla/5.0 (Linux; Android 13; Mobile) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/139.0.0.0 Mobile Safari/537.36"
        ),
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9"
        }
    )
    page = await context.new_page()
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(5000)

    phone = await visible(['input[type="tel"]','input[placeholder*="phone" i]',
        'input[placeholder*="mobile" i]','input[placeholder*="number" i]',
        'input[name*="phone" i]','input[name*="mobile" i]','input[name*="username" i]'])
    pwd = await visible(['input[type="password"]','input[placeholder*="password" i]',
        'input[name*="password" i]'])
    if not phone: raise RuntimeError("Phone number field was not detected.")
    if not pwd: raise RuntimeError("Password field was not detected.")
    await phone.fill(phone_value)
    await pwd.fill(password_value)
    await page.wait_for_timeout(700)

    # YaarWin submits the login through its web API.  Prefer the
    # form's native submit/keyboard path because SPA click handlers
    # can ignore synthetic element clicks.
    login_response = None

    try:
        async with page.expect_response(
            lambda r: "/api/webapi/Login" in r.url and r.request.method == "POST",
            timeout=15000
        ) as response_info:
            try:
                await pwd.press("Enter")
            except Exception:
                await click_login()

        login_response = await response_info.value
        global LOGIN_API_DIAG
        LOGIN_API_DIAG = f"observed HTTP {login_response.status}"
        log.info("Login API response received: %s %s",
                 login_response.status, login_response.url)

        try:
            payload = await login_response.json()
            # Never log tokens/passwords/session fields.
            code = payload.get("code")
            msg = str(payload.get("msg") or payload.get("message") or "")
            log.info("Login API returned code=%s msg=%s", code, msg)
            if str(code) not in ("0", "200") and msg:
                raise RuntimeError(f"YaarWin login rejected the request: {msg}")
        except RuntimeError:
            raise
        except Exception:
            pass

    except Exception as e:
        log.info("Native submit/API wait failed: %s", e)

        # Fallback: use all click strategies, then wait briefly for the
        # same endpoint to appear in the page's network traffic.
        await click_login()
        await page.wait_for_timeout(7500)

    await page.wait_for_timeout(2500)

    ok, reason = await verify()
    if not ok:
        await screenshot("/tmp/login_failed_debug.png")
        if LOGIN_API_DIAG.startswith("server rejected login:"):
            raise RuntimeError(
                "YaarWin server rejected the login request: "
                + LOGIN_API_DIAG
                + ". This is a server-side authorization/context rejection, "
                  "not a Telegram button-click error."
            )
        raise RuntimeError("Login was NOT verified. " + reason)
    return reason

async def query_uid(uid):
    global logged_in
    if not logged_in: await do_login()
    await page.goto(RECORD_URL, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(3000)
    if "#/login" in page.url.lower() or await login_form():
        logged_in = False
        raise RuntimeError("Saved login session expired. Use /login again.")
    text = await body()
    lines = [norm(x) for x in text.splitlines() if norm(x)]
    out = []
    for i, line in enumerate(lines):
        if str(uid).strip() in line:
            out.append(" | ".join(lines[max(0,i-1):min(len(lines),i+4)]))
    return out

async def handle(chat_id, text):
    global phone_value, password_value
    if not is_admin(chat_id): return
    p = text.strip().split()
    if not p: return
    cmd = p[0].split("@")[0].lower()

    if cmd == "/start":
        await send(chat_id, "/setlogin NUMBER PASSWORD\n/login\n/info UID\n/screenshot\n/status\n/stop")
    elif cmd == "/setlogin":
        if len(p) != 3:
            await send(chat_id, "Use:\n/setlogin NUMBER PASSWORD"); return
        phone_value, password_value = p[1], p[2]
        await close_browser()
        await send(chat_id, "Login details saved in memory.\nNow use /login.")
    elif cmd == "/login":
        try: await send(chat_id, "Checking website login..."); reason=await do_login()
        except Exception as e: await send(chat_id, f"Login NOT verified.\n\n{type(e).__name__}: {e}\n\nUse /screenshot to inspect the page.")
        else: await send(chat_id, "Login verified successfully.\n\n"+reason)
    elif cmd == "/info":
        if len(p)!=2: await send(chat_id, "Use:\n/info 123452"); return
        try:
            rows=await query_uid(p[1])
            if rows:
                await send(chat_id, f"UID: {p[1]}\n\nRecord:\n" + "\n".join(f"{i+1}. {x}" for i,x in enumerate(rows[:5])))
            else: await send(chat_id, f"UID: {p[1]}\nStatus: Record not found on the current page.")
        except Exception as e: await send(chat_id, f"Info error:\n{type(e).__name__}: {e}")
    elif cmd == "/diagnose":
        if not page:
            await send(chat_id, "Browser is not open. Use /login first.")
            return
        try:
            info = await login_diagnostics()
            path = "/tmp/login_diagnose.png"
            await page.screenshot(path=path, full_page=False)
            summary = []
            for x in info:
                summary.append(
                    f"{x['i']}: {x['tag']} text={x['text']!r} "
                    f"role={x['role']!r} type={x['type']!r} "
                    f"visible={x['visible']} disabled={x['disabled']} "
                    f"box={x['x']},{x['y']} {x['w']}x{x['h']}"
                )
            msg = "Login UI diagnostics:\\n\\n" + (
                "\\n".join(summary) if summary else "No exact Log in/Login text element found."
            )
            await send(chat_id, msg[:3900])
            with open(path, "rb") as f:
                form = aiohttp.FormData()
                form.add_field("chat_id", str(chat_id))
                form.add_field("photo", f, filename="login_diagnose.png", content_type="image/png")
                await tg("sendPhoto", form)
        except Exception as e:
            await send(chat_id, f"Diagnose error:\\n{type(e).__name__}: {e}")

    elif cmd == "/screenshot":
        if not page: await send(chat_id, "Browser is not open. Use /login first."); return
        path="/tmp/current_screen.png"
        try:
            await page.screenshot(path=path, full_page=False)
            with open(path,"rb") as f:
                form=aiohttp.FormData(); form.add_field("chat_id",str(chat_id))
                form.add_field("photo",f,filename="screen.png",content_type="image/png")
                await tg("sendPhoto",form)
        except Exception as e: await send(chat_id, f"Screenshot error:\n{e}")
    elif cmd == "/status":
        await send(chat_id, f"Browser open: {bool(page)}\nLogin configured: {bool(phone_value and password_value)}\nLogin verified: {logged_in}\nLogin API: {LOGIN_API_DIAG}\nCurrent page: {page.url if page else '-'}")
    elif cmd == "/help":
        await send(chat_id, "/setlogin NUMBER PASSWORD\n/login\n/info UID\n/screenshot\n/diagnose\n/status\n/stop")
    elif cmd == "/stop":
        await close_browser()
        await send(chat_id, "Browser stopped.")

async def main():
    if not BOT_TOKEN: raise SystemExit("BOT_TOKEN is missing.")
    if not ADMIN_CHAT_ID: raise SystemExit("ADMIN_CHAT_ID is missing.")
    offset=None
    try:
        r=await tg("getUpdates",{"offset":-1,"timeout":0,"allowed_updates":json.dumps(["message"])})
        if r.get("result"): offset=r["result"][-1]["update_id"]+1
    except: pass
    log.info("UID Verification Bot started")
    while True:
        try:
            params={"timeout":25,"allowed_updates":json.dumps(["message"])}
            if offset is not None: params["offset"]=offset
            r=await tg("getUpdates",params)
            for u in r.get("result",[]):
                offset=u["update_id"]+1
                m=u.get("message",{}); c=m.get("chat",{}).get("id"); t=m.get("text","")
                if c and t: await handle(c,t)
        except asyncio.CancelledError: raise
        except Exception as e:
            log.error("Polling error: %s",e)
            await asyncio.sleep(max(3,POLL_SECONDS))

if __name__=="__main__":
    asyncio.run(main())
