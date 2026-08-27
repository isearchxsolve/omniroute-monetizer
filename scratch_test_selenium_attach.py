"""scratch_test_selenium_attach.py — does Selenium attach to live Chrome :9222 and run JS?"""
import sys, time

def step(name):
    print(f"[{time.strftime('%H:%M:%S')}] {name}", flush=True)

step("1. import selenium")
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

step("2. build options with debuggerAddress=127.0.0.1:9222")
opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

step("3. webdriver.Chrome (Selenium Manager fetches matching chromedriver)")
t0 = time.perf_counter()
driver = webdriver.Chrome(options=opts)
step(f"   attached in {time.perf_counter()-t0:.1f}s")

step("4. window handles")
handles = driver.window_handles
step(f"   {len(handles)} windows")

step("5. current url + title")
print(f"   url={driver.current_url}", flush=True)

step("6. execute_script trivial")
r = driver.execute_script("return 1+1;")
print(f"   1+1 -> {r}", flush=True)

step("7. execute_async_script fetch on current tab")
driver.set_script_timeout(30)
JS = """
const cb = arguments[arguments.length-1];
(async () => {
  try {
    const r = await fetch(location.origin + '/', { method:'GET', credentials:'include' });
    cb({ ok:true, status:r.status, url:r.url });
  } catch(e) { cb({ ok:false, error:String(e) }); }
})();
"""
r = driver.execute_async_script(JS)
print(f"   fetch -> {r}", flush=True)

step("DONE — Selenium works against live Chrome")
# NOTE: deliberately NOT calling driver.quit() — with debuggerAddress we attached to the
# operator's live Chrome; quit() could close it. Just let the script exit.
