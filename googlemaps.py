import logging
import os
import random
import re
import subprocess
import sys
import threading
import time
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, Locator, sync_playwright


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
    def __init__(self, headless: bool = False, max_results: int = 100, scroll_pause: float = 2, delay_between_requests: float = 1.5):
        self.headless = self._resolve_headless_mode(headless)
        self.max_results = max_results
        self.scroll_pause = scroll_pause
        self.delay_between_requests = delay_between_requests
        self.playwright = None
        self.browser = None
        self.context = None
        self.page: Optional[Page] = None

        self.phone_pattern = re.compile(r"(\+\d{1,3}[\s\-]?)?\(?\d{1,4}\)?[\s\-]?\d{1,4}[\s\-]?\d{1,9}")
        self.email_pattern = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
        self.postal_pattern = re.compile(r"\b\d{5}(?:[-\s]\d{4})?\b|\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b")
        self.country_aliases = self.load_country_data()

        self.config_dir = "scraper_config"
        self.cache_dir = "cache"
        self.create_directories()

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
        return {
            "Afghanistan": ["AFG"],
            "Albania": ["ALB"],
            "Algeria": ["DZ", "DZA"],
            "Andorra": ["AND"],
            "Angola": ["AGO"],
            "Argentina": ["AR", "ARG"],
            "Australia": ["AU", "AUS"],
            "Austria": ["AT", "AUT"],
            "Bahrain": ["BHR"],
            "Bangladesh": ["BD", "BGD"],
            "Belgium": ["BE", "BEL"],
            "Brazil": ["BR", "BRA"],
            "Canada": ["CA", "CAN"],
            "Chile": ["CL", "CHL"],
            "China": ["CN", "CHN"],
            "Colombia": ["CO", "COL"],
            "Czech Republic": ["CZ", "CZE"],
            "Denmark": ["DK", "DNK"],
            "Egypt": ["EG", "EGY"],
            "Finland": ["FI", "FIN"],
            "France": ["FR", "FRA"],
            "Germany": ["DE", "DEU"],
            "Greece": ["GR", "GRC"],
            "Hong Kong": ["HK", "HKG"],
            "India": ["IN", "IND"],
            "Indonesia": ["ID", "IDN"],
            "Iran": ["IR", "IRN"],
            "Iraq": ["IQ", "IRQ"],
            "Ireland": ["IE", "IRL"],
            "Israel": ["IL", "ISR"],
            "Italy": ["IT", "ITA"],
            "Japan": ["JP", "JPN"],
            "Jordan": ["JO", "JOR"],
            "Kazakhstan": ["KZ", "KAZ"],
            "Kenya": ["KE", "KEN"],
            "Kuwait": ["KW", "KWT"],
            "Lebanon": ["LB", "LBN"],
            "Malaysia": ["MY", "MYS"],
            "Mexico": ["MX", "MEX"],
            "Morocco": ["MA", "MAR", "Maroc"],
            "Netherlands": ["NL", "NLD"],
            "New Zealand": ["NZ", "NZL"],
            "Nigeria": ["NG", "NGA"],
            "Norway": ["NO", "NOR"],
            "Oman": ["OM", "OMN"],
            "Pakistan": ["PK", "PAK"],
            "Philippines": ["PH", "PHL"],
            "Poland": ["PL", "POL"],
            "Portugal": ["PT", "PRT"],
            "Qatar": ["QA", "QAT"],
            "Romania": ["RO", "ROU"],
            "Russia": ["RU", "RUS"],
            "Saudi Arabia": ["SA", "SAU"],
            "Singapore": ["SG", "SGP"],
            "South Africa": ["ZA", "ZAF"],
            "South Korea": ["KR", "KOR"],
            "Spain": ["ES", "ESP"],
            "Sweden": ["SE", "SWE"],
            "Switzerland": ["CH", "CHE"],
            "Taiwan": ["TW", "TWN"],
            "Thailand": ["TH", "THA"],
            "Turkey": ["TR", "TUR"],
            "Ukraine": ["UA", "UKR"],
            "United Arab Emirates": ["AE", "ARE", "UAE"],
            "United Kingdom": ["GB", "GBR", "UK"],
            "United States": ["US", "USA"],
            "Vietnam": ["VN", "VNM"],
        }

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

        normalized = location_input.strip()
        parts = [part.strip() for part in normalized.split(",") if part.strip()]
        if len(parts) >= 2:
            location_info["city"] = parts[0]
            location_info["country"] = parts[-1]
            location_info["specific_location"] = normalized
            if len(parts) >= 3:
                location_info["state_province"] = parts[1]
        else:
            lowered = normalized.lower()
            for country, codes in self.country_aliases.items():
                if lowered == country.lower() or lowered in {code.lower() for code in codes}:
                    location_info["country"] = country
                    break
            if not location_info["country"]:
                location_info["city"] = normalized

        lowered = normalized.lower()
        for country, codes in self.country_aliases.items():
            if country.lower() in lowered or any(code.lower() in lowered for code in codes):
                location_info["country"] = country
                break

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
        install_env.setdefault("PLAYWRIGHT_BROWSERS_PATH", os.getenv("PLAYWRIGHT_BROWSERS_PATH", "0") or "0")
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

    def setup_driver(self) -> None:
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

        self.browser = self._launch_browser(launch_kwargs)
        self.context = self.browser.new_context(
            user_agent=random.choice(user_agents),
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
        location_info = self.determine_location_from_input(location)
        terms = [keyword]
        if location_info["specific_location"]:
            terms.append(location_info["specific_location"])
        elif location:
            terms.append(location)
        query = "+".join(urllib.parse.quote_plus(term) for term in terms if term)
        url = f"https://www.google.com/maps/search/{query}/?hl=en&gl=us"
        if radius and radius != "10000":
            url = f"{url}&radius={urllib.parse.quote_plus(radius)}"
        return url

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
        return self.page.locator("div[role='article'], div.Nv2PK, a.hfpxzc")

    def _wait_for_results_or_empty_state(self) -> bool:
        if self.page is None:
            return False
        deadline = time.monotonic() + RESULTS_PANEL_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self._get_business_cards().count() > 0:
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
        selectors = ["div[role='feed']", "div.m6QErb[aria-label*='Results']", "div.m6QErb.DxyBCb"]
        for selector in selectors:
            locator = self.page.locator(selector).first
            try:
                if locator.count():
                    return locator
            except Exception:
                continue
        return None

    def _scroll_results_panel(self, panel: Locator) -> None:
        panel.evaluate(
            """
            (element) => {
                const step = Math.floor(element.clientHeight * (0.45 + Math.random() * 0.25));
                element.scrollBy({ top: step, behavior: 'smooth' });
            }
            """
        )
        self.human_like_delay(1.0, 2.2)

    def scroll_results_enhanced(self, progress_callback=None) -> None:
        panel = self._find_results_panel()
        if panel is None:
            logger.warning("Could not find Google Maps results panel.")
            return
        last_count = 0
        stagnant_rounds = 0
        for _ in range(35):
            count = self._get_business_cards().count()
            if progress_callback:
                progress_callback(0, f"Loaded {count} map results so far...")
            if count >= self.max_results:
                break
            if count <= last_count:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0
                last_count = count
            if stagnant_rounds >= 5:
                break
            self._scroll_results_panel(panel)

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

    def _extract_business_hours_and_description(self) -> Dict[str, str]:
        hours = self._inner_text("div[aria-label*='Hours'], table.eK4R0e tbody, div.OMl5r")
        description = self._inner_text("div.PYvSYb, div.fontBodyMedium span, div[role='main'] span")
        return {
            "business_hours": hours.replace("\n", " | ") if hours else "",
            "description": description if len(description) > 20 else "",
        }

    def _extract_contact_info(self) -> Dict[str, str]:
        info = {"phone": "", "website": "", "email": "", "social_media": ""}
        phone_text = self._inner_text("button[data-item-id*='phone'], a[href^='tel:']")
        if phone_text and self.phone_pattern.search(phone_text):
            info["phone"] = phone_text
        website = self._attribute("a[data-item-id*='authority'], a[href^='http']", "href")
        if website and "google." not in website.lower():
            info["website"] = website
        if self.page is not None:
            body = self.page.locator("body").inner_text(timeout=2_000)
            email_match = self.email_pattern.search(body or "")
            if email_match:
                info["email"] = email_match.group(0)
        return info

    def _extract_address_info(self) -> Dict[str, str]:
        info = {
            "address": "",
            "country": "",
            "city": "",
            "street": "",
            "postal_code": "",
            "state_province": "",
        }
        address = self._inner_text("button[data-item-id*='address'], div[role='main'] button[aria-label*='Address']")
        if not address:
            return info
        info["address"] = address
        postal_match = self.postal_pattern.search(address)
        if postal_match:
            info["postal_code"] = postal_match.group(0)
        parts = [part.strip() for part in address.split(",") if part.strip()]
        if parts:
            info["street"] = parts[0]
        if len(parts) >= 2:
            info["city"] = parts[1]
        if len(parts) >= 3:
            info["state_province"] = parts[2]
        lowered = address.lower()
        for country in self.country_aliases:
            if country.lower() in lowered:
                info["country"] = country
                break
        return info

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
        rating_match = re.search(r"(\d+(?:\.\d+)?)", card_text)
        if rating_match:
            info["rating"] = float(rating_match.group(1))
        reviews_match = re.search(r"(\d[\d,]*)\s+reviews", card_text, re.IGNORECASE)
        if reviews_match:
            info["reviews_count"] = int(reviews_match.group(1).replace(",", ""))
        if len(lines) >= 2:
            info["category"] = lines[1]
        if len(lines) >= 3:
            info["address"] = lines[2]
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
            (previous) => {
                const addressButton = document.querySelector("button[data-item-id*='address']");
                const heading = document.querySelector("h1");
                return window.location.href !== previous || Boolean(addressButton) || Boolean(heading);
            }
            """,
            arg=previous_url,
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

                detail_name = self._inner_text("h1")
                if detail_name:
                    data.name = detail_name

                rating_text = self._attribute("span[role='img'][aria-label*='star']", "aria-label") or self._inner_text("span.MW4etd")
                if rating_text:
                    rating_match = re.search(r"(\d+(?:\.\d+)?)", rating_text)
                    if rating_match:
                        data.rating = float(rating_match.group(1))

                review_text = self._inner_text("button[jsaction*='pane.rating.category']") or rating_text
                review_match = re.search(r"(\d[\d,]*)", review_text or "")
                if review_match:
                    data.reviews_count = int(review_match.group(1).replace(",", ""))

                category = self._inner_text("button[jsaction*='pane.rating.category'], div.DkEaL")
                if category:
                    data.category = category.split("\n")[0].strip()

                details = self._extract_contact_info()
                details.update(self._extract_address_info())
                details.update(self._extract_business_hours_and_description())
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

        try:
            url = self.build_search_url(keyword, location, radius)
            logger.info("Searching Google Maps with Playwright: %s", url)
            if progress_callback:
                progress_callback(0, f"Opening Google Maps for {keyword} {location}".strip())

            self._open_search_page(url)
            self.handle_google_maps_ui()
            if not self._wait_for_results_or_empty_state():
                return []

            self.scroll_results_enhanced(progress_callback=progress_callback)
            total_cards = min(self._get_business_cards().count(), self.max_results)
            if progress_callback:
                progress_callback(0, f"Found {total_cards} map results. Opening business cards...")

            for index in range(total_cards):
                cards = self._get_business_cards()
                if index >= cards.count():
                    break
                if progress_callback:
                    progress_callback(len(results), f"Opening card {index + 1} of {total_cards}...")
                business_data = self.scrape_business_card(cards.nth(index), index + 1, location_info)
                if business_data:
                    results.append(business_data)
                    if progress_callback:
                        progress_callback(
                            len(results),
                            f"Downloaded {len(results)} of {self.max_results} businesses. Last: {business_data.get('name', 'Unknown')}",
                        )
                if (index + 1) % 10 == 0 and results:
                    self.save_progress(results, keyword, location, f"_partial_{index + 1}")
                self.human_like_delay()

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
    max_results = int((input("Maximum results [100]: ").strip() or "100"))
    headless = input("Run in background? [y/N]: ").strip().lower() == "y"
    scraper = UniversalGoogleMapsScraper(headless=headless, max_results=min(max_results, 500))
    rows = scraper.scrape(keyword=keyword, location=location)
    if rows:
        output = scraper.generate_filename(keyword, location) + ".xlsx"
        scraper.save_to_excel(rows, output)
        print(f"Saved {len(rows)} businesses to {output}")
    else:
        print("No businesses found.")