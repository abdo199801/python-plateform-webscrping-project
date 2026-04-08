# python-plateform-webscrping-project

## Google Maps Scraper Full-stack App

This project now includes:

- A FastAPI backend
- PostgreSQL persistence for scrape runs and businesses
- A browser dashboard
- The original Selenium Google Maps scraper

## Setup

1. Start PostgreSQL with Docker if you want a quick local database:

```powershell
docker compose up -d
```

2. Copy `.env.example` to `.env` and update `DATABASE_URL` if needed.
3. Install dependencies:

```powershell
pip install -r requirements.txt
```

4. Start the app:

```powershell
uvicorn app.main:app --reload
```

5. Open `http://127.0.0.1:8000`

## API

- `GET /api/health`
- `POST /api/scrapes`
- `GET /api/scrapes`
- `GET /api/businesses`
- `GET /api/businesses/{business_id}`

## Notes

- Tables are created automatically on startup.
- `POST /api/scrapes` runs the Selenium scraper and then stores the results in PostgreSQL.
- If `save_files` is `true`, the scrape also exports XLSX and CSV files using the original script behavior.
