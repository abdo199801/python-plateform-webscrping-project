import logging
import os
import random
import re
import time
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from scraper_config.world_locations import ALL_COUNTRIES, COUNTRY_VARIATIONS, MAJOR_CITIES


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


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
    extraction_sources: str = ""


class UniversalGoogleMapsScraper:
    def __init__(self, headless: bool = False, max_results: int = 500, scroll_pause: float = 2.0, delay_between_requests: float = 1.5):
        self.headless = headless
        self.max_results = max_results
        self.scroll_pause = scroll_pause
        self.delay_between_requests = delay_between_requests
        self.driver = None
        self.wait = None

        self.phone_pattern = re.compile(r"(\+\d{1,3}[\s\-]?)?\(?\d{1,4}\)?[\s\-]?\d{1,4}[\s\-]?\d{1,9}")
        self.email_pattern = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
        self.postal_pattern = re.compile(r"\b\d{5}(?:[-\s]\d{4})?\b|\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b")
        self.website_pattern = re.compile(r"^https?://", re.IGNORECASE)

    def setup_driver(self) -> None:
        chrome_options = Options()

        if self.headless:
            chrome_options.add_argument("--headless=new")

        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--lang=en-US")
        chrome_options.add_argument("accept-language=en-US,en;q=0.9")

        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        ]
        chrome_options.add_argument(f"user-agent={random.choice(user_agents)}")

        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, 20)

        try:
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        except Exception:
            pass

    def human_like_delay(self) -> None:
        pause = random.uniform(max(0.3, self.delay_between_requests - 0.4), self.delay_between_requests + 0.6)
        time.sleep(pause)

    def determine_location_from_input(self, location_input: str) -> Dict[str, str]:
        info = {
            "country": "",
            "city": "",
            "state_province": "",
            "specific_location": "",
            "original_input": location_input or "",
        }
        if not location_input:
            return info

        normalized = location_input.strip()
        lowered = normalized.lower()

        for country in ALL_COUNTRIES:
            if country.lower() in lowered:
                info["country"] = country
                break

        if not info["country"]:
            for alias, canonical in COUNTRY_VARIATIONS.items():
                if alias.lower() in lowered:
                    info["country"] = canonical
                    break

        for city in MAJOR_CITIES:
            if city.lower() in lowered:
                info["city"] = city
                break

        if "," in normalized:
            info["specific_location"] = normalized
            if not info["city"]:
                first_part = normalized.split(",", 1)[0].strip()
                if len(first_part) >= 3:
                    info["city"] = first_part

        return info

    def build_search_url(self, keyword: str, location: str = "", radius: str = "10000") -> str:
        terms: List[str] = []
        if keyword:
            terms.append(keyword)
        if location:
            terms.append(location)
        query = " ".join(terms).strip() or keyword
        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.google.com/maps/search/{encoded}/?hl=en&gl=us"
        if radius and radius.isdigit() and radius != "10000":
            url = f"{url}&radius={radius}"
        return url

    def handle_google_maps_ui(self) -> None:
        button_candidates = [
            "button[aria-label*='Accept']",
            "button[aria-label*='I agree']",
            "button[jsaction*='consent']",
            "button[aria-label*='Close']",
            "button[aria-label*='No thanks']",
        ]
        for selector in button_candidates:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements[:2]:
                    if element.is_displayed() and element.is_enabled():
                        element.click()
                        time.sleep(0.5)
            except Exception:
                continue

    def _find_results_panel(self):
        panel_selectors = [
            "div[role='feed']",
            "div.m6QErb.DxyBCb",
            "div.m6QErb[aria-label*='Results']",
            "div[aria-label*='Results']",
        ]
        for selector in panel_selectors:
            try:
                return self.driver.find_element(By.CSS_SELECTOR, selector)
            except Exception:
                continue
        return None

    def _collect_cards(self):
        card_selectors = [
            "div[role='article']",
            "div.Nv2PK",
            "a.hfpxzc",
            "div[jsaction*='pane.result']",
        ]
        for selector in card_selectors:
            cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
            if cards:
                return cards
        return []

    def scroll_results_enhanced(self) -> None:
        panel = self._find_results_panel()
        if panel is None:
            logger.warning("Could not find results panel for scrolling")
            return

        stagnant_rounds = 0
        last_count = 0

        for _ in range(45):
            self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", panel)
            time.sleep(self.scroll_pause)

            current_cards = self._collect_cards()
            current_count = len(current_cards)

            if current_count >= self.max_results:
                return

            if current_count == last_count:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0

            if stagnant_rounds >= 6:
                return

            last_count = current_count

    def _extract_contact_info(self) -> Dict[str, str]:
        info = {"phone": "", "website": "", "email": "", "social_media": ""}

        phone_selectors = [
            "button[data-item-id*='phone']",
            "a[href^='tel:']",
            "button[aria-label*='Phone']",
            "button[aria-label*='phone']",
        ]
        for selector in phone_selectors:
            try:
                for elem in self.driver.find_elements(By.CSS_SELECTOR, selector):
                    text = (elem.text or elem.get_attribute("aria-label") or elem.get_attribute("href") or "").strip()
                    if text.startswith("tel:"):
                        text = text[4:]
                    if text and self.phone_pattern.search(text):
                        info["phone"] = text
                        break
                if info["phone"]:
                    break
            except Exception:
                continue

        website_selectors = [
            "a[data-item-id*='authority']",
            "a[data-item-id*='website']",
            "a[href^='http']",
        ]
        for selector in website_selectors:
            try:
                for elem in self.driver.find_elements(By.CSS_SELECTOR, selector):
                    href = (elem.get_attribute("href") or "").strip()
                    if href and "google.com/maps" not in href and self.website_pattern.match(href):
                        info["website"] = href
                        break
                if info["website"]:
                    break
            except Exception:
                continue

        try:
            text_blob = self.driver.page_source or ""
            email_match = self.email_pattern.search(text_blob)
            if email_match:
                info["email"] = email_match.group(0)
        except Exception:
            pass

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

        address_selectors = [
            "button[data-item-id*='address']",
            "button[aria-label*='Address']",
            "button[aria-label*='address']",
            "div[data-item-id*='address']",
        ]

        address_text = ""
        for selector in address_selectors:
            try:
                for elem in self.driver.find_elements(By.CSS_SELECTOR, selector):
                    candidate = (elem.text or elem.get_attribute("aria-label") or "").strip()
                    if candidate and len(candidate) > 8:
                        address_text = candidate
                        break
                if address_text:
                    break
            except Exception:
                continue

        if address_text:
            info["address"] = address_text
            postal = self.postal_pattern.search(address_text)
            if postal:
                info["postal_code"] = postal.group(0)
            for country in ALL_COUNTRIES:
                if country.lower() in address_text.lower():
                    info["country"] = country
                    break

        return info

    def extract_basic_card_info(self, card) -> Dict[str, object]:
        info: Dict[str, object] = {
            "name": "",
            "rating": 0.0,
            "reviews_count": 0,
            "category": "",
            "address": "",
        }

        name_selectors = [
            ".fontHeadlineSmall",
            ".qBF1Pd",
            "[role='heading']",
        ]
        for selector in name_selectors:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                text = (elem.text or "").strip()
                if text:
                    info["name"] = text
                    break
            except Exception:
                continue

        if not info["name"]:
            try:
                text_lines = [line.strip() for line in (card.text or "").splitlines() if line.strip()]
                if text_lines:
                    info["name"] = text_lines[0]
            except Exception:
                pass

        try:
            rating_el = card.find_element(By.CSS_SELECTOR, "span[aria-label*='star'], span.MW4etd")
            rating_text = (rating_el.get_attribute("aria-label") or rating_el.text or "").strip()
            rating_match = re.search(r"(\d+(?:\.\d+)?)", rating_text)
            if rating_match:
                info["rating"] = float(rating_match.group(1))
            reviews_match = re.search(r"(\d[\d,]*)", rating_text)
            if reviews_match:
                info["reviews_count"] = int(reviews_match.group(1).replace(",", ""))
        except Exception:
            pass

        try:
            category_el = card.find_element(By.CSS_SELECTOR, "div.W4Efsd, div.fontBodyMedium")
            category_text = (category_el.text or "").strip()
            if category_text:
                info["category"] = category_text.split("\n", 1)[0].strip()
        except Exception:
            pass

        return info

    def _open_card(self, card) -> bool:
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
            time.sleep(0.3)
            card.click()
            WebDriverWait(self.driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1, h1.DUwDvf, button[data-item-id*='address']"))
            )
            return True
        except Exception:
            return False

    def _close_details(self) -> None:
        close_selectors = [
            "button[aria-label*='Back']",
            "button[aria-label*='Close']",
            "button[jsaction*='pane.back']",
        ]
        for selector in close_selectors:
            try:
                btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                btn.click()
                time.sleep(0.5)
                return
            except Exception:
                continue
        try:
            self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            time.sleep(0.5)
        except Exception:
            pass

    def extract_coordinates_from_url(self, url: str) -> Tuple[str, str]:
        patterns = [
            r"@(-?\d+\.\d+),(-?\d+\.\d+)",
            r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1), match.group(2)
        return "", ""

    def extract_place_id(self, url: str) -> str:
        patterns = [
            r"!1s([^!]+)",
            r"cid=([^&]+)",
            r"place/([^/@]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return ""

    def scrape_business_card(self, card, index: int, location_info: Dict[str, str]) -> Optional[Dict[str, object]]:
        data = BusinessData()
        card_info = self.extract_basic_card_info(card)
        if not card_info.get("name"):
            return None

        for key, value in card_info.items():
            if hasattr(data, key) and value is not None:
                setattr(data, key, value)

        if location_info.get("country"):
            data.country = location_info["country"]
        if location_info.get("city"):
            data.city = location_info["city"]
        if location_info.get("state_province"):
            data.state_province = location_info["state_province"]

        extraction_sources = ["maps_card", "location_input"]

        if self._open_card(card):
            current_url = self.driver.current_url or ""
            data.source_url = current_url
            lat, lng = self.extract_coordinates_from_url(current_url)
            data.latitude = lat
            data.longitude = lng
            data.place_id = self.extract_place_id(current_url)

            details = self._extract_contact_info()
            address = self._extract_address_info()
            details.update(address)

            for key, value in details.items():
                if hasattr(data, key) and value:
                    setattr(data, key, value)

            extraction_sources.append("maps_detail")
            self._close_details()

        data.scraped_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data.extraction_sources = "|".join(extraction_sources)
        return asdict(data)

    def scrape(self, keyword: str, location: str = "", radius: str = "10000", max_results: int = None, progress_callback=None):
        if max_results:
            self.max_results = max_results

        location_info = self.determine_location_from_input(location)
        results: List[Dict[str, object]] = []

        self.setup_driver()

        try:
            url = self.build_search_url(keyword, location, radius)
            logger.info("Searching URL: %s", url)
            self.driver.get(url)
            time.sleep(3)

            self.handle_google_maps_ui()
            self.scroll_results_enhanced()

            total_attempted = 0
            while len(results) < self.max_results:
                cards = self._collect_cards()
                if not cards:
                    break

                if total_attempted >= len(cards):
                    break

                card = cards[total_attempted]
                total_attempted += 1

                try:
                    business = self.scrape_business_card(card, total_attempted, location_info)
                    if business:
                        results.append(business)
                        if progress_callback:
                            progress_callback(len(results), f"Scraped {len(results)} businesses...")
                    self.human_like_delay()
                except Exception as exc:
                    logger.debug("Failed to parse card %s: %s", total_attempted, exc)
                    continue

            return results
        finally:
            try:
                self.driver.quit()
            except Exception:
                pass

    def generate_filename(self, keyword: str, location: str = "") -> str:
        clean_keyword = re.sub(r"[^\w\s]", "", (keyword or "").lower())
        clean_keyword = "_".join(clean_keyword.split()[:3]) or "search"

        location_info = self.determine_location_from_input(location)
        location_parts = []
        if location_info.get("city"):
            location_parts.append(re.sub(r"[^\w\s]", "", location_info["city"].lower()).replace(" ", "_"))
        if location_info.get("country"):
            location_parts.append(re.sub(r"[^\w\s]", "", location_info["country"].lower()).replace(" ", "_"))

        suffix = "_".join([part for part in location_parts if part]) if location_parts else "worldwide"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs("results", exist_ok=True)
        return f"results/{clean_keyword}_{suffix}_{timestamp}"

    def save_to_excel(self, data: List[Dict[str, object]], filename: str = None):
        if not data:
            logger.warning("No data to save")
            return None

        if not filename:
            filename = f"results/google_maps_scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        df = pd.DataFrame(data)
        ordered_cols = [
            "name",
            "category",
            "address",
            "country",
            "city",
            "state_province",
            "street",
            "postal_code",
            "phone",
            "email",
            "website",
            "social_media",
            "rating",
            "reviews_count",
            "business_hours",
            "description",
            "latitude",
            "longitude",
            "place_id",
            "source_url",
            "scraped_date",
            "extraction_sources",
        ]

        existing = [col for col in ordered_cols if col in df.columns]
        extras = [col for col in df.columns if col not in existing]
        df = df[existing + extras]

        df.to_excel(filename, index=False)
        csv_name = filename.replace(".xlsx", ".csv")
        df.to_csv(csv_name, index=False, encoding="utf-8-sig")
        logger.info("Saved %s rows to %s", len(df), filename)
        return df


if __name__ == "__main__":
    scraper = UniversalGoogleMapsScraper(headless=False, max_results=100)
    rows = scraper.scrape(keyword="restaurants", location="Casablanca, Morocco", radius="10000", max_results=25)
    if rows:
        file_name = scraper.generate_filename("restaurants", "Casablanca, Morocco") + ".xlsx"
        scraper.save_to_excel(rows, file_name)
        print(f"Saved {len(rows)} rows to {file_name}")
    else:
        print("No rows scraped")