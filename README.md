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

## Hosting Notes

- Do not rely on `sqlite:///./googlemaps.db` for hosted deployments if you need your existing data to appear online. A hosted container or serverless instance will usually start with a different or ephemeral filesystem. Use a persistent PostgreSQL database and set `DATABASE_URL` to that managed database.
- Set `FRONTEND_URL` to the public URL of the frontend and `ALLOWED_ORIGINS` to the exact frontend origins that should call the API.
- If the frontend is served from a different host than the API, set `API_BASE_URL` to the public backend URL so browser requests go to the right server.
- To guarantee admin login on a fresh production database, set `ADMIN_EMAIL` and `ADMIN_PASSWORD`. The app will create that admin account automatically on startup if it does not already exist.

## Neon Setup

- Create a Neon project and copy its connection string.
- Set `DATABASE_URL` in production to the Neon string, including `?sslmode=require`.
- Set `NEON_DATABASE_URL` locally if you want to run the migration script without changing your local app database.
- Migrate existing local data with:

```powershell
python migrate_to_neon.py --truncate-target
```

- If you want to keep any existing Neon rows and only allow copying into a non-empty target, run:

```powershell
python migrate_to_neon.py --allow-nonempty-target
```

- After migration, redeploy the hosted app with `DATABASE_URL` pointing to Neon.

## PayPal Setup

- Add `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, and `PAYPAL_ENVIRONMENT` to your environment.
- The frontend now loads the PayPal JS SDK dynamically and renders a PayPal button directly inside each paid plan card.
- The backend creates PayPal orders with `POST /api/paypal/orders` and captures them with `POST /api/paypal/orders/{order_id}/capture`.
- A successful PayPal capture activates a 30-day subscription in the same database used by the rest of the app.
