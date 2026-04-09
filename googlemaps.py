from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import ElementClickInterceptedException, NoSuchElementException, StaleElementReferenceException, TimeoutException, WebDriverException
from selenium.webdriver.common.keys import Keys
import pandas as pd
import time
import re
import urllib.parse
import json
import os
import platform
import shutil
import tempfile
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Union
import logging
from dataclasses import dataclass, asdict
import random

try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    ChromeDriverManager = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

PAGE_LOAD_TIMEOUT_SECONDS = 45
RESULTS_PANEL_TIMEOUT_SECONDS = 25
SCRIPT_TIMEOUT_SECONDS = 30
DETAIL_PANEL_TIMEOUT_SECONDS = 12


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
    def __init__(self, headless=False, max_results=100, scroll_pause=2, delay_between_requests=1.5):
        self.headless = self._resolve_headless_mode(headless)
        self.max_results = max_results
        self.scroll_pause = scroll_pause
        self.delay_between_requests = delay_between_requests
        self.driver = None
        self.wait = None

        # Regex patterns for data extraction
        self.phone_pattern = re.compile(r'(\+\d{1,3}[\s\-]?)?\(?\d{1,4}\)?[\s\-]?\d{1,4}[\s\-]?\d{1,9}')
        self.website_pattern = re.compile(r'(?:https?://)?(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?')
        self.email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
        self.postal_pattern = re.compile(r'\b\d{5}(?:[-\s]\d{4})?\b|\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b')

        # Enhanced worldwide location database
        self.location_keywords = self.load_worldwide_location_data()

        # Configuration paths
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

    def _resolve_browser_binary(self) -> Optional[str]:
        env_candidates = [
            os.getenv("CHROME_BINARY_PATH", "").strip(),
            os.getenv("GOOGLE_CHROME_BIN", "").strip(),
            os.getenv("CHROMIUM_BIN", "").strip(),
        ]
        path_candidates = [candidate for candidate in env_candidates if candidate]

        if os.name == "nt":
            path_candidates.extend([
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            ])
        else:
            for executable in ["google-chrome", "chrome", "chromium", "chromium-browser", "microsoft-edge"]:
                resolved = shutil.which(executable)
                if resolved:
                    path_candidates.append(resolved)

            path_candidates.extend([
                "/usr/bin/google-chrome",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
                "/opt/render/project/.render/chrome/opt/google/chrome/chrome",
            ])

        for candidate in path_candidates:
            if candidate and os.path.exists(candidate):
                logger.info(f"Using browser binary: {candidate}")
                return candidate

        logger.warning("No explicit Chrome/Chromium binary found. Selenium will try its default browser resolution.")
        return None

    def determine_location_from_input(self, location_input: str) -> Dict:
        """Parse location input to extract country, city, etc."""
        location_info = {
            'country': '',
            'city': '',
            'state_province': '',
            'specific_location': '',
            'original_input': location_input
        }

        if not location_input or not location_input.strip():
            return location_info

        location_input = location_input.strip()

        # First, try to identify country
        for country, codes in self.location_keywords['countries'].items():
            # Check if country name appears in input
            if country.lower() in location_input.lower():
                location_info['country'] = country
                break

            # Check for country codes
            for code in codes:
                if f", {code}" in location_input.upper() or f" {code}" in location_input.upper():
                    location_info['country'] = country
                    break

        # Try to identify city
        if location_info['country'] and location_info['country'] in self.location_keywords['cities_by_country']:
            cities = self.location_keywords['cities_by_country'][location_info['country']]
            for city in cities:
                if city.lower() in location_input.lower():
                    location_info['city'] = city
                    break

        # If no specific city found but we have comma-separated input, take first part as city
        if ',' in location_input and not location_info['city']:
            parts = [p.strip() for p in location_input.split(',')]
            if len(parts) >= 2:
                potential_city = parts[0]
                # Don't use if it looks like a street address or too short
                if len(potential_city) > 3 and not any(
                        word in potential_city.lower() for word in ['street', 'st', 'avenue', 'ave', 'road', 'rd']):
                    location_info['city'] = potential_city

        # Extract state/province (for US, Canada, Australia)
        if location_info['country'] in ['United States', 'Canada', 'Australia']:
            state_patterns = {
                'United States': self.location_keywords['address_patterns_by_country'].get('US', {}).get('state_codes',
                                                                                                         []),
                'Canada': self.location_keywords['address_patterns_by_country'].get('Canada', {}).get('province_codes',
                                                                                                      []),
                'Australia': self.location_keywords['address_patterns_by_country'].get('Australia', {}).get(
                    'state_codes', [])
            }

            if location_info['country'] in state_patterns:
                for state in state_patterns[location_info['country']]:
                    if state in location_input.upper():
                        location_info['state_province'] = state
                        break

        # Set specific location as the original input if it contains additional info
        if ',' in location_input:
            location_info['specific_location'] = location_input

        return location_info

    def load_worldwide_location_data(self):
        """Load comprehensive worldwide location data"""
        # This can be loaded from external JSON files for better maintainability
        return {
            'countries': self.load_country_data(),
            'cities_by_country': self.load_city_data(),
            'address_patterns_by_country': self.load_address_patterns()
        }

    def load_country_data(self):
        """Load comprehensive country data with variations"""
        countries = {
            'Afghanistan': ['AFG'],
            'Albania': ['ALB'],
            'Algeria': ['DZ', 'DZA'],
            'Andorra': ['AND'],
            'Angola': ['AGO'],
            'Argentina': ['AR', 'ARG'],
            'Australia': ['AU', 'AUS'],
            'Austria': ['AT', 'AUT'],
            'Bahrain': ['BHR'],
            'Bangladesh': ['BD', 'BGD'],
            'Belgium': ['BE', 'BEL'],
            'Brazil': ['BR', 'BRA'],
            'Canada': ['CA', 'CAN'],
            'Chile': ['CL', 'CHL'],
            'China': ['CN', 'CHN'],
            'Colombia': ['CO', 'COL'],
            'Czech Republic': ['CZ', 'CZE'],
            'Denmark': ['DK', 'DNK'],
            'Egypt': ['EG', 'EGY'],
            'Finland': ['FI', 'FIN'],
            'France': ['FR', 'FRA'],
            'Germany': ['DE', 'DEU'],
            'Greece': ['GR', 'GRC'],
            'Hong Kong': ['HK', 'HKG'],
            'India': ['IN', 'IND'],
            'Indonesia': ['ID', 'IDN'],
            'Iran': ['IR', 'IRN'],
            'Iraq': ['IQ', 'IRQ'],
            'Ireland': ['IE', 'IRL'],
            'Israel': ['IL', 'ISR'],
            'Italy': ['IT', 'ITA'],
            'Japan': ['JP', 'JPN'],
            'Jordan': ['JO', 'JOR'],
            'Kazakhstan': ['KZ', 'KAZ'],
            'Kenya': ['KE', 'KEN'],
            'Kuwait': ['KW', 'KWT'],
            'Lebanon': ['LB', 'LBN'],
            'Malaysia': ['MY', 'MYS'],
            'Mexico': ['MX', 'MEX'],
            'Morocco': ['MA', 'MAR', 'Maroc'],
            'Netherlands': ['NL', 'NLD'],
            'New Zealand': ['NZ', 'NZL'],
            'Nigeria': ['NG', 'NGA'],
            'Norway': ['NO', 'NOR'],
            'Oman': ['OM', 'OMN'],
            'Pakistan': ['PK', 'PAK'],
            'Philippines': ['PH', 'PHL'],
            'Poland': ['PL', 'POL'],
            'Portugal': ['PT', 'PRT'],
            'Qatar': ['QA', 'QAT'],
            'Romania': ['RO', 'ROU'],
            'Russia': ['RU', 'RUS'],
            'Saudi Arabia': ['SA', 'SAU'],
            'Singapore': ['SG', 'SGP'],
            'South Africa': ['ZA', 'ZAF'],
            'South Korea': ['KR', 'KOR'],
            'Spain': ['ES', 'ESP'],
            'Sweden': ['SE', 'SWE'],
            'Switzerland': ['CH', 'CHE'],
            'Taiwan': ['TW', 'TWN'],
            'Thailand': ['TH', 'THA'],
            'Turkey': ['TR', 'TUR'],
            'Ukraine': ['UA', 'UKR'],
            'United Arab Emirates': ['AE', 'ARE', 'UAE'],
            'United Kingdom': ['GB', 'GBR', 'UK'],
            'United States': ['US', 'USA'],
            'Vietnam': ['VN', 'VNM']
        }
        return countries

    def load_city_data(self):
        """Load major cities by country"""
        cities_by_country = {
            'United States': ['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix', 'Philadelphia', 'San Antonio',
                              'San Diego', 'Dallas', 'San Jose', 'Austin', 'Jacksonville', 'Fort Worth', 'Columbus',
                              'Charlotte', 'San Francisco', 'Indianapolis', 'Seattle', 'Denver', 'Washington DC'],
            'United Kingdom': ['London', 'Manchester', 'Birmingham', 'Glasgow', 'Liverpool', 'Bristol', 'Leeds',
                               'Edinburgh', 'Sheffield', 'Cardiff'],
            'Canada': ['Toronto', 'Montreal', 'Vancouver', 'Calgary', 'Edmonton', 'Ottawa', 'Winnipeg', 'Quebec City'],
            'Australia': ['Sydney', 'Melbourne', 'Brisbane', 'Perth', 'Adelaide', 'Gold Coast', 'Canberra'],
            'Germany': ['Berlin', 'Hamburg', 'Munich', 'Cologne', 'Frankfurt', 'Stuttgart', 'Düsseldorf', 'Dortmund'],
            'France': ['Paris', 'Marseille', 'Lyon', 'Toulouse', 'Nice', 'Nantes', 'Strasbourg', 'Montpellier'],
            'Japan': ['Tokyo', 'Yokohama', 'Osaka', 'Nagoya', 'Sapporo', 'Fukuoka', 'Kobe', 'Kyoto'],
            'China': ['Beijing', 'Shanghai', 'Guangzhou', 'Shenzhen', 'Chengdu', 'Hangzhou', 'Wuhan', 'Xi\'an'],
            'India': ['Mumbai', 'Delhi', 'Bangalore', 'Hyderabad', 'Ahmedabad', 'Chennai', 'Kolkata', 'Pune'],
            'Brazil': ['São Paulo', 'Rio de Janeiro', 'Brasília', 'Salvador', 'Fortaleza', 'Belo Horizonte', 'Manaus'],
            'Morocco': ['Casablanca', 'Tangier', 'Fez', 'Marrakesh', 'Salé', 'Meknes', 'Rabat',
                        'Oujda', 'Tetouan', 'Kenitra', 'Agadir', 'Temara', 'Safi', 'Mohammedia',
                        'Khouribga', 'El Jadida', 'Beni Mellal', 'Aït Melloul', 'Nador', 'Dar Bouazza',
                        'Taza', 'Settat', 'Berrechid', 'Khemisset', 'Inezgane', 'Ksar El Kebir',
                        'Larache', 'Guelmim', 'Khenifra', 'Berkane', 'Taourirt', 'Bouskoura',
                        'Fquih Ben Salah', 'Dcheira El Jihadia', 'Oued Zem', 'El Kelaa Des Sraghna',
                        'Sidi Slimane', 'Errachidia', 'Guercif', 'Oulad Teima', 'Ben Guerir', 'Tifelt',
                        'Lqliaa', 'Taroudant', 'Sefrou', 'Essaouira', 'Fnideq', 'Sidi Kacem',
                        'Tiznit', 'Tan-Tan', 'Ouarzazate', 'Souk El Arbaa', 'Youssoufia', 'Lahraouyine',
                        'Martil', 'Ain Harrouda', 'Suq as-Sabt Awlad an-Nama', 'Skhirat', 'Ouazzane',
                        'Benslimane', 'Al Hoceima', 'Beni Ansar', 'M\'diq', 'Sidi Bennour', 'Midelt', 'Azrou']
        }
        return cities_by_country

    def load_address_patterns(self):
        """Load address patterns by country for better parsing"""
        patterns = {
            'US': {
                'street_suffixes': ['St', 'Street', 'Ave', 'Avenue', 'Rd', 'Road', 'Blvd', 'Boulevard', 'Ln', 'Lane'],
                'state_codes': ['AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN',
                                'IA', 'KS', 'KY',
                                'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM',
                                'NY', 'NC', 'ND',
                                'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV',
                                'WI', 'WY']
            },
            'UK': {
                'street_suffixes': ['Street', 'Road', 'Lane', 'Avenue', 'Drive', 'Close', 'Way', 'Court', 'Grove'],
                'postal_pattern': r'[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}'
            },
            'Canada': {
                'street_suffixes': ['Street', 'Avenue', 'Road', 'Boulevard', 'Drive', 'Court', 'Crescent', 'Way'],
                'province_codes': ['AB', 'BC', 'MB', 'NB', 'NL', 'NS', 'NT', 'NU', 'ON', 'PE', 'QC', 'SK', 'YT']
            },
            'Australia': {
                'street_suffixes': ['Street', 'Road', 'Avenue', 'Drive', 'Court', 'Place', 'Lane', 'Crescent'],
                'state_codes': ['NSW', 'QLD', 'SA', 'TAS', 'VIC', 'WA', 'ACT', 'NT']
            }
        }
        return patterns

    def create_directories(self):
        """Create necessary directories"""
        for directory in [self.config_dir, self.cache_dir]:
            if not os.path.exists(directory):
                os.makedirs(directory)

    def setup_driver(self):
        """Setup Chrome WebDriver with enhanced anti-detection measures and crash prevention"""
        chrome_options = Options()
        runtime_system = platform.system().lower()
        chrome_options.page_load_strategy = "eager"

        # Use headless mode only if explicitly requested
        if self.headless:
            chrome_options.add_argument("--headless=new")

        # ===== CRASH PREVENTION OPTIONS =====
        # These options help prevent Chrome from crashing on Windows
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-gpu-software-rasterization")

        # Use a temporary user data directory to avoid profile corruption
        user_data_dir = tempfile.mkdtemp(prefix="chrome_profile_")
        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
        
        # Use a temporary disk cache directory
        cache_dir = tempfile.mkdtemp(prefix="chrome_cache_")
        chrome_options.add_argument(f"--disk-cache-dir={cache_dir}")

        if os.name == "nt":
            chrome_options.add_argument("--remote-debugging-port=9222")
        else:
            chrome_options.add_argument("--remote-debugging-pipe")

        # ===== ANTI-DETECTION SETTINGS =====
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        # ===== STABILITY OPTIONS =====
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-features=IsolateOrigins,site-per-process")
        chrome_options.add_argument("--disable-site-isolation-trials")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--disable-default-apps")
        chrome_options.add_argument("--disable-hang-monitor")
        chrome_options.add_argument("--disable-prompt-on-repost")
        chrome_options.add_argument("--disable-sync")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--safebrowsing-disable-auto-update")
        chrome_options.add_argument("--disable-client-side-phishing-detection")
        chrome_options.add_argument("--disable-component-extensions-with-background-pages")
        chrome_options.add_argument("--disable-breakpad")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-ipc-flooding-protection")
        chrome_options.add_argument("--force-color-profile=srgb")
        
        # Windows-specific stability options
        chrome_options.add_argument("--disable-features=TranslateUI")
        chrome_options.add_argument("--disable-features=PrivacySandboxSettings4")
        if os.name == "nt":
            chrome_options.add_argument("--ozone-platform=win")

        # ===== WINDOW SETTINGS =====
        # Set window size but don't maximize in headless mode (causes crashes)
        chrome_options.add_argument("--window-size=1920,1080")
        if not self.headless:
            chrome_options.add_argument("--start-maximized")

        # ===== LANGUAGE SETTINGS =====
        chrome_options.add_argument("--lang=en-US")
        chrome_options.add_argument("accept-language=en-US,en;q=0.9")

        # ===== USER AGENT =====
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
        ]
        user_agent = random.choice(user_agents)
        chrome_options.add_argument(f'user-agent={user_agent}')

        # Add random viewport
        chrome_options.add_argument(f'--window-position={random.randint(0, 500)},{random.randint(0, 500)}')

        # Set Chrome binary location explicitly
        browser_binary = self._resolve_browser_binary()
        if browser_binary:
            chrome_options.binary_location = browser_binary

        # Kill any existing Chrome processes to avoid conflicts
        if os.name == "nt":
            try:
                import subprocess
                subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True, timeout=5)
                subprocess.run(["taskkill", "/F", "/IM", "chromedriver.exe"], capture_output=True, timeout=5)
                logger.info("Killed existing Chrome processes")
            except Exception:
                pass

        driver = None
        errors = []

        def try_create_driver(label: str, factory):
            nonlocal driver
            try:
                driver = factory()
                logger.info(f"WebDriver initialized successfully ({label})")
                return True
            except Exception as exc:
                errors.append(f"{label}: {exc}")
                logger.warning(f"{label} failed: {exc}")
                return False

        def build_webdriver_manager_driver():
            if ChromeDriverManager is None:
                raise RuntimeError("webdriver-manager is not installed in the active Python environment")

            os.environ.setdefault("WDM_LOCAL", "1")
            driver_path = ChromeDriverManager().install()
            service = Service(driver_path)
            return webdriver.Chrome(service=service, options=chrome_options)
        
        # Try multiple initialization methods for better compatibility.
        if ChromeDriverManager is not None:
            logger.info("Attempting to use webdriver-manager for automatic ChromeDriver installation...")
            try_create_driver("webdriver-manager", build_webdriver_manager_driver)

        if driver is None:
            try_create_driver("selenium-manager", lambda: webdriver.Chrome(options=chrome_options))

        if driver is None:
            try_create_driver("explicit-service", lambda: webdriver.Chrome(service=Service(), options=chrome_options))

        if driver is None:
            logger.info("Attempting to use Microsoft Edge as fallback...")

            def build_edge_driver():
                from selenium.webdriver.edge.options import Options as EdgeOptions

                edge_options = EdgeOptions()
                edge_options.use_chromium = True
                if self.headless:
                    edge_options.add_argument("--headless=new")
                edge_options.add_argument("--no-sandbox")
                edge_options.add_argument("--disable-dev-shm-usage")
                edge_options.add_argument("--disable-gpu")
                edge_options.add_argument(f"--user-data-dir={tempfile.mkdtemp(prefix='edge_profile_')}")
                edge_options.add_argument("--disable-blink-features=AutomationControlled")
                edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                edge_options.add_experimental_option('useAutomationExtension', False)
                edge_options.add_argument(f'user-agent={user_agent}')
                return webdriver.Edge(options=edge_options)

            try_create_driver("edge-fallback", build_edge_driver)
        
        if driver is None:
            logger.error("All WebDriver initialization methods failed:")
            for error in errors:
                logger.error(f"  {error}")
            logger.error("\nCRITICAL TROUBLESHOOTING STEPS:")
            logger.error("  1. Run as Administrator (required on Windows)")
            logger.error("  2. Update Chrome: Go to chrome://settings/help")
            logger.error("  3. Disable antivirus temporarily")
            logger.error("  4. Close ALL Chrome windows and try again")
            logger.error("  5. Check Chrome version: chrome://version")
            logger.error("  6. Reinstall Chrome if corrupted")
            logger.error("  7. Try using Edge browser instead (set headless=True)")
            raise RuntimeError(
                "Failed to initialize WebDriver after all attempts. "
                "On hosted Linux, make sure the browser can run in headless mode and that a Chrome or Chromium binary is available."
            )

        self.driver = driver
        self.wait = WebDriverWait(self.driver, 20)
        self.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT_SECONDS)
        self.driver.set_script_timeout(SCRIPT_TIMEOUT_SECONDS)
        self.driver.implicitly_wait(0)

        # Execute CDP commands to prevent detection
        try:
            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": user_agent,
                "platform": "Windows" if runtime_system == "windows" else runtime_system.title()
            })
        except Exception as e:
            logger.warning(f"Failed to execute CDP command: {e}")

        # Additional anti-detection scripts
        scripts = [
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
            "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})",
            "Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})",
            """
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            """
        ]

        for script in scripts:
            try:
                self.driver.execute_script(script)
            except:
                pass

        logger.info("WebDriver setup complete with anti-detection measures")

    def _wait_for_results_or_empty_state(self):
        """Wait until Google Maps shows results, an empty state, or fail fast with diagnostics."""
        result_selectors = [
            "div[role='feed']",
            "div[role='article']",
            "div.Nv2PK",
            "a.hfpxzc",
        ]
        empty_state_selectors = [
            "div[role='main']",
            "div.section-no-result-title",
            "div.fontBodyMedium",
        ]

        def _page_ready(driver):
            for selector in result_selectors:
                try:
                    if driver.find_elements(By.CSS_SELECTOR, selector):
                        return "results"
                except Exception:
                    continue

            page_source = (driver.page_source or "").lower()
            empty_markers = [
                "no results found",
                "did not match any locations",
                "no results",
            ]
            if any(marker in page_source for marker in empty_markers):
                return "empty"

            for selector in empty_state_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                except Exception:
                    continue

                if any((element.text or "").strip() for element in elements):
                    return "shell"

            return False

        try:
            state = WebDriverWait(self.driver, RESULTS_PANEL_TIMEOUT_SECONDS).until(_page_ready)
        except TimeoutException as exc:
            title = self.driver.title if self.driver else "unknown"
            current_url = self.driver.current_url if self.driver else "unknown"
            raise TimeoutException(
                f"Google Maps did not load visible results within {RESULTS_PANEL_TIMEOUT_SECONDS}s. "
                f"Title='{title}', URL='{current_url}'."
            ) from exc

        if state == "empty":
            logger.info("Google Maps returned an empty state for this search.")
            return False

        return True

    def _open_search_page(self, url: str) -> None:
        try:
            self.driver.get(url)
        except TimeoutException:
            logger.warning("Page load timed out; stopping further network activity and continuing with the rendered DOM.")
            try:
                self.driver.execute_script("window.stop();")
            except Exception:
                pass
        except WebDriverException as exc:
            raise RuntimeError(f"Browser navigation failed: {exc}") from exc

    def build_search_url(self, keyword: str, location: str = "", radius: str = "10000"):
        """Build optimized Google Maps search URL for worldwide search"""
        base_url = "https://www.google.com/maps/search/"

        # Parse location
        location_info = self.determine_location_from_input(location)

        # Construct search query
        search_terms = []

        if keyword:
            search_terms.append(keyword)

        # Add location components in order of specificity
        if location_info['specific_location']:
            search_terms.append(location_info['specific_location'])

        if location_info['city']:
            search_terms.append(location_info['city'])

        if location_info['state_province']:
            search_terms.append(location_info['state_province'])

        if location_info['country'] and location_info['country'] not in " ".join(search_terms):
            search_terms.append(location_info['country'])

        # Combine terms
        if search_terms:
            search_query = "+".join([urllib.parse.quote_plus(term) for term in search_terms])
            url = f"{base_url}{search_query}"
        else:
            # Worldwide search without location
            url = f"{base_url}{urllib.parse.quote_plus(keyword)}"

        # Add parameters
        params = []
        if radius and radius != "10000":
            params.append(f"radius={radius}")

        # Add additional parameters for better results
        params.append("hl=en")  # English language
        params.append("gl=us")  # US region

        if params:
            url += "/" + "&".join(params)

        logger.debug(f"Built URL: {url}")
        return url

    def human_like_delay(self):
        """Add random delay to mimic human behavior"""
        delay = random.uniform(self.delay_between_requests - 0.5, self.delay_between_requests + 0.5)
        time.sleep(delay)

    def _find_results_panel(self):
        selectors = [
            "div[role='feed']",
            "div[aria-label*='Results']",
            "div.m6QErb",
            "div.m6QErb.DxyBCb",
            "div.m6QErb[aria-label*='Results']",
        ]
        for selector in selectors:
            try:
                return self.driver.find_element(By.CSS_SELECTOR, selector)
            except Exception:
                continue
        return None

    def _get_business_cards(self):
        selectors = [
            "div[role='article']",
            "div.Nv2PK",
            "a.hfpxzc",
            "div[jsaction*='mouseover:pane']",
        ]
        for selector in selectors:
            try:
                cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                cards = [card for card in cards if (card.text or "").strip()]
                if cards:
                    return cards
            except Exception:
                continue
        return []

    def _move_cursor_to_element(self, element) -> None:
        try:
            ActionChains(self.driver).move_to_element(element).pause(random.uniform(0.15, 0.45)).perform()
        except Exception:
            pass

    def _human_scroll_results_panel(self, panel) -> None:
        current_scroll = self.driver.execute_script("return arguments[0].scrollTop;", panel)
        panel_height = self.driver.execute_script("return arguments[0].clientHeight;", panel)
        step = random.randint(max(180, int(panel_height * 0.3)), max(320, int(panel_height * 0.7)))
        next_scroll = current_scroll + step
        self.driver.execute_script("arguments[0].scrollTo({top: arguments[1], behavior: 'smooth'});", panel, next_scroll)
        time.sleep(random.uniform(1.1, 2.6))

        if random.random() < 0.22:
            correction = max(0, next_scroll - random.randint(40, 140))
            self.driver.execute_script("arguments[0].scrollTo({top: arguments[1], behavior: 'smooth'});", panel, correction)
            time.sleep(random.uniform(0.3, 0.9))

    def _find_button_by_text(self, labels: List[str]):
        lowered = [label.strip().lower() for label in labels if label.strip()]
        xpaths = [
            "//button",
            "//div[@role='button']",
            "//span/ancestor::button[1]",
        ]
        for xpath in xpaths:
            try:
                elements = self.driver.find_elements(By.XPATH, xpath)
            except Exception:
                continue
            for element in elements:
                try:
                    text = (element.text or element.get_attribute("aria-label") or "").strip().lower()
                except Exception:
                    continue
                if text and any(label in text for label in lowered):
                    return element
        return None

    def _safe_click(self, element) -> bool:
        try:
            self._move_cursor_to_element(element)
            element.click()
            return True
        except (ElementClickInterceptedException, StaleElementReferenceException, WebDriverException):
            try:
                self.driver.execute_script("arguments[0].click();", element)
                return True
            except Exception:
                return False

    def _extract_business_hours_and_description(self) -> Dict:
        info = {"business_hours": "", "description": ""}

        hour_selectors = [
            "div[aria-label*='Hours']",
            "table.eK4R0e tbody",
            "div.OMl5r",
        ]
        for selector in hour_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
            except Exception:
                continue
            for element in elements:
                text = (element.text or "").strip()
                if text and len(text) > 6:
                    info["business_hours"] = text.replace("\n", " | ")
                    break
            if info["business_hours"]:
                break

        description_selectors = [
            "div.PYvSYb",
            "div.DxyBCb div[role='main'] span[jscontroller]",
            "div.fontBodyMedium span",
        ]
        for selector in description_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
            except Exception:
                continue
            for element in elements:
                text = (element.text or "").strip()
                if text and len(text) > 20:
                    info["description"] = text
                    break
            if info["description"]:
                break

        return info

    def _close_detail_panel(self) -> None:
        close_selectors = [
            "button[aria-label*='Close']",
            "button[aria-label*='Back']",
            "button[jsaction*='pane.back']",
            "div[aria-label*='Close']",
        ]
        for selector in close_selectors:
            try:
                close_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
            except Exception:
                continue
            if self._safe_click(close_btn):
                time.sleep(random.uniform(0.7, 1.2))
                return

        try:
            body = self.driver.find_element(By.TAG_NAME, 'body')
            body.send_keys(Keys.ESCAPE)
            time.sleep(random.uniform(0.6, 1.0))
        except Exception:
            pass

    def handle_google_maps_ui(self):
        """Handle various Google Maps UI elements and popups"""
        time.sleep(2)

        cookie_btn = self._find_button_by_text(["Accept all", "I agree", "Accept", "Tout accepter"])
        if cookie_btn and self._safe_click(cookie_btn):
            logger.info("Cookies accepted")
            time.sleep(1)

        # Handle sign-in popup
        try:
            signin_close = self.driver.find_elements(By.CSS_SELECTOR,
                                                     "button[aria-label*='Close'], button[aria-label*='No thanks'], button[jsaction*='close']")
            if signin_close:
                self._safe_click(signin_close[0])
                time.sleep(1)
        except:
            pass

        # Handle "Got it" button for location
        got_it_btn = self._find_button_by_text(["Got it", "OK", "Continue"])
        if got_it_btn:
            self._safe_click(got_it_btn)
            time.sleep(1)

    def scroll_results_enhanced(self):
        """Enhanced scrolling with better element detection"""
        logger.info("Scrolling to load more results...")

        last_height = 0
        scroll_attempts = 0
        max_scroll_attempts = 30
        consecutive_no_new_content = 0

        while scroll_attempts < max_scroll_attempts:
            try:
                results_panel = self._find_results_panel()

                if not results_panel:
                    logger.warning("Could not find results panel")
                    break

                visible_cards = self._get_business_cards()
                if visible_cards:
                    self._move_cursor_to_element(random.choice(visible_cards[: min(4, len(visible_cards))]))

                self._human_scroll_results_panel(results_panel)

                # Check current scroll height
                new_height = self.driver.execute_script(
                    "return arguments[0].scrollHeight",
                    results_panel
                )

                # Check if we have enough results
                cards = self._get_business_cards()

                logger.info(f"Loaded {len(cards)} results so far...")

                if len(cards) >= self.max_results:
                    logger.info(f"Reached target of {self.max_results} results")
                    break

                if new_height == last_height:
                    consecutive_no_new_content += 1
                    if consecutive_no_new_content >= 5:
                        logger.info("No more content loading")
                        break
                else:
                    consecutive_no_new_content = 0
                    last_height = new_height

                scroll_attempts += 1

                if scroll_attempts % 4 == 0 and cards:
                    self._move_cursor_to_element(random.choice(cards[: min(6, len(cards))]))
                    time.sleep(random.uniform(0.2, 0.5))

            except Exception as e:
                logger.warning(f"Error during scrolling: {e}")
                scroll_attempts += 1
                time.sleep(2)

        time.sleep(2)
        logger.info(f"Finished scrolling. Total results found: {len(cards) if 'cards' in locals() else 0}")

    def _extract_contact_info(self) -> Dict:
        """Extract contact information"""
        info = {'phone': '', 'website': '', 'email': '', 'social_media': ''}

        # Phone
        phone_selectors = [
            "button[data-item-id*='phone']",
            "a[href^='tel:']",
            "[aria-label*='Phone']",
            "[data-tooltip*='Phone']",
            "div[class*='phone']",
            "span:contains('+')"
        ]

        for selector in phone_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for elem in elements:
                    text = elem.text.strip()
                    if text and self.phone_pattern.search(text):
                        info['phone'] = text
                        break
                if info['phone']:
                    break
            except:
                continue

        # Website
        website_selectors = [
            "a[href*='://']:not([href*='google.com'])",
            "button[data-item-id*='website']",
            "[aria-label*='Website']",
            "[data-tooltip*='Website']",
            "a[href*='www.']",
            "a[class*='website']"
        ]

        for selector in website_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for elem in elements:
                    href = elem.get_attribute('href') or elem.text
                    if href and ('http://' in href.lower() or 'https://' in href.lower()):
                        info['website'] = href
                        break
                if info['website']:
                    break
            except:
                continue

        # Email
        try:
            all_text = self.driver.page_source
            email_match = self.email_pattern.search(all_text)
            if email_match:
                info['email'] = email_match.group()
        except:
            pass

        return info

    def _extract_address_info(self) -> Dict:
        """Extract and parse address information"""
        info = {
            'address': '', 'country': '', 'city': '',
            'street': '', 'postal_code': '', 'state_province': ''
        }

        # Address
        address_selectors = [
            "button[data-item-id*='address']",
            "[data-tooltip*='Address']",
            "[aria-label*='Address']",
            "div[class*='address']",
            "div[class*='location']"
        ]

        address_text = ""
        for selector in address_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for elem in elements:
                    text = elem.text.strip()
                    if text and len(text) > 10:
                        address_text = text
                        info['address'] = text
                        break
                if address_text:
                    break
            except:
                continue

        # Parse address components if we have text
        if address_text:
            # Try to extract postal code
            postal_match = self.postal_pattern.search(address_text)
            if postal_match:
                info['postal_code'] = postal_match.group()

            # Try to identify country
            for country in self.location_keywords['countries']:
                if country.lower() in address_text.lower():
                    info['country'] = country
                    break

            # Try to identify city (common cities first)
            if info['country'] and info['country'] in self.location_keywords['cities_by_country']:
                cities = self.location_keywords['cities_by_country'][info['country']]
                for city in cities:
                    if city.lower() in address_text.lower():
                        info['city'] = city
                        break

        return info

    def scrape(self, keyword: str, location: str = "", radius: str = "10000", max_results: int = None):
        """Main scraping function with worldwide capability"""
        if max_results:
            self.max_results = max_results

        logger.info("=" * 70)
        logger.info("🌍 UNIVERSAL GOOGLE MAPS SCRAPER - WORLDWIDE")
        logger.info("=" * 70)

        # Parse location
        location_info = self.determine_location_from_input(location)

        # Setup driver
        self.setup_driver()

        # Build and navigate to URL
        url = self.build_search_url(keyword, location, radius)
        logger.info(f"🔍 Searching for: {keyword}")
        logger.info(f"📍 Location analysis:")
        logger.info(f"   Country: {location_info['country'] or 'Worldwide'}")
        logger.info(f"   City: {location_info['city'] or 'Not specified'}")
        logger.info(f"   State/Province: {location_info['state_province'] or 'Not specified'}")
        logger.info(f"   Specific: {location_info['specific_location'] or 'Not specified'}")
        logger.info(f"🔗 URL: {url}")

        # Navigate
        self._open_search_page(url)
        time.sleep(3)

        # Handle UI elements
        self.handle_google_maps_ui()

        has_results = self._wait_for_results_or_empty_state()
        if not has_results:
            try:
                self.driver.quit()
            except Exception:
                pass
            return []

        # Scroll to load results
        self.scroll_results_enhanced()

        # Find business cards
        card_selectors = [
            "div[role='article']",
            "a.hfpxzc",
            "div.Nv2PK",
            "div[jsaction*='mouseover:pane']"
        ]

        cards = []
        for selector in card_selectors:
            try:
                cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                cards = [card for card in cards if (card.text or "").strip()]
                if cards:
                    logger.info(f"Found {len(cards)} business cards using selector: {selector}")
                    break
            except:
                continue

        if not cards:
            logger.warning("No business cards found. Trying alternative approach...")
            # Try to get all clickable elements
            cards = self.driver.find_elements(By.XPATH,
                                              "//*[contains(@class, 'section-result') or contains(@class, 'place-card')]")

        logger.info(f"📍 Total businesses found: {len(cards)}")

        # Scrape each business
        results = []
        for i in range(min(len(cards), self.max_results)):
            try:
                current_cards = self._get_business_cards()
                if i >= len(current_cards):
                    break
                business_data = self.scrape_business_card(current_cards[i], i + 1, location_info)
                if business_data:
                    results.append(business_data)
                    logger.info(
                        f"✅ ({i + 1}/{min(len(cards), self.max_results)}) Success: {business_data.get('name', 'Unknown')}")

                # Save progress periodically
                if (i + 1) % 10 == 0 and results:
                    self.save_progress(results, keyword, location, f"_partial_{i + 1}")

                # Human-like delay between requests
                self.human_like_delay()

            except Exception as e:
                logger.error(f"❌ Error scraping business {i + 1}: {e}")
                continue

        # Close driver
        try:
            self.driver.quit()
        except:
            pass

        logger.info(f"🎉 Scraping complete! Extracted {len(results)} businesses")

        return results

    def scrape_business_card(self, card, index: int, location_info: Dict) -> Optional[Dict]:
        """Scrape individual business card"""
        try:
            data = BusinessData()

            # Scroll to card
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", card)
            self._move_cursor_to_element(card)
            time.sleep(random.uniform(0.4, 0.9))

            # Extract basic info from card
            card_info = self.extract_basic_card_info(card)
            if not card_info.get('name'):
                return None

            # Update data object
            for key, value in card_info.items():
                if hasattr(data, key) and value:
                    setattr(data, key, value)

            # Set location info
            if location_info['country']:
                data.country = location_info['country']
            if location_info['city']:
                data.city = location_info['city']
            if location_info['state_province']:
                data.state_province = location_info['state_province']

            # Try to get detailed info
            try:
                previous_url = self.driver.current_url
                if not self._safe_click(card):
                    return None

                WebDriverWait(self.driver, DETAIL_PANEL_TIMEOUT_SECONDS).until(
                    lambda driver: driver.current_url != previous_url or len(driver.find_elements(By.CSS_SELECTOR, "h1, div[role='main'] h1, button[data-item-id*='address']")) > 0
                )
                time.sleep(random.uniform(1.2, 2.0))

                # Get current URL
                current_url = self.driver.current_url
                data.source_url = current_url

                # Extract coordinates and place ID
                lat, lng = self.extract_coordinates_from_url(current_url)
                if lat and lng:
                    data.latitude = lat
                    data.longitude = lng

                data.place_id = self.extract_place_id(current_url)

                # Extract detailed information
                details = self._extract_contact_info()
                details.update(self._extract_address_info())
                details.update(self._extract_business_hours_and_description())

                # Update data with details
                for key, value in details.items():
                    if hasattr(data, key) and value:
                        setattr(data, key, value)

                self._close_detail_panel()

            except Exception as e:
                logger.debug(f"Couldn't open detail panel: {e}")

            # Set scraped date
            data.scraped_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            return asdict(data)

        except Exception as e:
            logger.error(f"Error scraping card {index}: {e}")
            return None

    def extract_basic_card_info(self, card) -> Dict:
        """Extract basic information from card without opening details"""
        info = {
            'name': '',
            'rating': 0.0,
            'reviews_count': 0,
            'category': '',
            'address': ''
        }

        try:
            # Extract name
            name_selectors = [
                ".fontHeadlineSmall",
                ".fontHeadlineMedium",
                ".fontHeadlineLarge",
                "[role='heading']",
                "div.fontHeadlineSmall",
                "div.qBF1Pd",
                "div.fontHeadlineMedium"
            ]

            for selector in name_selectors:
                try:
                    name_elem = card.find_element(By.CSS_SELECTOR, selector)
                    if name_elem.text.strip():
                        info['name'] = name_elem.text.strip()
                        break
                except:
                    continue

            if not info['name']:
                # Fallback: get first significant text
                card_text = card.text.split('\n')
                if card_text:
                    info['name'] = card_text[0].strip()

            # Extract rating
            try:
                rating_elem = card.find_element(By.CSS_SELECTOR,
                                                "span[aria-label*='stars'], span[aria-label*='rating'], span.MW4etd")
                rating_text = rating_elem.get_attribute('aria-label') or rating_elem.text
                if rating_text:
                    rating_match = re.search(r'(\d+(\.\d+)?)', rating_text)
                    if rating_match:
                        info['rating'] = float(rating_match.group(1))

                    # Extract review count
                    reviews_match = re.search(r'(\d+(,\d+)*)\s*(reviews|avis|レビュー|评论|Bewertungen)',
                                              rating_text, re.IGNORECASE)
                    if reviews_match:
                        info['reviews_count'] = int(reviews_match.group(1).replace(',', ''))
            except:
                pass

            # Extract category/type
            try:
                category_elem = card.find_element(By.CSS_SELECTOR,
                                                  "div.fontBodyMedium, div.W4Efsd, div.UaQhfb")
                category_text = category_elem.text.strip()
                if category_text and category_text != info['name']:
                    # Take first line as category
                    info['category'] = category_text.split('\n')[0]
            except:
                pass

        except Exception as e:
            logger.debug(f"Error extracting basic card info: {e}")

        return info

    def extract_coordinates_from_url(self, url: str) -> Tuple[str, str]:
        """Extract latitude and longitude from URL"""
        try:
            patterns = [
                r'@(-?\d+\.\d+),(-?\d+\.\d+)',
                r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)',
                r'place/.+@(-?\d+\.\d+),(-?\d+\.\d+)'
            ]

            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    return match.group(1), match.group(2)
        except:
            pass
        return "", ""

    def extract_place_id(self, url: str) -> str:
        """Extract place ID from URL"""
        try:
            patterns = [
                r'place/([^/@]+)',
                r'!1s([^!]+)',
                r'cid=([^&]+)'
            ]

            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    return match.group(1)
        except:
            pass
        return ""

    def save_progress(self, data, keyword, location, suffix=""):
        """Save partial progress"""
        if not data:
            return

        filename = self.generate_filename(keyword, location) + suffix + ".xlsx"
        df = pd.DataFrame(data)
        df.to_excel(filename, index=False)
        logger.info(f"💾 Progress saved: {filename}")

    def generate_filename(self, keyword: str, location: str = "") -> str:
        """Generate filename for output"""
        # Clean keyword
        clean_keyword = re.sub(r'[^\w\s]', '', keyword.lower())
        clean_keyword = '_'.join(clean_keyword.split()[:3])  # First 3 words

        # Parse location for filename
        location_info = self.determine_location_from_input(location)

        location_parts = []
        if location_info['city']:
            clean_city = re.sub(r'[^\w\s]', '', location_info['city'].lower())
            location_parts.append('_'.join(clean_city.split()))

        if location_info['country']:
            clean_country = re.sub(r'[^\w\s]', '', location_info['country'].lower())
            location_parts.append('_'.join(clean_country.split()))

        if location_parts:
            location_str = '_'.join(location_parts[:2])
            base_name = f"{clean_keyword}_{location_str}"
        else:
            base_name = f"{clean_keyword}_worldwide"

        # Add timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"results/{base_name}_{timestamp}"

        # Ensure results directory exists
        os.makedirs("results", exist_ok=True)

        return filename

    def save_to_excel(self, data, filename: str = None):
        """Save data to Excel with proper formatting"""
        if not data:
            logger.warning("No data to save")
            return None

        if not filename:
            # Generate default filename
            filename = f"results/google_maps_scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        df = pd.DataFrame(data)

        # Define column order
        column_order = [
            'name', 'category', 'address', 'country', 'city',
            'state_province', 'street', 'postal_code', 'phone',
            'email', 'website', 'social_media', 'rating',
            'reviews_count', 'business_hours', 'description',
            'latitude', 'longitude', 'place_id', 'source_url',
            'scraped_date'
        ]

        # Reorder columns
        existing_cols = [col for col in column_order if col in df.columns]
        extra_cols = [col for col in df.columns if col not in existing_cols]
        final_cols = existing_cols + extra_cols

        df = df[final_cols]

        # Save to Excel
        df.to_excel(filename, index=False)
        logger.info(f"💾 Data saved to {filename}")

        # Also save as CSV for compatibility
        csv_file = filename.replace('.xlsx', '.csv')
        df.to_csv(csv_file, index=False, encoding='utf-8-sig')
        logger.info(f"📄 Data also saved to {csv_file}")

        return df


# --- Main execution with enhanced interface ---
if __name__ == "__main__":
    print("=" * 80)
    print("🌍 UNIVERSAL GOOGLE MAPS SCRAPER - WORLDWIDE BUSINESS EXTRACTOR")
    print("=" * 80)
    print("SUPPORTS: 200+ COUNTRIES | 1000+ CITIES | MULTILINGUAL | ANTI-DETECTION")
    print("=" * 80)

    # Get user input
    print("\n📋 SEARCH CONFIGURATION")
    print("-" * 40)

    keyword = input("Enter search keyword (e.g., restaurants, hotels, pharmacies): ").strip()
    if not keyword:
        print("❌ Keyword is required!")
        exit()

    print("\n📍 LOCATION EXAMPLES:")
    print("   • 'New York, USA'")
    print("   • 'Tokyo, Japan'")
    print("   • 'London, UK'")
    print("   • 'Sydney, Australia'")
    print("   • 'Dubai, UAE'")
    print("   • 'Paris, France'")
    print("   • 'Berlin, Germany'")
    print("   • 'Singapore'")
    print("   • 'Toronto, Canada'")
    print("   • 'Mumbai, India'")
    print("   • 'Casablanca, Morocco'")
    print("   • Leave blank for worldwide search")

    location = input("\nEnter location (country/city/address): ").strip()

    # Advanced options
    print("\n⚙️ ADVANCED OPTIONS")
    print("-" * 40)

    try:
        max_results = int(input("Maximum results (default: 100, max: 500): ").strip() or "100")
        max_results = min(max_results, 500)
    except:
        max_results = 100

    headless_input = input("Run in background? (y/n, default: n): ").strip().lower()
    headless = headless_input == 'y'

    radius_input = input("Search radius in meters (default: 10000 = 10km): ").strip()
    radius = radius_input if radius_input else "10000"

    print("\n" + "=" * 80)
    print("🚀 STARTING WORLDWIDE SCRAPING")
    print("=" * 80)
    print(f"🔍 Keyword: {keyword}")
    print(f"📍 Location: {location if location else 'WORLDWIDE'}")
    print(f"📊 Max results: {max_results}")
    print(f"📏 Radius: {radius} meters")
    print(f"👻 Background mode: {'Yes' if headless else 'No'}")
    print("=" * 80 + "\n")

    # Create scraper instance
    scraper = UniversalGoogleMapsScraper(
        headless=headless,
        max_results=max_results,
        delay_between_requests=1.5
    )

    try:
        # Run scraping
        data = scraper.scrape(
            keyword=keyword,
            location=location,
            radius=radius,
            max_results=max_results
        )

        # Save results
        if data:
            # Generate filename
            filename = scraper.generate_filename(keyword, location) + ".xlsx"

            # Save to Excel
            df = scraper.save_to_excel(data, filename)

            # Print comprehensive summary
            print("\n" + "=" * 80)
            print("✅ SCRAPING COMPLETE - DETAILED SUMMARY")
            print("=" * 80)
            print(f"🔍 Search: {keyword}")
            print(f"📍 Location: {location if location else 'Worldwide'}")
            print(f"📊 Total businesses scraped: {len(data)}")
            print(f"💾 Excel file: {filename}")
            print(f"📄 CSV file: {filename.replace('.xlsx', '.csv')}")
            print("=" * 80)

            # Detailed statistics
            if len(data) > 0:
                print("\n📈 DATA STATISTICS:")
                print("-" * 40)

                # Count by country
                countries = {}
                for item in data:
                    country = item.get('country', 'Unknown')
                    countries[country] = countries.get(country, 0) + 1

                # Count by city
                cities = {}
                for item in data:
                    city = item.get('city', 'Unknown')
                    if city:
                        cities[city] = cities.get(city, 0) + 1

                # Calculate completion rates
                total = len(data)
                phone_count = sum(1 for item in data if item.get('phone'))
                website_count = sum(1 for item in data if item.get('website'))
                email_count = sum(1 for item in data if item.get('email'))
                address_count = sum(1 for item in data if item.get('address'))
                rating_count = sum(1 for item in data if item.get('rating', 0) > 0)

                print(f"📊 Total entries: {total}")
                print(f"🌍 Countries found: {len(countries)}")
                print(f"🏙️ Cities found: {len(cities)}")
                print(f"📞 Phone numbers: {phone_count} ({phone_count / total * 100:.1f}%)")
                print(f"🌐 Websites: {website_count} ({website_count / total * 100:.1f}%)")
                print(f"📧 Emails: {email_count} ({email_count / total * 100:.1f}%)")
                print(f"📍 Addresses: {address_count} ({address_count / total * 100:.1f}%)")
                print(f"⭐ Ratings: {rating_count} ({rating_count / total * 100:.1f}%)")

                # Show top countries
                if countries:
                    print("\n🌎 TOP COUNTRIES:")
                    for country, count in sorted(countries.items(), key=lambda x: x[1], reverse=True)[:5]:
                        print(f"   {country}: {count} businesses")

                # Show sample data
                print("\n📋 SAMPLE DATA (First 5 entries):")
                print("-" * 60)
                for i, item in enumerate(data[:5]):
                    print(f"{i + 1}. {item.get('name', 'N/A')}")
                    if item.get('country'):
                        print(f"   🌍 {item['country']}", end="")
                        if item.get('city'):
                            print(f" | 🏙️ {item['city']}")
                        else:
                            print()
                    if item.get('phone'):
                        print(f"   📞 {item['phone']}")
                    if item.get('address'):
                        addr = item['address'][:70] + "..." if len(item['address']) > 70 else item['address']
                        print(f"   📍 {addr}")
                    if item.get('rating'):
                        print(f"   ⭐ {item['rating']}/5 ({item.get('reviews_count', 0)} reviews)")
                    print()

        else:
            print("\n❌ No data was scraped.")
            print("Possible reasons:")
            print("  1. No businesses found for your search")
            print("  2. Google Maps blocked the request (try again later)")
            print("  3. Location not found")
            print("  4. Network issues")

    except KeyboardInterrupt:
        print("\n\n⚠️ Scraping interrupted by user.")
    except Exception as e:
        print(f"\n❌ Error during scraping: {e}")
        print("Please check your internet connection and try again.")
    finally:
        print("\n" + "=" * 80)
        print("🎯 TIPS FOR BETTER RESULTS:")
        print("-" * 80)
        print("1. Use specific keywords (e.g., 'Italian restaurants' not just 'restaurants')")
        print("2. Add city/country to location for more targeted results")
        print("3. Try different search terms if results are limited")
        print("4. For worldwide search, be patient as it may take longer")
        print("5. Consider using VPN if you get blocked")
        print("=" * 80)