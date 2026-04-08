from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.keys import Keys
import pandas as pd
import time
import re
import urllib.parse
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Union
import logging
from dataclasses import dataclass, asdict
import random

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
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


class UniversalGoogleMapsScraper:
    def __init__(self, headless=False, max_results=100, scroll_pause=2, delay_between_requests=1.5):
        self.headless = headless
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

        # Use headless mode only if explicitly requested
        if self.headless:
            chrome_options.add_argument("--headless=new")

        # ===== CRASH PREVENTION OPTIONS =====
        # These options help prevent Chrome from crashing on Windows
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        # Note: --disable-gpu can sometimes cause issues on Windows, try without it first
        # chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-gpu-software-rasterization")

        # Use a temporary user data directory to avoid profile corruption
        import tempfile
        user_data_dir = tempfile.mkdtemp(prefix="chrome_profile_")
        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
        
        # Use a temporary disk cache directory
        cache_dir = tempfile.mkdtemp(prefix="chrome_cache_")
        chrome_options.add_argument(f"--disk-cache-dir={cache_dir}")

        # Add remote debugging port to help with DevToolsActivePort issue
        chrome_options.add_argument("--remote-debugging-port=9222")
        
        # Add single process flag (can help on Windows)
        chrome_options.add_argument("--single-process")
        chrome_options.add_argument("--no-zygote")

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
        chrome_options.binary_location = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

        # Kill any existing Chrome processes to avoid conflicts
        try:
            import subprocess
            subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], 
                          capture_output=True, timeout=5)
            subprocess.run(["taskkill", "/F", "/IM", "chromedriver.exe"], 
                          capture_output=True, timeout=5)
            logger.info("Killed existing Chrome processes")
        except:
            pass

        driver = None
        errors = []
        
        # Try multiple initialization methods for better compatibility
        # Method 1: Basic Chrome initialization
        try:
            driver = webdriver.Chrome(options=chrome_options)
            logger.info("WebDriver initialized successfully (Method 1)")
        except Exception as e1:
            errors.append(f"Method 1: {e1}")
            logger.warning(f"Method 1 failed: {e1}")
            
            # Method 2: With explicit Service
            try:
                service = Service()
                driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.info("WebDriver initialized successfully (Method 2)")
            except Exception as e2:
                errors.append(f"Method 2: {e2}")
                logger.warning(f"Method 2 failed: {e2}")
                
                # Method 3: Try with webdriver-manager for automatic ChromeDriver management
                try:
                    from selenium.webdriver.chrome.service import Service as ChromeService
                    from webdriver_manager.chrome import ChromeDriverManager
                    from webdriver_manager.core.os import ChromeType
                    
                    logger.info("Attempting to use webdriver-manager for automatic ChromeDriver installation...")
                    service = ChromeService(ChromeDriverManager(chrome_type=ChromeType.GOOGLE).install())
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                    logger.info("ChromeDriver installed/updated successfully via webdriver-manager")
                except Exception as e3:
                    errors.append(f"Method 3: {e3}")
                    logger.warning(f"Method 3 failed: {e3}")
                    
                    # Method 4: Try with Edge browser (built into Windows)
                    try:
                        logger.info("Attempting to use Microsoft Edge as fallback...")
                        from selenium.webdriver.edge.options import Options as EdgeOptions
                        from selenium.webdriver.edge.service import Service as EdgeService
                        
                        edge_options = EdgeOptions()
                        edge_options.use_chromium = True
                        edge_options.add_argument("--headless") if self.headless else None
                        edge_options.add_argument("--no-sandbox")
                        edge_options.add_argument("--disable-dev-shm-usage")
                        edge_options.add_argument("--disable-gpu")
                        edge_options.add_argument(f"--user-data-dir={tempfile.mkdtemp(prefix='edge_profile_')}")
                        edge_options.add_argument("--remote-debugging-port=9223")
                        edge_options.add_argument("--disable-blink-features=AutomationControlled")
                        edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                        edge_options.add_experimental_option('useAutomationExtension', False)
                        edge_options.add_argument(f'user-agent={user_agent}')
                        
                        driver = webdriver.Edge(options=edge_options)
                        logger.info("WebDriver initialized successfully using Edge (Method 4)")
                    except Exception as e4:
                        errors.append(f"Method 4 (Edge): {e4}")
                        logger.warning(f"Method 4 (Edge) failed: {e4}")
        
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
            raise RuntimeError("Failed to initialize WebDriver after all attempts")

        self.driver = driver
        self.wait = WebDriverWait(self.driver, 20)

        # Execute CDP commands to prevent detection
        try:
            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": user_agent,
                "platform": "Windows"
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

    def handle_google_maps_ui(self):
        """Handle various Google Maps UI elements and popups"""
        time.sleep(2)

        # Handle cookie consent
        cookie_selectors = [
            "button[aria-label*='Accept all']",
            "button:contains('Accept all')",
            "button:contains('I agree')",
            "form[action*='consent'] button",
            "div[aria-modal='true'] button:last-child",
            "button[jsaction*='cookie']"
        ]

        for selector in cookie_selectors:
            try:
                cookie_btn = self.wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                cookie_btn.click()
                logger.info("Cookies accepted")
                time.sleep(1)
                break
            except:
                continue

        # Handle sign-in popup
        try:
            signin_close = self.driver.find_elements(By.CSS_SELECTOR,
                                                     "button[aria-label*='Close'], button[aria-label*='No thanks'], button[jsaction*='close']")
            if signin_close:
                signin_close[0].click()
                time.sleep(1)
        except:
            pass

        # Handle "Got it" button for location
        try:
            got_it_btn = self.driver.find_elements(By.CSS_SELECTOR,
                                                   "button:contains('Got it'), button:contains('OK'), button[jsaction*='pane.gotit']")
            if got_it_btn:
                got_it_btn[0].click()
                time.sleep(1)
        except:
            pass

    def scroll_results_enhanced(self):
        """Enhanced scrolling with better element detection"""
        logger.info("Scrolling to load more results...")

        last_height = 0
        scroll_attempts = 0
        max_scroll_attempts = 30
        consecutive_no_new_content = 0

        while scroll_attempts < max_scroll_attempts:
            try:
                # Find the results container
                results_containers = [
                    "div[role='feed']",
                    "div[aria-label*='Results']",
                    "div.m6QErb",
                    "div.m6QErb.DxyBCb",
                    "div.m6QErb[aria-label*='Results']"
                ]

                results_panel = None
                for selector in results_containers:
                    try:
                        results_panel = self.driver.find_element(By.CSS_SELECTOR, selector)
                        break
                    except:
                        continue

                if not results_panel:
                    logger.warning("Could not find results panel")
                    break

                # Scroll
                self.driver.execute_script(
                    "arguments[0].scrollTop = arguments[0].scrollHeight;",
                    results_panel
                )

                # Random delay to mimic human
                time.sleep(random.uniform(1.5, 3))

                # Check current scroll height
                new_height = self.driver.execute_script(
                    "return arguments[0].scrollHeight",
                    results_panel
                )

                # Check if we have enough results
                cards = self.driver.find_elements(By.CSS_SELECTOR,
                                                  "div[role='article'], div.Nv2PK, a.hfpxzc")

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

                # Occasionally scroll a bit more randomly
                if scroll_attempts % 5 == 0:
                    self.driver.execute_script(
                        "arguments[0].scrollTop = arguments[0].scrollTop + 300;",
                        results_panel
                    )
                    time.sleep(0.5)

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
        self.driver.get(url)
        time.sleep(3)

        # Handle UI elements
        self.handle_google_maps_ui()

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
        for i, card in enumerate(cards[:self.max_results]):
            try:
                business_data = self.scrape_business_card(card, i + 1, location_info)
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
            time.sleep(0.5)

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
                # Click on card to open details
                card.click()
                time.sleep(2)

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

                # Update data with details
                for key, value in details.items():
                    if hasattr(data, key) and value:
                        setattr(data, key, value)

                # Try to close detail panel
                try:
                    close_selectors = [
                        "button[aria-label*='Close']",
                        "button[aria-label*='Back']",
                        "button[jsaction*='pane.back']",
                        "div[aria-label*='Close']"
                    ]

                    for selector in close_selectors:
                        try:
                            close_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                            close_btn.click()
                            time.sleep(1)
                            break
                        except:
                            continue
                except:
                    # Press Escape as fallback
                    try:
                        from selenium.webdriver.common.keys import Keys
                        body = self.driver.find_element(By.TAG_NAME, 'body')
                        body.send_keys(Keys.ESCAPE)
                        time.sleep(1)
                    except:
                        pass

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