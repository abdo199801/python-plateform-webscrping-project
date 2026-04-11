# python-plateform-webscrping-project

## Google Maps Scraper Full-stack App

Full platform documentation is available in [PLATFORM_DOCUMENTATION.md](PLATFORM_DOCUMENTATION.md).

This project now includes:

- A FastAPI backend
- PostgreSQL persistence for scrape runs and businesses
- A browser dashboard
- A Playwright Google Maps scraper
- Optional Celery + Redis queue workers for scrape jobs
- Free local enrichment based on scraped business fields
- Smart duplicate detection using deterministic fuzzy matching

## Setup

1. Start PostgreSQL with Docker if you want a quick local database:

```powershell
docker compose up -d
```

2. Copy `.env.example` to `.env` and update `DATABASE_URL` if needed.
3. Install dependencies:

```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

4. Start the app:

```powershell
uvicorn app.main:app --reload
```

5. Optional: start Redis and a Celery worker for background scrape processing:

```powershell
docker compose up -d redis
celery -A app.tasks worker --loglevel=info --pool=solo
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
- After a scrape completes, the app runs free local enrichment and fuzzy deduplication for the saved businesses.
- If `save_files` is `true`, the scrape also exports XLSX and CSV files using the original script behavior.
- Celery is enabled only when `ENABLE_CELERY=true` and Redis is configured. Otherwise the API falls back to FastAPI in-process background tasks.

## Hosting Notes

- Do not rely on `sqlite:///./googlemaps.db` for hosted deployments if you need your existing data to appear online. A hosted container or serverless instance will usually start with a different or ephemeral filesystem. Use a persistent PostgreSQL database and set `DATABASE_URL` to that managed database.
- Set `FRONTEND_URL` to the public URL of the frontend and `ALLOWED_ORIGINS` to the exact frontend origins that should call the API.
- If the frontend is served from a different host than the API, set `API_BASE_URL` to the public backend URL so browser requests go to the right server.
- To guarantee admin login on a fresh production database, set `ADMIN_EMAIL` and `ADMIN_PASSWORD`. The app will create that admin account automatically on startup if it does not already exist.
- Vercel should not be treated as the backend host for this project in its current form. The browser UI can live on Vercel, but the FastAPI API should run on a Python host such as Render or Railway.
- The Playwright scraper needs the Chromium browser installed in production. The included Render build command installs it into a hermetic Playwright path, and the scraper can repair the browser runtime automatically if it is missing.
- For Celery in production, point `REDIS_URL` or `CELERY_BROKER_URL` to a Redis instance and run a separate worker process with `celery -A app.tasks worker --loglevel=info --pool=solo`.
- Leave `ENABLE_CELERY=false` on the web service until Redis and the worker are both confirmed healthy. The worker service can exist before that, but the web service should not dispatch jobs to Celery until the queue stack is verified.

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
REDIS_URL=redis://...render-redis...
ENABLE_CELERY=false
CELERY_BROKER_URL=
CELERY_RESULT_BACKEND=
PLAYWRIGHT_BROWSERS_PATH=0
FRONTEND_URL=https://your-frontend.vercel.app
ALLOWED_ORIGINS=https://your-frontend.vercel.app
API_BASE_URL=https://your-render-service.onrender.com
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_PASSWORD=replace-with-a-strong-password
USER_JWT_SECRET=replace-with-a-strong-secret
PAYPAL_CLIENT_ID=...
PAYPAL_CLIENT_SECRET=...
PAYPAL_ENVIRONMENT=sandbox
PAYPAL_CURRENCY=USD
```

If you use a separate Render worker service, give it the same values for `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `PLAYWRIGHT_BROWSERS_PATH`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and `USER_JWT_SECRET`.
Set `ENABLE_CELERY=true` on the worker, but keep `ENABLE_CELERY=false` on the web service until you have confirmed the worker is online and Redis is reachable.

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
