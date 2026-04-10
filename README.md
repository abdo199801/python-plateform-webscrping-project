# python-plateform-webscrping-project

## Google Maps Scraper Full-stack App

Full platform documentation is available in [PLATFORM_DOCUMENTATION.md](PLATFORM_DOCUMENTATION.md).

This project now includes:

- A FastAPI backend
- PostgreSQL persistence for scrape runs and businesses
- A browser dashboard
- A Playwright Google Maps scraper

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
- `POST /api/scrapes` runs the Playwright scraper and then stores the results in PostgreSQL.
- If `save_files` is `true`, the scrape also exports XLSX and CSV files using the original script behavior.

## Hosting Notes

- Do not rely on `sqlite:///./googlemaps.db` for hosted deployments if you need your existing data to appear online. A hosted container or serverless instance will usually start with a different or ephemeral filesystem. Use a persistent PostgreSQL database and set `DATABASE_URL` to that managed database.
- Set `FRONTEND_URL` to the public URL of the frontend and `ALLOWED_ORIGINS` to the exact frontend origins that should call the API.
- If the frontend is served from a different host than the API, set `API_BASE_URL` to the public backend URL so browser requests go to the right server.
- To guarantee admin login on a fresh production database, set `ADMIN_EMAIL` and `ADMIN_PASSWORD`. The app will create that admin account automatically on startup if it does not already exist.
- Vercel should not be treated as the backend host for this project in its current form. The browser UI can live on Vercel, but the FastAPI API should run on a Python host such as Render or Railway.
- The Playwright scraper needs the Chromium browser installed in production. The included Render build command installs it automatically.

## Recommended Deploy Split

Use this layout:

- Frontend: Vercel
- Backend API: Render
- Database: Neon

Example values after the backend is deployed on Render:

```dotenv
FRONTEND_URL=https://your-frontend.vercel.app
ALLOWED_ORIGINS=https://your-frontend.vercel.app
API_BASE_URL=https://your-render-service.onrender.com
DATABASE_URL=postgresql://...neon...&sslmode=require
```

For the Vercel frontend, set the public backend URL that the browser must call:

```dotenv
API_BASE_URL=https://your-render-service.onrender.com
```

For the Render backend, set at least:

```dotenv
DATABASE_URL=postgresql://...neon...&sslmode=require
FRONTEND_URL=https://your-frontend.vercel.app
ALLOWED_ORIGINS=https://your-frontend.vercel.app
API_BASE_URL=https://your-render-service.onrender.com
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_PASSWORD=replace-with-a-strong-password
PAYPAL_CLIENT_ID=...
PAYPAL_CLIENT_SECRET=...
PAYPAL_ENVIRONMENT=sandbox
PAYPAL_CURRENCY=USD
```

The admin login connection error on Vercel happens when `/api/admin/login` is not backed by a running FastAPI API, or when the frontend is still pointing to localhost instead of the deployed backend.

## Render Deployment

- A starter Render service definition is included in [render.yaml](render.yaml).
- Create a new Render Web Service from this repository.
- Add the environment variables listed above.
- After the first deploy, copy the Render service URL and use it as `API_BASE_URL` for the Vercel frontend.

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
