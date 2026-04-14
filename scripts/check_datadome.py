#!/usr/bin/env python3
"""
Probe Allegro with the current .datadome-cookie to verify the session is alive.
Exit 0 = cookie good (listings visible). Exit 1 = blocked or cookie missing.
"""
import json, pathlib, subprocess, sys

REPO = pathlib.Path(__file__).resolve().parent.parent
COOKIE_FILE = REPO / ".datadome-cookie"
PROBE_URL = "https://allegro.pl/kategoria/laptopy-491?string=macbook&order=p"


def main() -> int:
    if not COOKIE_FILE.exists():
        print("[datadome] .datadome-cookie missing", file=sys.stderr)
        return 1
    cookie = COOKIE_FILE.read_text().strip()
    if not cookie:
        print("[datadome] .datadome-cookie empty", file=sys.stderr)
        return 1

    js = f"""
const page = await browser.getPage("datadome-probe");
await page.context().addCookies([{{
  name:'datadome', value:{json.dumps(cookie)},
  domain:'.allegro.pl', path:'/', httpOnly:true, secure:true, sameSite:'Lax',
}}]);
await page.setExtraHTTPHeaders({{'Accept-Language':'pl-PL,pl;q=0.9,en;q=0.8'}});
await page.goto({json.dumps(PROBE_URL)}, {{waitUntil:'domcontentloaded', timeout:30000}});
await page.waitForSelector('article', {{timeout:10000}}).catch(()=>{{}});
const r = await page.evaluate(() => ({{
  articles: document.querySelectorAll('article').length,
  blocked: document.documentElement.outerHTML.includes('captcha-delivery'),
}}));
console.log(JSON.stringify(r));
"""
    try:
        r = subprocess.run(
            ["dev-browser", "--connect", "http://127.0.0.1:9222"],
            input=js, capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        print("[datadome] probe timed out", file=sys.stderr)
        return 1

    result = None
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                result = json.loads(line)
                break
            except json.JSONDecodeError:
                pass

    if not result:
        print(f"[datadome] no probe output. stderr={r.stderr[:200]}", file=sys.stderr)
        return 1

    if result.get("blocked"):
        print("[datadome] BLOCKED — cookie expired or IP reputation lost", file=sys.stderr)
        return 1
    if result.get("articles", 0) == 0:
        print("[datadome] 0 articles — page not rendering (cookie may be stale)", file=sys.stderr)
        return 1

    print(f"[datadome] OK — {result['articles']} articles visible")
    return 0


if __name__ == "__main__":
    sys.exit(main())
