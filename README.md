# Eden Chamber Directory Scraper (no-browser)

Scrapes the Eden Area Chamber business directory and saves member details into a CSV — **no headless browser required** (pure `requests + BeautifulSoup`).

## Features
- Crawls these index pages automatically:  
  `/list/search?sa=true`, `/list/searchalpha/0-9`, `/list/searchalpha/a…z`
- Finds member detail pages (e.g., `/list/member/...`, `/list/details`, `memberdetails`, `mid=`, `bid=`).
- Extracts: name, categories, phone, email, website, address, city, state, ZIP, description.
- Writes a deduplicated CSV into `data/`.

## Quick start

### 1) Clone
```bash
git clone git@github.com:SujayO372/eden_chamber_scraper.git
cd eden_chamber_scraper
````

### 2) Python venv + deps

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

*(Optional)* If you have `scripts/setup_venv.sh`, you can just run:

```bash
./scripts/setup_venv.sh
```

### 3) Configure

Create `config.ini` (example):

```ini
[app]
urls = https://business.edenareachamber.com/list
user_agent = Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
```

### 4) Run

```bash
source .venv/bin/activate
python scrape_eden_no_browser.py
```
