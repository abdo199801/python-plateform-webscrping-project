# Platform Documentation

## Overview

MapsScraper Pro is a Google Maps lead-generation platform built as a FastAPI application with a static browser frontend.

The platform lets users:

- create or update a company profile
- run Google Maps scraping jobs
- store scraped businesses in a database
- manage lead pipeline status, notes, and tags
- save filtered lead views as reusable searches
- monitor trial, credits, and subscription access
- pay with Stripe or PayPal
- access an admin area for management tasks

The current product supports two user modes:

- legacy email-based flow, where a user can work by profile email without mandatory login
- optional authenticated customer flow, where a user can register, log in, and use a bearer token for private account access

This compatibility mode was kept intentionally so the original workflow continues to work while the hosted version can later move toward stricter authentication.

## Stack

- Backend: FastAPI
- Database ORM: SQLAlchemy
- Database: PostgreSQL in production, SQLite fallback locally
- Frontend: static HTML, CSS, and JavaScript served by FastAPI
- Scraping engine: Playwright
- Payments: Stripe and PayPal
- Authentication: JWT for admins and optional platform users

## Project Structure

- `app/main.py`: main FastAPI app, route registration, startup checks, runtime config
- `app/services.py`: scrape execution and persistence helpers
- `app/payment_service.py`: trials, subscriptions, credits, dashboard, and payment logic
- `app/auth_service.py`: admin auth and optional customer auth helpers
- `app/admin_routes.py`: admin endpoints and admin UI access flow
- `app/lead_service.py`: lead pipeline, tags, and saved search helpers
- `app/lead_models.py`: lead records and saved searches tables
- `app/static/index.html`: browser UI
- `app/static/app.js`: frontend behavior and API calls
- `app/static/styles.css`: frontend styling
- `render.yaml`: starter Render deployment file
- `requirements.txt`: Python dependencies

## Core Product Areas

### 1. Company Profile

Users begin by filling in business information:

- full name
- company name
- email
- phone
- country
- preferred payment method

In optional auth mode, the same profile form can also create a customer account with password and confirmation.

Profile data is used to:

- associate scrapes to a user email
- calculate trial access and dashboard state
- attach lead pipeline activity to a single account
- connect billing and subscription state

### 2. Scraper

The scrape form supports:

- keyword
- location
- radius
- max results
- headless mode
- file export toggle
- email for account association

When a scrape runs, the app:

1. executes the Playwright Google Maps scraping flow
2. persists the run in the database
3. stores businesses found in that run
4. optionally exports CSV and XLSX files
5. updates the user usage statistics

### 3. Dashboard

The user dashboard is the main account summary view. It exposes:

- trial status
- subscription state
- total scrape count
- recent payments
- subscription history
- upgrade actions
- subscription cancellation

This is driven mainly by the user access and dashboard endpoints in `app/main.py` and the account logic in `app/payment_service.py`.

### 4. Lead Desk

Lead Desk is the CRM-style layer added on top of saved businesses.

Each lead record can store:

- status
- tags
- notes
- archived flag

Supported lead statuses:

- `new`
- `contacted`
- `qualified`
- `proposal`
- `won`
- `lost`

Lead Desk also supports:

- filtering businesses by search, city, country, category, status, tag, and saved-only mode
- reusable saved searches
- lead summary cards for tracked, active, qualified, and won leads

### 5. Pricing and Payments

The platform supports both credit purchases and subscriptions.

Current payment capabilities:

- Stripe checkout session creation
- PayPal order creation and capture
- trial access before paid plan activation
- credit tracking
- subscription activation and cancellation

Important implementation details:

- the app normalizes datetime handling to avoid naive versus aware datetime comparison failures
- database pooling includes liveness checking and recycle behavior for hosted PostgreSQL connections

### 6. Admin Area

The admin side is separate from the customer-facing UI.

It is intended for:

- admin login
- user management
- subscription and payment management
- analytics and operational visibility

Admin bootstrap behavior:

- if `ADMIN_EMAIL` and `ADMIN_PASSWORD` are set, the first admin account can be created automatically on startup

## Frontend Sections

The main browser interface currently includes:

- Hero section
- Account Access
- Company Profile
- User Dashboard
- Signal Board
- Start a Scrape
- Lead Desk
- Pricing
- Saved Runs
- Saved Businesses

The frontend is a static app served by FastAPI and relies on API calls from `app/static/app.js`.

## Authentication Model

There are two active auth layers.

### Admin Authentication

Admin authentication is separate and intended for back-office use.

- login endpoint is handled in admin routes
- admin accounts use hashed passwords
- admin sessions use JWT

### Customer Authentication

Customer authentication is optional right now.

- registration endpoint: `POST /api/auth/register`
- login endpoint: `POST /api/auth/login`
- current session endpoint: `GET /api/auth/me`

The frontend stores:

- `userEmail` for the legacy flow
- `authToken` for authenticated customer sessions

Many user routes accept the legacy email-only flow when no authenticated user is present. If a user is authenticated, the backend enforces ownership so one logged-in user cannot access another user’s data.

## API Overview

### General

- `GET /api/health`: health check
- `GET /config.js`: runtime frontend configuration

### Scraping

- `POST /api/scrapes`: create a scrape job
- `GET /api/scrapes`: list stored scrape runs
- `GET /api/scrapes/{run_id}/exports/{file_format}`: download a run export

### Businesses

- `GET /api/businesses`: list saved businesses with optional filters
- `GET /api/businesses/{business_id}`: fetch a single business

Supported business filters include:

- `page`
- `page_size`
- `search`
- `city`
- `country`
- `category`
- `email`
- `lead_status`
- `tag`
- `saved_only`

### Lead Desk

- `POST /api/leads`: create or update a lead record
- `GET /api/leads/summary/{email}`: get lead summary metrics
- `GET /api/saved-searches/{email}`: list saved searches
- `POST /api/saved-searches`: create a saved search
- `DELETE /api/saved-searches/{search_id}`: delete a saved search

### User Profile and Access

- `POST /api/users/onboard`: create or update user record
- `PUT /api/users/profile`: update user profile
- `GET /api/users/access/{email}`: access and trial status
- `GET /api/users/dashboard/{email}`: user dashboard payload
- `POST /api/users/subscription/cancel`: cancel subscription

### Customer Auth

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`

### Payments and Credits

- `GET /api/pricing`
- `GET /api/payment/config`
- `POST /api/payment/create-checkout-session`
- `POST /api/subscription/create-checkout-session`
- `POST /api/paypal/orders`
- `POST /api/paypal/orders/{order_id}/capture`
- `POST /api/stripe/webhook`
- `GET /api/user/credits/{email}`
- `POST /api/user/credits/use`

### Insights

- `GET /api/insights/overview`

### Admin

Admin routes are mounted from `app/admin_routes.py` and serve the admin experience separately from the main user UI.

## Data Model Summary

Key domain entities include:

- `PlatformUser`: customer profile, trial, and account state
- `ScrapeRun`: metadata for a scraping session
- `Business`: each stored scraped business
- `LeadRecord`: CRM state for a user-business pair
- `SavedSearch`: reusable lead filters
- `Payment`: payment records
- `Subscription`: active or historical subscription records
- `ScrapeCredit`: credit balances linked to payments
- `AdminUser`: admin account model

## Local Development

### Requirements

- Python virtual environment
- installed dependencies from `requirements.txt`
- PostgreSQL through Docker or local SQLite fallback

### Quick Start

```powershell
docker compose up -d
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

### Local Notes

- tables are created automatically at startup
- startup also attempts lightweight schema repair for platform user auth columns
- `.vscode/tasks.json` contains a local task to run the FastAPI app

## Deployment

### Recommended Split

- Frontend: Vercel
- Backend: Render
- Database: Neon

### Render Configuration

Root directory:

```text
.
```

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Important:

- use Python `3.11.11` for Render
- if Render defaults to Python `3.14`, `pydantic-core` may fail to build because it falls back to a Rust-based build path
- `.python-version` and `PYTHON_VERSION` are used to pin the supported version

### Required Environment Variables

Minimum backend environment variables:

```dotenv
DATABASE_URL=postgresql://...neon...&sslmode=require
FRONTEND_URL=https://your-frontend.vercel.app
ALLOWED_ORIGINS=https://your-frontend.vercel.app
API_BASE_URL=https://your-render-service.onrender.com
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_PASSWORD=replace-with-a-strong-password
USER_JWT_SECRET=replace-with-a-long-random-secret
PAYPAL_CLIENT_ID=...
PAYPAL_CLIENT_SECRET=...
PAYPAL_ENVIRONMENT=sandbox
PAYPAL_CURRENCY=USD
STRIPE_PUBLISHABLE_KEY=...
STRIPE_SECRET_KEY=...
STRIPE_WEBHOOK_SECRET=...
```

### Database Notes

- hosted deployments should use PostgreSQL, not local SQLite
- Neon connections should include SSL
- the SQLAlchemy engine uses `pool_pre_ping=True` and `pool_recycle=300` for better hosted connection reliability

## Operational Notes

### Timezone Safety

Subscription and trial comparisons normalize datetimes before checking expiry. This avoids crashes caused by comparing timezone-aware and timezone-naive datetime values.

### Connection Stability

Hosted PostgreSQL connections can drop between requests. The database configuration now checks connection liveness and recycles pooled connections to reduce intermittent SSL connection errors.

### Backward Compatibility

The platform currently preserves the original email-driven user flow. This matters because it reduces user friction while hosting is being introduced.

The practical result is:

- a user can still save profile information and scrape without mandatory login in the legacy flow
- customer auth endpoints remain available for later stricter rollout

## Suggested Next Improvements

- separate customer auth rollout from the legacy flow with a clear feature flag
- add automated database migrations instead of relying on startup schema repair
- add background job processing for scraping and exports
- preinstall the Playwright Chromium runtime for more predictable hosted scraping
- add automated tests for access, dashboard, lead desk, and payment flows

## Ownership and Maintenance

This codebase is structured as a single deployable FastAPI application. The simplest maintenance model is:

- keep backend API and static frontend in the same repo
- host API on Render
- move only the public frontend to Vercel if needed
- keep Neon as the single source of persisted production data

If stricter account isolation becomes mandatory later, the current optional auth layer is the starting point for that transition.