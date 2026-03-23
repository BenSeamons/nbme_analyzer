# NBME Miss Analyzer

A Flask web app that scrapes NBME score report URLs, analyzes missed questions 
with Claude AI, and generates downloadable Anki decks with teaching points.

## How it works

1. User pastes their NBME starttest.com score report URL
2. Playwright (headless Chromium) navigates the report and clicks "Review Incorrect Items"
3. Scrapes each wrong question: stem, their answer, correct answer
4. Sends all misses to Claude API → gets topic, category, teaching point, Anki card
5. Renders a miss analysis page with expandable cards + category heatmap
6. User downloads an `.apkg` Anki deck with all missed questions as cards

---

## Deploy to Railway

### 1. Clone / upload this folder to GitHub

```bash
git init
git add .
git commit -m "initial commit"
gh repo create nbme-analyzer --public --push
```

### 2. Create Railway project

- Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
- Select your repo

### 3. Set environment variables in Railway dashboard

```
ANTHROPIC_API_KEY=sk-ant-...
SECRET_KEY=some-random-string-for-flask-sessions
```

### 4. Deploy

Railway auto-deploys on push. The Procfile handles installing Playwright's 
Chromium browser at startup.

---

## Local development

```bash
pip install -r requirements.txt
playwright install chromium

export ANTHROPIC_API_KEY=sk-ant-...
export SECRET_KEY=dev-secret

python app.py
```

Then open http://localhost:5000

---

## Architecture notes

- **Single worker** (gunicorn --workers 1) required because Playwright is not 
  thread-safe and scraping takes ~60s per report
- **Session storage** holds analyzed results between `/analyze` and `/download-anki`
  — works fine for single-user or low-traffic use. For high traffic, swap to Redis.
- **URL expiry**: NBME starttest.com URLs expire after ~2 hours. Users need a 
  fresh URL each session.
- **Timeout**: gunicorn timeout set to 120s to allow for full scrape + Claude API call

---

## File structure

```
nbme_analyzer/
├── app.py              # Flask routes, Claude API, Anki builder
├── scraper.py          # Playwright scraper for NBME reports
├── templates/
│   └── index.html      # Frontend UI
├── requirements.txt
├── Procfile            # Railway/Heroku start command
├── railway.json        # Railway config
└── README.md
```
