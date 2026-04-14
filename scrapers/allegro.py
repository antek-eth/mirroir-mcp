#!/usr/bin/env python3
# Scrape Allegro.pl listings into JSON for pipeline.py
# Usage: ./scrapers/allegro.py "<search-url>" [--used] [--pages N]
# Requires Chrome running (non-headless) with --remote-debugging-port=9222
# Requires .datadome-cookie file at repo root: paste the `datadome` cookie
# value from a real Brave/Chrome session on allegro.pl. Refresh when it expires.

import json, os, pathlib, re, subprocess, sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
COOKIE_FILE = REPO_ROOT / ".datadome-cookie"


def load_datadome_cookie():
    if not COOKIE_FILE.exists():
        print(f"[allegro] WARNING: {COOKIE_FILE} not found — expect DataDome blocks", file=sys.stderr)
        return ""
    v = COOKIE_FILE.read_text().strip()
    if not v:
        print(f"[allegro] WARNING: {COOKIE_FILE} is empty", file=sys.stderr)
    return v


def scrape_page(url, datadome):
    js = f"""
const page=await browser.getPage("allegro-scrape");

// Inject a valid datadome session cookie (obtained from a real Brave/Chrome browse).
// Without this, Allegro's DataDome shield hard-blocks fresh scraper profiles.
const DD={json.dumps(datadome)};
if(DD) await page.context().addCookies([{{
  name:'datadome',value:DD,domain:'.allegro.pl',path:'/',
  httpOnly:true,secure:true,sameSite:'Lax'
}}]);

// Polish locale header — required for Accept-Language consistency with allegro.pl
await page.setExtraHTTPHeaders({{
  'Accept-Language':'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
  'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
}});

await page.goto({json.dumps(url)},{{waitUntil:'domcontentloaded',timeout:40000}});

// Wait for actual content, not a fixed time
await page.waitForSelector('article',{{timeout:15000}}).catch(()=>{{}});

// Random read delay (800–2300 ms) — fixed delays are a strong bot signal
await new Promise(r=>setTimeout(r,Math.floor(Math.random()*1500)+800));

// Gradual scroll simulating a human reading the listing grid
await page.evaluate(()=>{{
  return new Promise((resolve)=>{{
    const maxScroll=document.body.scrollHeight*0.75;
    let pos=0;
    const step=()=>{{
      pos+=Math.floor(Math.random()*250)+100;
      window.scrollTo(0,pos);
      if(pos<maxScroll) setTimeout(step,Math.floor(Math.random()*200)+80);
      else resolve();
    }};
    step();
  }});
}});

// Short pause after scroll
await new Promise(r=>setTimeout(r,Math.floor(Math.random()*600)+300));

const o=await page.evaluate(()=>{{
  const out=[];
  for(const a of document.querySelectorAll('article')){{
    let t='',u='';
    for(const l of a.querySelectorAll('a[href*="/oferta/"]')){{
      const x=l.textContent.trim();
      if(x.length>10){{t=x;u=l.href;break;}}
    }}
    if(!t||!u) continue;
    if(u.includes('redirect=')) try{{u=decodeURIComponent(new URL(u).searchParams.get('redirect'));}}catch{{}}
    u=u.split('?')[0];
    let p='';
    for(const s of a.querySelectorAll('span')){{
      const x=s.textContent.trim();
      if(x.includes('zł')&&/\\d/.test(x)&&x.length<30&&!x.includes('/')){{p=x;break;}}
    }}
    out.push([t,u,p]);
  }}
  return out;
}});
console.log(JSON.stringify(o));
"""
    r = subprocess.run(
        ['dev-browser', '--connect', 'http://127.0.0.1:9222'],
        input=js, capture_output=True, text=True, timeout=90
    )
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith('['):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
    return []

def clean_price(p):
    p = re.sub(r'do negocjacji', '', p, flags=re.I).strip()
    p = re.sub(r'\s+', ' ', p).strip()
    return p

def extract_cpu(url):
    m = re.search(r'm(\d)[-_]?(pro|max|ultra)', url.lower())
    if m:
        return f"M{m.group(1)} {m.group(2).upper()}"
    m = re.search(r'm(\d)(?![\w])', url.lower())
    if m:
        return f"M{m.group(1)}"
    return None

def main():
    args = sys.argv[1:]
    if not args or args[0].startswith('-'):
        print("Usage: allegro.py <search-url> [--used] [--pages N]", file=sys.stderr)
        sys.exit(1)

    raw_url = args[0]
    is_used = '--used' in args
    max_pages = 5
    if '--pages' in args:
        idx = args.index('--pages')
        max_pages = int(args[idx + 1])

    base = re.sub(r'[?&]p=\d+', '', raw_url)
    sep = '&' if '?' in base else '?'

    datadome = load_datadome_cookie()

    seen_urls = set()
    results = []

    for page_num in range(1, max_pages + 1):
        url = base if page_num == 1 else f"{base}{sep}p={page_num}"
        print(f"[allegro] page {page_num}", file=sys.stderr)
        items = scrape_page(url, datadome)
        new = 0
        for title, u, price in items:
            if u in seen_urls:
                continue
            seen_urls.add(u)
            new += 1
            entry = {
                'title': title,
                'url': u,
                'price': clean_price(price),
                'source': 'allegro.pl',
                'used': is_used,
            }
            cpu = extract_cpu(u)
            if cpu:
                entry['cpu'] = cpu
            results.append(entry)
        print(f"[allegro] {len(items)} found, {new} new, total {len(results)}", file=sys.stderr)
        if new == 0:
            break

    print(json.dumps(results, ensure_ascii=False, separators=(',', ':')))

if __name__ == '__main__':
    main()
