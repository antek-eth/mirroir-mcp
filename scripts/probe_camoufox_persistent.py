#!/usr/bin/env python3
"""
Headful camoufox with a persistent profile. No cookie injection.
- First run: you solve the DataDome CONFIRM page manually.
- Subsequent runs: cookies are reused from the profile dir.
Exits when the page reports articles visible.
"""
import pathlib, sys, time
from camoufox.sync_api import Camoufox
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ensure_fingerprint import load_or_create

REPO = pathlib.Path(__file__).resolve().parent.parent
PROFILE = REPO / ".camoufox-profile"
PROFILE.mkdir(exist_ok=True)
URL = "https://allegro.pl/kategoria/laptopy-491?string=macbook&order=p"

with Camoufox(
    headless=False,
    locale="pl-PL",
    persistent_context=True,
    user_data_dir=str(PROFILE),
    fingerprint=load_or_create(),
    i_know_what_im_doing=True,
) as ctx:
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.set_extra_http_headers({"Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8"})
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)

    print("[probe] page loaded, waiting up to 2 min for you to solve CONFIRM if shown...")
    deadline = time.time() + 120
    while time.time() < deadline:
        info = page.evaluate("""() => ({
            articles: document.querySelectorAll('article').length,
            blocked: document.documentElement.outerHTML.includes('captcha-delivery')
                  || /Potwierd.+cz.owiekiem/i.test(document.body.innerText || ''),
            title: document.title,
            url: location.href,
        })""")
        if info["articles"] > 0 and not info["blocked"]:
            print(f"[probe] ✓ OK — {info['articles']} articles  title={info['title']!r}")
            sys.exit(0)
        print(f"[probe] waiting… articles={info['articles']} blocked={info['blocked']} url={info['url'][:80]}")
        time.sleep(5)
    print("[probe] ✗ timed out without clearing block", file=sys.stderr)
    sys.exit(1)
