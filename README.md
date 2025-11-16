# 📘 README.md — *Eden Chamber Directory Scraper (No-Browser)*

Scrapes the Eden Area Chamber business directory and saves all member details into a CSV — **no headless browser required** (pure `requests + BeautifulSoup`).

---

## 🚀 Features

* Crawls these index pages automatically:

  * `/list/search?sa=true`
  * `/list/searchalpha/0-9`
  * `/list/searchalpha/a…z`
* Detects and follows all **member detail pages**:

  * `/list/member/...`, `/list/details`, `memberdetails`, `mid=`, `bid=`
* Extracts key information:

  * **Name, Categories, Phone, Email, Website, Address, City, State, Postal Code, Description**
* Outputs a **deduplicated CSV** per run.

---

## 🧩 Project Structure

```
eden_chamber_scraper/
├── scrape_eden_no_browser.py      # Main scraper script
├── config.ini                     # Configuration file (URLs, User-Agent)
├── requirements.txt               # Dependencies
├── data/                          # Output CSV files appear here
├── .gitignore                     # Git ignore rules
├── README.md                      # Documentation
└── scripts/
    └── setup_venv.sh              # Optional setup script
```

---

## ⚙️ Setup Instructions

### 1️⃣ Clone the repository

```bash
git clone https://github.com/SujayO372/eden_chamber_scraper.git
cd eden_chamber_scraper
```

### 2️⃣ Create a Python virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

*(Optional)*

```bash
./scripts/setup_venv.sh
```

---

## 🧾 Configuration

Create or edit `config.ini`:

```ini
[app]
urls = https://business.edenareachamber.com/list
user_agent = Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
```

---

## ▶️ Running the Scraper

Activate your venv and run:

```bash
source .venv/bin/activate
python scrape_eden_no_browser.py
```

You’ll see output like:

```
[*] Discovering member pages…
  https://business.edenareachamber.com/list/searchalpha/a -> 18 links
  ...
[*] Total unique member pages: 210
  parsed 20/210 profiles
...
[✓] Saved 210 rows -> data/eden-chamber-static-20251111-213045.csv
```

---

## 📂 Output Location

All CSV files are automatically saved in the `data/` folder.

Each run produces a new timestamped file, for example:

```
data/eden-chamber-static-20251111-213045.csv
```

If the folder doesn’t exist, it’s created automatically.

---

## 💡 CLI Overrides

You can skip `config.ini` entirely:

```bash
python scrape_eden_no_browser.py \
  --url https://business.edenareachamber.com/list \
  --user-agent "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ..."
```

---

## 🧠 Tips & Notes

* To scrape **multiple chambers**, add URLs separated by commas in `config.ini` or run the script multiple times.
* If a chamber site changes its layout, share one sample “A–Z” listing page HTML and one “member details” HTML — selectors can be tuned easily.
* For reproducibility, keep the `requirements.txt` pinned to the provided versions.

---

## 📊 Output Columns

| Column                         | Description                                 |
| :----------------------------- | :------------------------------------------ |
| `source_list_url`              | Index page where this member was discovered |
| `member_url`                   | Direct link to the business/member page     |
| `name`                         | Member or business name                     |
| `categories`                   | Category tags                               |
| `phone`                        | Phone number (if available)                 |
| `email`                        | Email address                               |
| `website`                      | Business website                            |
| `address`                      | Full mailing or street address              |
| `city`, `state`, `postal_code` | Parsed address fields                       |
| `description`                  | Company or organization description         |

---

