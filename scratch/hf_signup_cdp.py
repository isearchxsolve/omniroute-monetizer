"""HF signup via the persistent CDP Chrome (real browser signals — hCaptcha invisible may pass).

Flow: fill step1 -> Next -> fill step2 -> terms -> Create Account ->
wait for hCaptcha to resolve (invisible pass OR manual solve in the visible window).
"""
import json
import time
from playwright.sync_api import sync_playwright

with open(r"d:\omniroute-monetizer\state\hf_experiment_account.json") as f:
    acct = json.load(f)


def activate_chrome_window():
    """Bring the CDP Chrome window to the foreground so the user can see the captcha."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        EnumWindows = user32.EnumWindows
        GetWindowTextW = user32.GetWindowTextW
        GetWindowTextLengthW = user32.GetWindowTextLengthW
        IsWindowVisible = user32.IsWindowVisible
        ShowWindow = user32.ShowWindow
        SetForegroundWindow = user32.SetForegroundWindow
        GetWindowThreadProcessId = user32.GetWindowThreadProcessId

        SW_RESTORE = 9
        # find the slim-profile CDP chrome main PID dynamically (fallback: any chrome window)
        target_pid = None
        try:
            import subprocess
            out = subprocess.run(
                ["wmic", "process", "where", "Name='chrome.exe'", "get", "ProcessId,CommandLine", "/format:csv"],
                capture_output=True, text=True, timeout=15,
            ).stdout
            for line in out.splitlines():
                if "omniroute-chrome-profile" in line and "--type=" not in line:
                    parts = line.strip().split(",")
                    if parts and parts[-1].isdigit():
                        target_pid = int(parts[-1])
                        break
        except Exception:
            pass
        print(f"[window] target CDP chrome pid: {target_pid}")
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum_cb(hwnd, lparam):
            if IsWindowVisible(hwnd):
                length = GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    GetWindowTextW(hwnd, buf, length + 1)
                    pid = wintypes.DWORD()
                    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    found.append((hwnd, buf.value, pid.value))
            return True

        EnumWindows(enum_cb, 0)
        # prefer the CDP chrome pid, else any window with "Chrome" in title
        candidates = [f for f in found if f[2] == target_pid] or [f for f in found if "chrome" in f[1].lower()]
        for hwnd, title, pid in candidates:
            ShowWindow(hwnd, SW_RESTORE)
            SetForegroundWindow(hwnd)
            print(f"[window] activated: {title[:60]} (pid {pid})")
            return True
        print("[window] no chrome window found to activate")
        return False
    except Exception as e:
        print(f"[window] activation failed: {e}")
        return False


def human_type(page, selector, text):
    el = page.locator(selector).first
    el.click()
    page.wait_for_timeout(200)
    page.keyboard.type(text, delay=45)

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        page.goto("https://huggingface.co/join", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_selector('input[name="email"]', state="visible", timeout=20000)
        page.wait_for_timeout(1500)
        print("form visible")

        # step 1
        human_type(page, 'input[name="email"]', acct["email"])
        human_type(page, 'input[name="password"]', acct["password"])
        page.wait_for_timeout(800)
        page.click('button[type="submit"]')
        print("step1 Next clicked")

        # wait for step 2
        page.wait_for_selector('input[name="username"]', state="visible", timeout=20000)
        print("step2 visible")
        page.wait_for_timeout(1000)

        human_type(page, 'input[name="username"]', acct["username"])
        if page.locator('input[name="fullname"]').count():
            human_type(page, 'input[name="fullname"]', acct["fullName"])
        # check terms checkbox(es)
        for cb in page.locator('input[type="checkbox"]:visible').all():
            try:
                if not cb.is_checked():
                    cb.check()
                    print("checkbox checked")
            except Exception:
                pass
        page.wait_for_timeout(800)

        btn = page.locator('button[type="submit"]:visible').last
        print("submit text:", btn.inner_text())
        activate_chrome_window()
        btn.click()
        print("Create Account clicked — waiting for hCaptcha resolution...")
        print("\n" + "=" * 70)
        print(">>> WATCH THE CHROME WINDOW NOW <<<")
        print(">>> An hCaptcha image challenge will pop up — solve it there. <<<")
        print("=" * 70 + "\n")

        # Poll up to 300s for outcome:
        #  - URL leaves /join  -> account created
        #  - body mentions verify/email -> created, needs verification
        #  - interactive hcaptcha challenge visible -> user solves it in the window
        #  - challenge-expired -> re-click submit to get a fresh challenge
        deadline = time.time() + 300
        outcome = None
        retriggers = 0
        last_expire_seen = 0
        while time.time() < deadline:
            page.wait_for_timeout(2000)
            url = page.url
            if "/join" not in url:
                outcome = "NAVIGATED: " + url
                break
            body = ""
            try:
                body = page.locator("body").inner_text(timeout=3000)
            except Exception:
                pass
            low = body.lower()
            if "verify your email" in low or "check your email" in low or "confirmation email" in low:
                outcome = "VERIFY_EMAIL_PAGE"
                break
            if "welcome" in low and "profile" in low:
                outcome = "WELCOME_PAGE"
                break
            # challenge expired? re-click submit for a fresh one (max 3 times)
            if "challenge-expired" in low and time.time() - last_expire_seen > 10:
                last_expire_seen = time.time()
                if retriggers < 3:
                    retriggers += 1
                    print(f"challenge expired — re-clicking Create Account (retry {retriggers}/3)")
                    try:
                        activate_chrome_window()
                        page.locator('button[type="submit"]:visible').last.click()
                    except Exception as e:
                        print("re-click failed:", e)
            # error messages (deduped)?
            for sel in ['[role="alert"]']:
                try:
                    for el in page.locator(sel).all()[:2]:
                        t = (el.inner_text(timeout=1000) or "").strip()
                        if t and len(t) < 200 and "challenge-expired" not in t:
                            print("ERR-ELEMENT:", t[:200])
                except Exception:
                    pass

        print("OUTCOME:", outcome or "TIMEOUT (still on /join)")
        print("final url:", page.url)
        try:
            print("final body (400):", page.locator("body").inner_text(timeout=3000)[:400].replace("\n", " | "))
        except Exception:
            pass
        # CDP-native screenshot (Playwright screenshot hangs on font-wait on this machine)
        try:
            import base64
            cdp = ctx.new_cdp_session(page)
            shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            with open(r"d:\omniroute-monetizer\evidence\hf_cdp_signup_final.png", "wb") as f:
                f.write(base64.b64decode(shot["data"]))
            print("screenshot: evidence/hf_cdp_signup_final.png")
        except Exception as e:
            print("screenshot failed:", e)

        # save cookies for later steps
        cookies = ctx.cookies()
        hf_cookies = [c for c in cookies if "huggingface" in c.get("domain", "")]
        with open(r"d:\omniroute-monetizer\state\hf_cdp_cookies.json", "w") as f:
            json.dump(hf_cookies, f, indent=2)
        print(f"saved {len(hf_cookies)} HF cookies to state/hf_cdp_cookies.json")
    finally:
        page.close()
