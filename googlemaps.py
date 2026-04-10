import logging
import os
import random
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import unicodedata
from urllib import error as urlerror
from urllib import request as urlrequest
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, Locator, sync_playwright
from scraper_config.world_locations import ALL_COUNTRIES, COUNTRY_VARIATIONS, MAJOR_CITIES


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

PAGE_LOAD_TIMEOUT_SECONDS = 45
RESULTS_PANEL_TIMEOUT_SECONDS = 25
DETAIL_PANEL_TIMEOUT_SECONDS = 12
_PLAYWRIGHT_INSTALL_LOCK = threading.Lock()
DEFAULT_PLAYWRIGHT_BROWSERS_PATH = "0"
WEBSITE_FETCH_TIMEOUT_SECONDS = 8
WEBSITE_FETCH_MAX_PAGES = 3
WEBSITE_CONTACT_PATHS = ["/contact", "/contact-us", "/about", "/about-us"]
RESULT_PANEL_SELECTORS = [
    "div[role='feed']",
    "div[aria-label*='Results']",
    "div[aria-label*='results']",
    "div[aria-label*='Resultats']",
    "div[aria-label*='Resultat']",
    "div[aria-label*='Resultados']",
    "div[aria-label*='Resultaten']",
    "div.m6QErb[aria-label*='Results']",
    "div.m6QErb.DxyBCb",
    "div.m6QErb.kA9KIf.dS8AEf",
    "div[role='main'] div.m6QErb.DxyBCb",
    "div[role='main'] div[aria-label][tabindex='0']",
    "div.m6QErb.XiKgde",
]
BUSINESS_CARD_SELECTORS = [
    "div[role='article']",
    "div.Nv2PK",
    "a.hfpxzc",
    "div[jsaction*='pane.result']",
    "div[aria-label][role='article']",
    "div.lI9IFe",
    "div.Nv2PK.THOPZb.CpccDe",
    "div.Nv2PK.tH5CWc.THOPZb",
    "div[data-result-index]",
    "div[jslog*='mutableResult']",
    "a[href*='/maps/place/']",
]
DETAIL_READY_SELECTORS = [
    "button[data-item-id*='address']",
    "button[data-item-id*='locatedin']",
    "button[aria-label*='Address']",
    "button[aria-label*='adresse']",
    "button[aria-label*='direccion']",
    "button[aria-label*='indirizzo']",
    "button[aria-label*='endereco']",
    "div[role='main'] h1",
    "h1.DUwDvf",
    "h1.fontHeadlineLarge",
    "div[role='main'] [data-attrid='title']",
]
DETAIL_HEADING_SELECTORS = [
    "h1",
    "div[role='main'] h1",
    "h1.DUwDvf",
    "h1.fontHeadlineLarge",
    "div[role='main'] [data-attrid='title']",
    "div[role='main'] .fontHeadlineLarge",
]
DETAIL_RATING_ATTRIBUTE_SELECTORS = [
    ("span[role='img'][aria-label*='star']", "aria-label"),
    ("span[role='img'][aria-label*='Star']", "aria-label"),
    ("span[aria-label*='stars']", "aria-label"),
    ("span[aria-label*='rating']", "aria-label"),
    ("div[role='img'][aria-label*='star']", "aria-label"),
    ("div[aria-label*='stars']", "aria-label"),
]
DETAIL_RATING_TEXT_SELECTORS = [
    "span.MW4etd",
    "div.F7nice span[aria-hidden='true']",
    "div.F7nice div[aria-hidden='true']",
    "div[role='main'] span.ceNzKf",
    "div[role='main'] span.fontBodyMedium[aria-hidden='true']",
]
DETAIL_REVIEW_SELECTORS = [
    "button[jsaction*='pane.rating.category']",
    "button[jsaction*='pane.reviewChart.moreReviews']",
    "div.F7nice",
    "span[aria-label*='reviews']",
    "span[aria-label*='Reviews']",
    "span[aria-label*='avis']",
    "span[aria-label*='reseñas']",
    "span[aria-label*='Bewertungen']",
]
DETAIL_CATEGORY_SELECTORS = [
    "button[jsaction*='pane.rating.category']",
    "div.DkEaL",
    "button[jsaction*='pane.rating.moreReviews']",
    "div[role='main'] button[jslog*='category']",
    "div[role='main'] span.DkEaL",
    "div[role='main'] .fontBodyMedium span",
]
DETAIL_HOURS_SELECTORS = [
    "div[aria-label*='Hours']",
    "div[aria-label*='hours']",
    "div[aria-label*='Open']",
    "div[aria-label*='open']",
    "div[aria-label*='Horaire']",
    "div[aria-label*='Horario']",
    "table.eK4R0e tbody",
    "div.OMl5r",
    "div.t39EBf",
]
DETAIL_DESCRIPTION_SELECTORS = [
    "div.PYvSYb",
    "div.fontBodyMedium span",
    "div[role='main'] span[jslog]",
    "div[role='main'] span",
    "div[role='main'] div.PYvSYb",
    "div[role='main'] div.WeS02d",
]
DETAIL_PHONE_TEXT_SELECTORS = [
    "button[data-item-id*='phone']",
    "button[data-item-id*='phone:tel']",
    "button[aria-label*='Phone']",
    "button[aria-label*='phone']",
    "button[aria-label*='Telephone']",
    "button[aria-label*='telephone']",
    "button[aria-label*='Tel']",
    "a[href^='tel:']",
    "div[role='main'] a[href^='tel:']",
]
DETAIL_WEBSITE_ATTRIBUTE_SELECTORS = [
    ("a[data-item-id*='authority']", "href"),
    ("a[data-item-id*='menu']", "href"),
    ("a[aria-label*='Website']", "href"),
    ("a[aria-label*='website']", "href"),
    ("a[aria-label*='site web']", "href"),
    ("a[aria-label*='sitio web']", "href"),
    ("a[aria-label*='webseite']", "href"),
    ("div[role='main'] a[href^='http']", "href"),
    ("a[href^='http']", "href"),
]
DETAIL_ADDRESS_TEXT_SELECTORS = [
    "button[data-item-id*='address']",
    "button[data-item-id*='locatedin']",
    "div[role='main'] button[aria-label*='Address']",
    "button[aria-label*='Address']",
    "button[aria-label*='address']",
    "button[aria-label*='adresse']",
    "button[aria-label*='direccion']",
    "button[aria-label*='indirizzo']",
    "button[aria-label*='endereco']",
]
MAX_SEARCH_VARIANTS = 4
MAX_SCROLL_STAGNANT_ROUNDS = 12
COUNTRY_FANOUT_CITY_LIMIT = 8
COUNTRY_BATCH_CITY_LIMIT = 16
COUNTRY_BATCH_SIZE = 4


@dataclass
class BusinessData:
    name: str = ""
    address: str = ""
    phone: str = ""
    website: str = ""
    rating: float = 0.0
    reviews_count: int = 0
    category: str = ""
    business_hours: str = ""
    description: str = ""
    latitude: str = ""
    longitude: str = ""
    place_id: str = ""
    source_url: str = ""
    scraped_date: str = ""
    country: str = ""
    city: str = ""
    street: str = ""
    postal_code: str = ""
    state_province: str = ""
    email: str = ""
    social_media: str = ""


class UniversalGoogleMapsScraper:
    def __init__(self, headless: bool = False, max_results: int = 1000, scroll_pause: float = 2, delay_between_requests: float = 1.5):
        self.headless = self._resolve_headless_mode(headless)
        self.max_results = max_results
        self.scroll_pause = scroll_pause
        self.delay_between_requests = delay_between_requests
        self.playwright = None
        self.browser = None
        self.context = None
        self.page: Optional[Page] = None
        self.session_user_agent = ""

        self.phone_pattern = re.compile(r"(\+\d{1,3}[\s\-]?)?\(?\d{1,4}\)?[\s\-]?\d{1,4}[\s\-]?\d{1,9}")
        self.email_pattern = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
        self.postal_pattern = re.compile(r"\b\d{5}(?:[-\s]\d{4})?\b|\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b")
        self.country_aliases = self.load_country_data()
        self.city_to_country = self.load_city_data()

        self.config_dir = "scraper_config"
        self.cache_dir = "cache"
        self.create_directories()

    def _normalize_lookup_text(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value or "")
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        lowered = ascii_text.lower().strip()
        return re.sub(r"\s+", " ", lowered)

    def _canonical_country_name(self, value: str) -> str:
        lookup = self._normalize_lookup_text(value)
        if not lookup:
            return ""

        for country, codes in self.country_aliases.items():
            aliases = [country, *codes]
            normalized_aliases = {self._normalize_lookup_text(alias) for alias in aliases}
            if lookup in normalized_aliases:
                return country

        for country, codes in self.country_aliases.items():
            aliases = [country, *codes]
            normalized_aliases = {self._normalize_lookup_text(alias) for alias in aliases}
            if any(alias and alias in lookup for alias in normalized_aliases):
                return country

        return value.strip()

    def _location_parts_from_input(self, location_input: str) -> List[str]:
        return [part.strip() for part in re.split(r"[,;/|-]", location_input or "") if part.strip()]

    def _infer_country_from_city(self, city: str) -> str:
        normalized_city = self._normalize_lookup_text(city)
        return self.city_to_country.get(normalized_city, "")

    def _matches_country_alias(self, haystack: str, alias: str) -> bool:
        normalized_haystack = self._normalize_lookup_text(haystack)
        normalized_alias = self._normalize_lookup_text(alias)
        if not normalized_haystack or not normalized_alias:
            return False
        if len(normalized_alias) <= 3 and normalized_alias.isalpha():
            tokens = set(re.findall(r"\b[a-z]{2,}\b", normalized_haystack))
            return normalized_alias in tokens
        return normalized_alias in normalized_haystack

    def _build_location_variants(self, location_info: Dict[str, str], include_country_fanout: bool = True) -> List[str]:
        variants: List[str] = []
        original = (location_info.get("original_input") or "").strip()
        city = (location_info.get("city") or "").strip()
        state = (location_info.get("state_province") or "").strip()
        country = (location_info.get("country") or "").strip()
        country_city_variants = []

        if include_country_fanout and country and not city:
            for major_city in MAJOR_CITIES.get(country, [])[:COUNTRY_FANOUT_CITY_LIMIT]:
                country_city_variants.append(f"{major_city}, {country}")

        for candidate in [
            original,
            ", ".join(part for part in [city, state, country] if part),
            ", ".join(part for part in [city, country] if part),
            " ".join(part for part in [city, state, country] if part),
            " ".join(part for part in [city, country] if part),
            *country_city_variants,
        ]:
            cleaned = re.sub(r"\s+", " ", (candidate or "").strip())
            ascii_variant = unicodedata.normalize("NFKD", cleaned).encode("ascii", "ignore").decode("ascii").strip()
            for variant in [cleaned, ascii_variant]:
                if variant and variant not in variants:
                    variants.append(variant)

        variant_limit = COUNTRY_FANOUT_CITY_LIMIT + 1 if country and not city else MAX_SEARCH_VARIANTS
        return variants[:variant_limit]

    def _build_search_queries(self, keyword: str, location: str, radius: str, include_country_fanout: bool = True) -> List[str]:
        location_info = self.determine_location_from_input(location)
        location_variants = self._build_location_variants(location_info, include_country_fanout=include_country_fanout)
        queries: List[str] = []

        base_keyword = re.sub(r"\s+", " ", (keyword or "").strip())
        if not base_keyword:
            return queries

        if not location_variants:
            queries.append(base_keyword)
        else:
            for variant in location_variants:
                queries.append(f"{base_keyword} {variant}".strip())
                queries.append(f"{base_keyword} in {variant}".strip())

        unique_queries: List[str] = []
        seen = set()
        for query in queries:
            normalized = self._normalize_lookup_text(query)
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique_queries.append(query)

        query_limit = max(len(location_variants) * 2, 4)
        return unique_queries[:query_limit]

    def _build_search_batches(self, keyword: str, location: str, radius: str) -> List[Dict[str, object]]:
        location_info = self.determine_location_from_input(location)
        country = (location_info.get("country") or "").strip()
        city = (location_info.get("city") or "").strip()

        if not country or city:
            return [
                {
                    "label": location_info.get("specific_location") or location or "worldwide",
                    "location": location,
                    "location_info": location_info,
                    "queries": self._build_search_queries(keyword, location, radius, include_country_fanout=True),
                }
            ]

        major_cities = MAJOR_CITIES.get(country, [])[:COUNTRY_BATCH_CITY_LIMIT]
        batches: List[Dict[str, object]] = [
            {
                "label": country,
                "location": country,
                "location_info": location_info,
                "queries": self._build_search_queries(keyword, country, radius, include_country_fanout=False),
            }
        ]

        for batch_index in range(0, len(major_cities), COUNTRY_BATCH_SIZE):
            city_chunk = major_cities[batch_index: batch_index + COUNTRY_BATCH_SIZE]
            queries: List[str] = []
            for major_city in city_chunk:
                city_location = f"{major_city}, {country}"
                queries.extend(self._build_search_queries(keyword, city_location, radius, include_country_fanout=False))

            deduped_queries: List[str] = []
            seen_queries: set[str] = set()
            for query in queries:
                normalized_query = self._normalize_lookup_text(query)
                if normalized_query and normalized_query not in seen_queries:
                    seen_queries.add(normalized_query)
                    deduped_queries.append(query)

            label = f"{country} cities {batch_index + 1}-{batch_index + len(city_chunk)}"
            batches.append(
                {
                    "label": label,
                    "location": ", ".join(city_chunk),
                    "location_info": {**location_info, "specific_location": label},
                    "queries": deduped_queries,
                }
            )

        return batches

    def _resolve_headless_mode(self, requested_headless: bool) -> bool:
        if requested_headless:
            return True
        if os.name != "nt":
            has_display = bool(os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY"))
            if not has_display:
                logger.info("No desktop display detected; forcing headless browser mode.")
                return True
        return False

    def load_country_data(self) -> Dict[str, List[str]]:
        aliases: Dict[str, List[str]] = {}
        for iso_code, country_name in ALL_COUNTRIES.items():
            aliases.setdefault(country_name, []).append(iso_code)

        for variation, canonical_country in COUNTRY_VARIATIONS.items():
            aliases.setdefault(canonical_country, []).append(variation)

        return {country: sorted(set(values)) for country, values in aliases.items()}

    def load_city_data(self) -> Dict[str, str]:
        city_map: Dict[str, str] = {}
        for country, cities in MAJOR_CITIES.items():
            for city in cities:
                city_map[self._normalize_lookup_text(city)] = country
        return city_map

    def determine_location_from_input(self, location_input: str) -> Dict[str, str]:
        location_info = {
            "country": "",
            "city": "",
            "state_province": "",
            "specific_location": "",
            "original_input": location_input,
        }
        if not location_input or not location_input.strip():
            return location_info

        normalized = re.sub(r"\s+", " ", location_input.strip())
        parts = self._location_parts_from_input(normalized)
        if len(parts) >= 2:
            location_info["city"] = parts[0]
            location_info["country"] = self._canonical_country_name(parts[-1])
            location_info["specific_location"] = ", ".join(part for part in [parts[0], *parts[1:-1], location_info["country"]] if part)
            if len(parts) >= 3:
                location_info["state_province"] = parts[1]
        else:
            lowered = self._normalize_lookup_text(normalized)
            for country, codes in self.country_aliases.items():
                aliases = {self._normalize_lookup_text(country), *(self._normalize_lookup_text(code) for code in codes)}
                if lowered in aliases:
                    location_info["country"] = country
                    break
            if not location_info["country"]:
                location_info["city"] = normalized
                inferred_country = self._infer_country_from_city(normalized)
                if inferred_country:
                    location_info["country"] = inferred_country

        lowered = self._normalize_lookup_text(normalized)
        for country, codes in self.country_aliases.items():
            aliases = [country, *codes]
            if any(self._matches_country_alias(lowered, alias) for alias in aliases):
                location_info["country"] = country
                break

        if location_info["country"]:
            location_info["country"] = self._canonical_country_name(location_info["country"])

        if location_info["city"] and not location_info["country"]:
            inferred_country = self._infer_country_from_city(location_info["city"])
            if inferred_country:
                location_info["country"] = inferred_country

        if location_info["city"] and not location_info["specific_location"]:
            location_info["specific_location"] = ", ".join(
                part for part in [location_info["city"], location_info["state_province"], location_info["country"]] if part
            )

        return location_info

    def create_directories(self) -> None:
        for directory in [self.config_dir, self.cache_dir, "results"]:
            os.makedirs(directory, exist_ok=True)

    def _resolve_browser_binary(self) -> Optional[str]:
        env_candidates = [
            os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH", "").strip(),
            os.getenv("CHROME_BINARY_PATH", "").strip(),
            os.getenv("GOOGLE_CHROME_BIN", "").strip(),
            os.getenv("CHROMIUM_BIN", "").strip(),
        ]
        for candidate in env_candidates:
            if candidate and os.path.exists(candidate):
                logger.info("Using browser binary: %s", candidate)
                return candidate
        return None

    def _enforce_playwright_runtime_environment(self) -> None:
        configured_path = os.getenv("PLAYWRIGHT_BROWSERS_PATH", "").strip()
        if configured_path != DEFAULT_PLAYWRIGHT_BROWSERS_PATH:
            logger.info(
                "Overriding PLAYWRIGHT_BROWSERS_PATH from %s to hermetic mode (%s).",
                configured_path or "<unset>",
                DEFAULT_PLAYWRIGHT_BROWSERS_PATH,
            )
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = DEFAULT_PLAYWRIGHT_BROWSERS_PATH

    def _resolve_browser_channel(self, browser_binary: Optional[str]) -> Optional[str]:
        forced_channel = os.getenv("PLAYWRIGHT_BROWSER_CHANNEL", "").strip().lower()
        if forced_channel in {"chrome", "msedge"}:
            return forced_channel
        binary_name = os.path.basename(browser_binary or "").lower()
        if "edge" in binary_name:
            return "msedge"
        if "chrome" in binary_name:
            return "chrome"
        return None

    def _install_playwright_browser(self) -> None:
        install_env = os.environ.copy()
        install_env["PLAYWRIGHT_BROWSERS_PATH"] = DEFAULT_PLAYWRIGHT_BROWSERS_PATH
        logger.warning("Playwright browser executable is missing. Installing Chromium runtime now...")
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            env=install_env,
        )

    def _should_reinstall_browser(self, exc: Exception) -> bool:
        message = str(exc)
        return "Executable doesn't exist" in message or "Please run the following command to download new browsers" in message

    def _launch_browser(self, launch_kwargs: Dict[str, object]):
        if self.playwright is None:
            self.playwright = sync_playwright().start()

        try:
            return self.playwright.chromium.launch(**launch_kwargs)
        except PlaywrightError as exc:
            if not self._should_reinstall_browser(exc):
                raise

            with _PLAYWRIGHT_INSTALL_LOCK:
                self._install_playwright_browser()

            return self.playwright.chromium.launch(**launch_kwargs)

    def _build_request_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self.session_user_agent or "Mozilla/5.0",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def setup_driver(self) -> None:
        self._enforce_playwright_runtime_environment()
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        ]
        browser_binary = self._resolve_browser_binary()
        browser_channel = self._resolve_browser_channel(browser_binary)

        launch_kwargs = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-notifications",
            ],
        }
        if browser_binary:
            launch_kwargs["executable_path"] = browser_binary
        elif browser_channel:
            launch_kwargs["channel"] = browser_channel

        self.session_user_agent = random.choice(user_agents)
        self.browser = self._launch_browser(launch_kwargs)
        self.context = self.browser.new_context(
            user_agent=self.session_user_agent,
            viewport={"width": random.randint(1366, 1680), "height": random.randint(820, 980)},
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        self.context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            """
        )
        self.page = self.context.new_page()
        self.page.set_default_timeout(20_000)
        self.page.set_default_navigation_timeout(PAGE_LOAD_TIMEOUT_SECONDS * 1000)

    def cleanup(self) -> None:
        if self.context is not None:
            try:
                self.context.close()
            except Exception:
                pass
        if self.browser is not None:
            try:
                self.browser.close()
            except Exception:
                pass
        if self.playwright is not None:
            try:
                self.playwright.stop()
            except Exception:
                pass
        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None

    def build_search_url(self, keyword: str, location: str = "", radius: str = "10000") -> str:
        search_queries = self._build_search_queries(keyword, location, radius)
        terms = [search_queries[0]] if search_queries else [keyword]
        query = "+".join(urllib.parse.quote_plus(term) for term in terms if term)
        url = f"https://www.google.com/maps/search/{query}/?hl=en&gl=us"
        if radius and radius != "10000":
            url = f"{url}&radius={urllib.parse.quote_plus(radius)}"
        return url

    def _open_best_search_page(self, keyword: str, location: str, radius: str, progress_callback=None) -> None:
        queries = self._build_search_queries(keyword, location, radius)
        last_error: Optional[Exception] = None
        for index, query in enumerate(queries, start=1):
            encoded_query = "+".join(urllib.parse.quote_plus(term) for term in [query] if term)
            url = f"https://www.google.com/maps/search/{encoded_query}/?hl=en&gl=us"
            if radius and radius != "10000":
                url = f"{url}&radius={urllib.parse.quote_plus(radius)}"
            logger.info("Searching Google Maps with Playwright (%s/%s): %s", index, len(queries), url)
            if progress_callback:
                progress_callback(0, f"Opening Google Maps query {index}/{len(queries)}: {query}")

            try:
                self._open_search_page(url)
                self.handle_google_maps_ui()
                if self._wait_for_results_or_empty_state():
                    return
            except Exception as exc:
                last_error = exc
                logger.warning("Google Maps query variant failed: %s", exc)
                continue

        if last_error is not None:
            raise last_error
        raise RuntimeError("Google Maps did not return visible results for any search query variant.")

    def _open_search_query(self, query: str, radius: str, query_index: int, total_queries: int, progress_callback=None) -> bool:
        encoded_query = "+".join(urllib.parse.quote_plus(term) for term in [query] if term)
        url = f"https://www.google.com/maps/search/{encoded_query}/?hl=en&gl=us"
        if radius and radius != "10000":
            url = f"{url}&radius={urllib.parse.quote_plus(radius)}"
        logger.info("Searching Google Maps with Playwright (%s/%s): %s", query_index, total_queries, url)
        if progress_callback:
            progress_callback(0, f"Opening Google Maps query {query_index}/{total_queries}: {query}")

        self._open_search_page(url)
        self.handle_google_maps_ui()
        return self._wait_for_results_or_empty_state()

    def _collect_results_from_open_page(
        self,
        keyword: str,
        location: str,
        location_info: Dict[str, str],
        results: List[Dict[str, object]],
        seen_businesses: set[str],
        progress_callback=None,
    ) -> int:
        start_count = len(results)
        self.scroll_results_enhanced(progress_callback=progress_callback)
        if progress_callback:
            progress_callback(len(results), f"Loaded map results for {location_info.get('specific_location') or location or 'worldwide'}. Opening business cards...")

        index = 0
        stagnant_cards = 0
        while len(results) < self.max_results:
            cards = self._get_business_cards()
            current_count = cards.count()
            if index >= current_count:
                previous_count = current_count
                self.scroll_results_enhanced(progress_callback=progress_callback)
                current_count = self._get_business_cards().count()
                if current_count <= previous_count:
                    stagnant_cards += 1
                else:
                    stagnant_cards = 0
                if index >= current_count and stagnant_cards >= 3:
                    break
                if index >= current_count:
                    continue

            if progress_callback:
                progress_callback(len(results), f"Opening card {index + 1} of at least {current_count} loaded results...")
            business_data = self.scrape_business_card(cards.nth(index), index + 1, location_info)
            if business_data:
                identity = self._build_card_identity(business_data)
                if identity not in seen_businesses:
                    seen_businesses.add(identity)
                    results.append(business_data)
                    if progress_callback:
                        progress_callback(
                            len(results),
                            f"Downloaded {len(results)} of {self.max_results} businesses. Last: {business_data.get('name', 'Unknown')}",
                        )
            if (index + 1) % 10 == 0 and results:
                self.save_progress(results, keyword, location, f"_partial_{len(results)}")
            if (index + 1) % 25 == 0:
                self.scroll_results_enhanced(progress_callback=progress_callback)
            index += 1
            self.human_like_delay()

        return len(results) - start_count

    def human_like_delay(self, minimum: Optional[float] = None, maximum: Optional[float] = None) -> None:
        low = self.delay_between_requests - 0.5 if minimum is None else minimum
        high = self.delay_between_requests + 0.5 if maximum is None else maximum
        time.sleep(max(0.1, random.uniform(low, high)))

    def _open_search_page(self, url: str) -> None:
        if self.page is None:
            raise RuntimeError("Browser page was not initialized.")
        try:
            self.page.goto(url, wait_until="domcontentloaded")
        except PlaywrightError as exc:
            raise RuntimeError(f"Browser navigation failed: {exc}") from exc

    def _click_first_matching_button(self, labels: List[str]) -> bool:
        if self.page is None:
            return False
        for label in labels:
            locator = self.page.get_by_role("button", name=re.compile(re.escape(label), re.IGNORECASE)).first
            try:
                if locator.count():
                    locator.click(timeout=2_500)
                    return True
            except Exception:
                continue
        return False

    def handle_google_maps_ui(self) -> None:
        self.human_like_delay(1.0, 1.8)
        self._click_first_matching_button(["Accept all", "I agree", "Accept", "Tout accepter"])
        self._click_first_matching_button(["Got it", "OK", "Continue", "No thanks"])

    def _get_business_cards(self) -> Locator:
        if self.page is None:
            raise RuntimeError("Browser page was not initialized.")
        return self.page.locator(", ".join(BUSINESS_CARD_SELECTORS))

    def _count_business_cards(self) -> int:
        if self.page is None:
            return 0
        highest_count = 0
        for selector in BUSINESS_CARD_SELECTORS:
            try:
                count = self.page.locator(selector).count()
            except Exception:
                continue
            if count > highest_count:
                highest_count = count
        return highest_count

    def _wait_for_results_or_empty_state(self) -> bool:
        if self.page is None:
            return False
        deadline = time.monotonic() + RESULTS_PANEL_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self._count_business_cards() > 0:
                return True
            body = (self.page.locator("body").inner_text(timeout=2_000) or "").lower()
            if "no results found" in body or "did not match any locations" in body:
                return False
            time.sleep(1)
        raise RuntimeError(
            f"Google Maps did not load visible results within {RESULTS_PANEL_TIMEOUT_SECONDS}s. URL='{self.page.url}'."
        )

    def _find_results_panel(self) -> Optional[Locator]:
        if self.page is None:
            return None
        for selector in RESULT_PANEL_SELECTORS:
            locator = self.page.locator(selector).first
            try:
                if locator.count() and locator.is_visible(timeout=1_500):
                    return locator
            except Exception:
                continue
        return None

    def _scroll_results_panel(self, panel: Locator) -> None:
        if self.page is None:
            return

        scroll_attempts = [
            self._scroll_results_panel_via_evaluate,
            self._scroll_results_panel_via_handle,
            self._scroll_results_panel_via_wheel,
            self._scroll_results_panel_via_keyboard,
        ]
        for strategy in scroll_attempts:
            try:
                strategy(panel)
                self.human_like_delay(1.0, 2.2)
                return
            except Exception as exc:
                logger.debug("Results scroll strategy %s failed: %s", strategy.__name__, exc)
                continue

        raise RuntimeError("Could not scroll the Google Maps results panel with any locator strategy.")

    def _scroll_results_panel_via_evaluate(self, panel: Locator) -> None:
        panel.evaluate(
            """
            (element) => {
                const step = Math.floor((element.clientHeight || 800) * (0.45 + Math.random() * 0.25));
                element.scrollBy({ top: step, behavior: 'auto' });
            }
            """,
            timeout=5_000,
        )

    def _scroll_results_panel_via_handle(self, panel: Locator) -> None:
        if self.page is None:
            return
        handle = panel.element_handle(timeout=3_000)
        if handle is None:
            raise RuntimeError("Results panel element handle was not available.")
        self.page.evaluate(
            """
            (element) => {
                const step = Math.floor((element.clientHeight || 800) * (0.5 + Math.random() * 0.2));
                element.scrollTop = (element.scrollTop || 0) + step;
            }
            """,
            handle,
        )

    def _scroll_results_panel_via_wheel(self, panel: Locator) -> None:
        if self.page is None:
            return
        panel.hover(timeout=2_000)
        self.page.mouse.wheel(0, random.randint(700, 1200))

    def _scroll_results_panel_via_keyboard(self, panel: Locator) -> None:
        if self.page is None:
            return
        panel.click(timeout=2_000)
        self.page.keyboard.press("PageDown")
        self.page.keyboard.press("ArrowDown")

    def scroll_results_enhanced(self, progress_callback=None) -> None:
        panel = self._find_results_panel()
        if panel is None:
            logger.warning("Could not find Google Maps results panel.")
            return
        last_count = 0
        stagnant_rounds = 0
        max_scroll_rounds = max(45, min(320, int(self.max_results / 3) + 30))
        for _ in range(max_scroll_rounds):
            panel = self._find_results_panel() or panel
            count = self._count_business_cards()
            if progress_callback:
                progress_callback(0, f"Loaded {count} map results so far...")
            if count >= self.max_results:
                break
            if count <= last_count:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0
                last_count = count
            if stagnant_rounds >= MAX_SCROLL_STAGNANT_ROUNDS:
                break
            self._scroll_results_panel(panel)

    def _build_card_identity(self, business_data: Dict[str, object]) -> str:
        place_id = self._clean_text(str(business_data.get("place_id") or "")).lower()
        if place_id:
            return f"place:{place_id}"
        website = self._clean_text(str(business_data.get("website") or "")).lower()
        if website:
            return f"website:{website}"
        name = self._clean_text(str(business_data.get("name") or "")).lower()
        address = self._clean_text(str(business_data.get("address") or "")).lower()
        return f"name:{name}|address:{address}"

    def _inner_text(self, selector: str) -> str:
        if self.page is None:
            return ""
        locator = self.page.locator(selector).first
        try:
            if locator.count():
                return (locator.inner_text(timeout=2_500) or "").strip()
        except Exception:
            return ""
        return ""

    def _attribute(self, selector: str, attribute: str) -> str:
        if self.page is None:
            return ""
        locator = self.page.locator(selector).first
        try:
            if locator.count():
                value = locator.get_attribute(attribute, timeout=2_500)
                return (value or "").strip()
        except Exception:
            return ""
        return ""

    def _first_text(self, selectors: List[str], minimum_length: int = 1) -> str:
        seen: set[str] = set()
        for selector in selectors:
            if selector in seen:
                continue
            seen.add(selector)
            value = self._inner_text(selector)
            if value and len(value.strip()) >= minimum_length:
                return value.strip()
        return ""

    def _first_attribute(self, selector_attribute_pairs: List[Tuple[str, str]]) -> str:
        seen: set[Tuple[str, str]] = set()
        for selector, attribute in selector_attribute_pairs:
            key = (selector, attribute)
            if key in seen:
                continue
            seen.add(key)
            value = self._attribute(selector, attribute)
            if value:
                return value
        return ""

    def _clean_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", (value or "").strip())

    def _normalize_website(self, value: str) -> str:
        cleaned = self._clean_text(value)
        if not cleaned:
            return ""
        if cleaned.startswith("http://") or cleaned.startswith("https://"):
            return cleaned
        if cleaned.startswith("www."):
            return f"https://{cleaned}"
        return cleaned

    def _normalize_phone(self, value: str) -> str:
        cleaned = self._clean_text(value)
        if not cleaned:
            return ""
        match = self.phone_pattern.search(cleaned)
        return self._clean_text(match.group(0)) if match else cleaned

    def _fetch_url_text(self, url: str) -> Tuple[str, str]:
        request = urlrequest.Request(url, headers=self._build_request_headers())
        with urlrequest.urlopen(request, timeout=WEBSITE_FETCH_TIMEOUT_SECONDS) as response:
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                return "", response.geturl()
            body = response.read().decode("utf-8", errors="replace")
            return body, response.geturl()

    def _extract_contact_links_from_html(self, html: str, base_url: str) -> List[str]:
        soup = BeautifulSoup(html, "html.parser")
        links: List[str] = []
        seen = set()
        for anchor in soup.select("a[href]"):
            href = (anchor.get("href") or "").strip()
            label = self._clean_text(anchor.get_text(" "))
            if not href:
                continue
            absolute = urllib.parse.urljoin(base_url, href)
            lowered = absolute.lower()
            if any(path in lowered for path in WEBSITE_CONTACT_PATHS) or any(word in label.lower() for word in ["contact", "about", "support"]):
                if absolute not in seen:
                    links.append(absolute)
                    seen.add(absolute)
            if len(links) >= WEBSITE_FETCH_MAX_PAGES - 1:
                break
        return links

    def _extract_contact_details_from_html(self, html: str, base_url: str) -> Dict[str, str]:
        info = {"email": "", "phone": "", "social_media": ""}
        if not html:
            return info

        emails: List[str] = []
        for email in self.email_pattern.findall(html):
            cleaned = email.strip().lower()
            if cleaned and cleaned not in emails:
                emails.append(cleaned)
        if emails:
            info["email"] = emails[0]

        phone_candidates: List[str] = []
        for match in self.phone_pattern.finditer(html):
            candidate = self._normalize_phone(match.group(0))
            if candidate and candidate not in phone_candidates and len(re.sub(r"\D", "", candidate)) >= 7:
                phone_candidates.append(candidate)
        if phone_candidates:
            info["phone"] = phone_candidates[0]

        soup = BeautifulSoup(html, "html.parser")
        social_links: List[str] = []
        for anchor in soup.select("a[href]"):
            href = urllib.parse.urljoin(base_url, (anchor.get("href") or "").strip())
            lowered = href.lower()
            if any(domain in lowered for domain in ["facebook.com", "instagram.com", "linkedin.com", "x.com", "twitter.com", "tiktok.com", "youtube.com"]):
                if href not in social_links:
                    social_links.append(href)
        if social_links:
            info["social_media"] = ", ".join(social_links[:5])

        return info

    def _enrich_from_website(self, website_url: str) -> Dict[str, str]:
        normalized_website = self._normalize_website(website_url)
        if not normalized_website or not normalized_website.startswith(("http://", "https://")):
            return {"email": "", "phone": "", "social_media": ""}

        visited = set()
        queue = [normalized_website]
        best = {"email": "", "phone": "", "social_media": ""}

        while queue and len(visited) < WEBSITE_FETCH_MAX_PAGES:
            current_url = queue.pop(0)
            if current_url in visited:
                continue
            visited.add(current_url)

            try:
                html, final_url = self._fetch_url_text(current_url)
            except (urlerror.URLError, TimeoutError, OSError, ValueError) as exc:
                logger.debug("Website enrichment fetch failed for %s: %s", current_url, exc)
                continue

            extracted = self._extract_contact_details_from_html(html, final_url)
            for key, value in extracted.items():
                if value and not best.get(key):
                    best[key] = value

            if best.get("email") and best.get("phone") and best.get("social_media"):
                break

            for next_url in self._extract_contact_links_from_html(html, final_url):
                if next_url not in visited and next_url not in queue:
                    queue.append(next_url)

        return best

    def _extract_social_media_links(self) -> str:
        if self.page is None:
            return ""
        social_domains = ("facebook.com", "instagram.com", "linkedin.com", "x.com", "twitter.com", "tiktok.com", "youtube.com")
        links: List[str] = []
        for domain in social_domains:
            locator = self.page.locator(f"a[href*='{domain}']")
            try:
                count = min(locator.count(), 3)
            except Exception:
                continue
            for index in range(count):
                try:
                    href = locator.nth(index).get_attribute("href", timeout=1_500) or ""
                except Exception:
                    href = ""
                href = href.strip()
                if href and href not in links:
                    links.append(href)
        return ", ".join(links)

    def _split_address_parts(self, address: str) -> Dict[str, str]:
        info = {
            "address": self._clean_text(address),
            "country": "",
            "city": "",
            "street": "",
            "postal_code": "",
            "state_province": "",
        }
        if not info["address"]:
            return info
        postal_match = self.postal_pattern.search(info["address"])
        if postal_match:
            info["postal_code"] = postal_match.group(0)
        parts = [self._clean_text(part) for part in info["address"].split(",") if self._clean_text(part)]
        if parts:
            info["street"] = parts[0]
        if len(parts) >= 2:
            info["city"] = parts[-2]
        if len(parts) >= 3:
            info["state_province"] = parts[-3] if len(parts) > 3 else parts[1]
        lowered = info["address"].lower()
        for country in self.country_aliases:
            if country.lower() in lowered:
                info["country"] = country
                break
        if not info["country"] and parts:
            info["country"] = parts[-1]
        if info["city"] and not info["country"]:
            info["country"] = self._infer_country_from_city(info["city"])
        if info["country"]:
            info["country"] = self._canonical_country_name(info["country"])
        return info

    def _extract_reviews_count(self, value: str) -> int:
        review_match = re.search(r"(\d[\d,]*)", value or "")
        return int(review_match.group(1).replace(",", "")) if review_match else 0

    def _extract_rating(self, value: str) -> float:
        rating_match = re.search(r"(\d+(?:\.\d+)?)", value or "")
        return float(rating_match.group(1)) if rating_match else 0.0

    def _normalize_category(self, value: str) -> str:
        cleaned = self._clean_text(value)
        if not cleaned:
            return ""
        cleaned = re.sub(r"\b\d[\d,]*\s+reviews?\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b\d+(?:\.\d+)?\b", "", cleaned).strip(" ·,-")
        return self._clean_text(cleaned)

    def _extract_business_hours_and_description(self) -> Dict[str, str]:
        hours = self._first_text(DETAIL_HOURS_SELECTORS)
        description = self._first_text(DETAIL_DESCRIPTION_SELECTORS, minimum_length=20)
        return {
            "business_hours": hours.replace("\n", " | ") if hours else "",
            "description": description if len(description) > 20 else "",
        }

    def _extract_contact_info(self) -> Dict[str, str]:
        info = {"phone": "", "website": "", "email": "", "social_media": ""}
        phone_text = self._first_text(DETAIL_PHONE_TEXT_SELECTORS)
        if phone_text and self.phone_pattern.search(phone_text):
            info["phone"] = self._normalize_phone(phone_text)
        website = self._first_attribute(DETAIL_WEBSITE_ATTRIBUTE_SELECTORS)
        if website and "google." not in website.lower():
            info["website"] = self._normalize_website(website)
        if self.page is not None:
            body = self.page.locator("body").inner_text(timeout=2_000)
            email_match = self.email_pattern.search(body or "")
            if email_match:
                info["email"] = email_match.group(0)
        info["social_media"] = self._extract_social_media_links()
        return info

    def _extract_address_info(self) -> Dict[str, str]:
        address = self._first_text(DETAIL_ADDRESS_TEXT_SELECTORS, minimum_length=6)
        return self._split_address_parts(address)

    def extract_basic_card_info(self, card: Locator) -> Dict[str, object]:
        info: Dict[str, object] = {
            "name": "",
            "rating": 0.0,
            "reviews_count": 0,
            "category": "",
            "address": "",
        }
        try:
            card_text = (card.inner_text(timeout=3_000) or "").strip()
        except Exception:
            return info
        lines = [line.strip() for line in card_text.splitlines() if line.strip()]
        if lines:
            info["name"] = lines[0]
        info["rating"] = self._extract_rating(card_text)
        info["reviews_count"] = self._extract_reviews_count(card_text)
        if len(lines) >= 2:
            info["category"] = self._normalize_category(lines[1])
        if len(lines) >= 3:
            info["address"] = self._clean_text(lines[2])
        return info

    def _open_business_details(self, card: Locator) -> None:
        if self.page is None:
            raise RuntimeError("Browser page was not initialized.")
        previous_url = self.page.url
        card.scroll_into_view_if_needed(timeout=3_000)
        self.human_like_delay(0.3, 0.8)
        try:
            card.hover(timeout=2_000)
        except Exception:
            pass
        try:
            card.click(timeout=4_000)
        except Exception:
            card.click(timeout=4_000, force=True)
        self.page.wait_for_function(
            """
            ({ previous, selectors }) => {
                const readyNode = selectors.some((selector) => Boolean(document.querySelector(selector)));
                const heading = document.querySelector("h1");
                return window.location.href !== previous || readyNode || Boolean(heading);
            }
            """,
            arg={"previous": previous_url, "selectors": DETAIL_READY_SELECTORS},
            timeout=DETAIL_PANEL_TIMEOUT_SECONDS * 1000,
        )
        self.human_like_delay(1.0, 1.8)

    def _close_detail_panel(self) -> None:
        if self.page is None:
            return
        try:
            self.page.keyboard.press("Escape")
            self.human_like_delay(0.4, 0.9)
        except Exception:
            pass

    def scrape_business_card(self, card: Locator, index: int, location_info: Dict[str, str]) -> Optional[Dict[str, object]]:
        try:
            data = BusinessData()
            basic_info = self.extract_basic_card_info(card)
            if not basic_info.get("name"):
                return None
            for key, value in basic_info.items():
                if hasattr(data, key) and value:
                    setattr(data, key, value)
            if location_info.get("country"):
                data.country = location_info["country"]
            if location_info.get("city"):
                data.city = location_info["city"]
            if location_info.get("state_province"):
                data.state_province = location_info["state_province"]

            try:
                self._open_business_details(card)
                if self.page is not None:
                    current_url = self.page.url
                    data.source_url = current_url
                    latitude, longitude = self.extract_coordinates_from_url(current_url)
                    data.latitude = latitude
                    data.longitude = longitude
                    data.place_id = self.extract_place_id(current_url)

                detail_name = self._first_text(DETAIL_HEADING_SELECTORS, minimum_length=2)
                if detail_name:
                    data.name = self._clean_text(detail_name)

                rating_text = self._first_attribute(DETAIL_RATING_ATTRIBUTE_SELECTORS) or self._first_text(DETAIL_RATING_TEXT_SELECTORS)
                if rating_text:
                    data.rating = self._extract_rating(rating_text)

                review_text = self._first_text(DETAIL_REVIEW_SELECTORS) or rating_text
                if review_text:
                    data.reviews_count = self._extract_reviews_count(review_text)

                category = self._first_text(DETAIL_CATEGORY_SELECTORS)
                if category:
                    data.category = self._normalize_category(category.split("\n")[0].strip())

                details = self._extract_contact_info()
                details.update(self._extract_address_info())
                details.update(self._extract_business_hours_and_description())
                if details.get("website"):
                    enriched = self._enrich_from_website(details["website"])
                    for field in ("email", "phone", "social_media"):
                        if enriched.get(field) and not details.get(field):
                            details[field] = enriched[field]
                for key, value in details.items():
                    if hasattr(data, key) and value:
                        setattr(data, key, value)
            except Exception as exc:
                logger.debug("Could not fully open detail panel for card %s: %s", index, exc)
            finally:
                self._close_detail_panel()

            data.scraped_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return asdict(data)
        except Exception as exc:
            logger.error("Error scraping card %s: %s", index, exc)
            return None

    def scrape(self, keyword: str, location: str = "", radius: str = "10000", max_results: int = None, progress_callback=None):
        if max_results:
            self.max_results = max_results

        self.setup_driver()
        location_info = self.determine_location_from_input(location)
        results: List[Dict[str, object]] = []
        seen_businesses: set[str] = set()
        batches = self._build_search_batches(keyword, location, radius)

        try:
            last_error: Optional[Exception] = None
            for batch_index, batch in enumerate(batches, start=1):
                if len(results) >= self.max_results:
                    break

                batch_queries = batch.get("queries") or []
                batch_location = str(batch.get("location") or location)
                batch_location_info = batch.get("location_info") or location_info
                batch_label = str(batch.get("label") or batch_location or "worldwide")
                if progress_callback:
                    progress_callback(len(results), f"Starting region batch {batch_index}/{len(batches)}: {batch_label}")

                for query_index, query in enumerate(batch_queries, start=1):
                    if len(results) >= self.max_results:
                        break

                    try:
                        if not self._open_search_query(query, radius, query_index, len(batch_queries), progress_callback=progress_callback):
                            continue
                        added = self._collect_results_from_open_page(
                            keyword,
                            batch_location,
                            batch_location_info,
                            results,
                            seen_businesses,
                            progress_callback=progress_callback,
                        )
                        if progress_callback:
                            progress_callback(
                                len(results),
                                f"Batch {batch_index}/{len(batches)} query {query_index}/{len(batch_queries)} finished with {added} new businesses.",
                            )
                    except Exception as exc:
                        last_error = exc
                        logger.warning(
                            "Search query failed (batch %s/%s, query %s/%s): %s",
                            batch_index,
                            len(batches),
                            query_index,
                            len(batch_queries),
                            exc,
                        )
                        continue

            if not results and last_error is not None:
                raise last_error

            if progress_callback:
                progress_callback(len(results), f"Scrape completed with {len(results)} businesses.")
            return results
        finally:
            self.cleanup()

    def extract_coordinates_from_url(self, url: str) -> Tuple[str, str]:
        patterns = [
            r"@(-?\d+\.\d+),(-?\d+\.\d+)",
            r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)",
            r"place/.+@(-?\d+\.\d+),(-?\d+\.\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1), match.group(2)
        return "", ""

    def extract_place_id(self, url: str) -> str:
        patterns = [r"place/([^/@]+)", r"!1s([^!]+)", r"cid=([^&]+)"]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return ""

    def save_progress(self, data, keyword, location, suffix="") -> None:
        if not data:
            return
        filename = self.generate_filename(keyword, location) + suffix + ".xlsx"
        pd.DataFrame(data).to_excel(filename, index=False)
        logger.info("Progress saved: %s", filename)

    def generate_filename(self, keyword: str, location: str = "") -> str:
        clean_keyword = re.sub(r"[^\w\s]", "", keyword.lower())
        clean_keyword = "_".join(clean_keyword.split()[:3])
        location_info = self.determine_location_from_input(location)
        location_parts = []
        if location_info["city"]:
            location_parts.append("_".join(re.sub(r"[^\w\s]", "", location_info["city"].lower()).split()))
        if location_info["country"]:
            location_parts.append("_".join(re.sub(r"[^\w\s]", "", location_info["country"].lower()).split()))
        if location_parts:
            base_name = f"{clean_keyword}_{'_'.join(location_parts[:2])}"
        else:
            base_name = f"{clean_keyword}_worldwide"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"results/{base_name}_{timestamp}"

    def save_to_excel(self, data, filename: str = None):
        if not data:
            logger.warning("No data to save")
            return None
        if not filename:
            filename = f"results/google_maps_scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        df = pd.DataFrame(data)
        column_order = [
            "name", "category", "address", "country", "city",
            "state_province", "street", "postal_code", "phone",
            "email", "website", "social_media", "rating",
            "reviews_count", "business_hours", "description",
            "latitude", "longitude", "place_id", "source_url",
            "scraped_date",
        ]
        existing_cols = [col for col in column_order if col in df.columns]
        extra_cols = [col for col in df.columns if col not in existing_cols]
        df = df[existing_cols + extra_cols]
        df.to_excel(filename, index=False)
        csv_file = filename.replace(".xlsx", ".csv")
        df.to_csv(csv_file, index=False, encoding="utf-8-sig")
        logger.info("Data saved to %s and %s", filename, csv_file)
        return df


if __name__ == "__main__":
    print("=" * 80)
    print("PLAYWRIGHT GOOGLE MAPS SCRAPER")
    print("=" * 80)
    keyword = input("Enter search keyword: ").strip()
    if not keyword:
        raise SystemExit("Keyword is required.")
    location = input("Enter location (optional): ").strip()
    max_results = int((input("Maximum results [1000]: ").strip() or "1000"))
    headless = input("Run in background? [y/N]: ").strip().lower() == "y"
    scraper = UniversalGoogleMapsScraper(headless=headless, max_results=min(max_results, 1000))
    rows = scraper.scrape(keyword=keyword, location=location)
    if rows:
        output = scraper.generate_filename(keyword, location) + ".xlsx"
        scraper.save_to_excel(rows, output)
        print(f"Saved {len(rows)} businesses to {output}")
    else:
        print("No businesses found.")