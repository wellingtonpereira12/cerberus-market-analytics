import os
import sys
import re
import json
import time
import logging
import ssl
import urllib.request
import urllib.parse
from datetime import datetime
from bs4 import BeautifulSoup

from scraper.database import CerberusDatabase

logger = logging.getLogger("cerberus_scraper")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BASE_URL = "https://cerberus-games.com"
MARKET_URL = "https://cerberus-games.com/market/items"
LOGIN_URL = "https://cerberus-games.com/login/login"

FORUM_SECTIONS = [
    {
        "id": "161",
        "name": "CERBERUS - FORCE & STEEL (New)",
        "url": "https://cerberus-games.com/forums/%D0%A0%D1%8B%D0%BD%D0%BE%D0%BA-marketplace.161/"
    },
    {
        "id": "144",
        "name": "CERBERUS - STAGE ERA",
        "url": "https://cerberus-games.com/forums/%D0%A0%D1%8B%D0%BD%D0%BE%D0%BA-marketplace.144/"
    }
]

SERVERS = [
    {"id": "1", "name": "CERBERUS - FORCE&STEEL"},
    {"id": "0", "name": "CERBERUS - STAGE ERA"}
]

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8,pt-BR;q=0.7',
    'Referer': 'https://cerberus-games.com/'
}

class CerberusScraper:
    def __init__(self, db=None, cookie=None, username=None, password=None):
        self.db = db or CerberusDatabase()
        self.cookie = cookie or os.getenv("CERBERUS_COOKIE")
        self.username = username or os.getenv("CERBERUS_USER", "teste1")
        self.password = password or os.getenv("CERBERUS_PASSWORD", "Le91916212.")
        self.ssl_ctx = ssl.create_default_context()
        self.ssl_ctx.check_hostname = False
        self.ssl_ctx.verify_mode = ssl.CERT_NONE
        self.cookies_dict = {}

        if self.cookie:
            self._parse_cookie_str(self.cookie)

    def _parse_cookie_str(self, cookie_str):
        for part in cookie_str.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                self.cookies_dict[k.strip()] = v.strip()

    def _get_cookie_header(self):
        return "; ".join([f"{k}={v}" for k, v in self.cookies_dict.items()])

    def set_cookie(self, cookie_str):
        self.cookie = cookie_str
        self._parse_cookie_str(cookie_str)

    def fetch(self, url, method="GET", data=None, timeout=20):
        headers = dict(DEFAULT_HEADERS)
        cookie_hdr = self._get_cookie_header()
        if cookie_hdr:
            headers['Cookie'] = cookie_hdr

        encoded_data = None
        if data:
            if isinstance(data, dict):
                encoded_data = urllib.parse.urlencode(data).encode('utf-8')
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
            elif isinstance(data, str):
                encoded_data = data.encode('utf-8')

        req = urllib.request.Request(url, data=encoded_data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=timeout) as resp:
                # Capture set-cookie
                set_cookies = resp.headers.get_all('Set-Cookie', [])
                for sc in set_cookies:
                    c_part = sc.split(";")[0]
                    if "=" in c_part:
                        ck, cv = c_part.split("=", 1)
                        self.cookies_dict[ck.strip()] = cv.strip()

                content = resp.read().decode('utf-8', errors='ignore')
                return content, resp.status, resp.geturl()
        except urllib.error.HTTPError as e:
            set_cookies = e.headers.get_all('Set-Cookie', [])
            for sc in set_cookies:
                c_part = sc.split(";")[0]
                if "=" in c_part:
                    ck, cv = c_part.split("=", 1)
                    self.cookies_dict[ck.strip()] = cv.strip()
            content = e.read().decode('utf-8', errors='ignore')
            return content, e.code, e.url
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None, 0, url

    def login(self):
        """Authenticates with Cerberus Games using username/password to get session cookies."""
        if not self.username or not self.password:
            logger.warning("No credentials provided for Cerberus Games login.")
            return False

        logger.info(f"Authenticating as user '{self.username}' on Cerberus Games...")
        # 1. Fetch login page to get CSRF token
        html, status, _ = self.fetch("https://cerberus-games.com/login/")
        if not html:
            logger.error("Failed to load login page.")
            return False

        token_match = re.search(r'name="_xfToken"\s+value="([^"]+)"', html)
        token = token_match.group(1) if token_match else None
        if not token:
            logger.error("Could not find _xfToken on login page.")
            return False

        # 2. Submit credentials
        login_data = {
            '_xfToken': token,
            'login': self.username,
            'password': self.password,
            'remember': '1',
            '_xfRedirect': 'https://cerberus-games.com/market/'
        }

        resp_html, resp_status, final_url = self.fetch(LOGIN_URL, method="POST", data=login_data)
        if "template-login" in (resp_html or ""):
            logger.error("Login failed: Still on login template.")
            return False

        logger.info(f"Login successful! Session established for user '{self.username}'.")
        return True

    def classify_race(self, text):
        t = text.lower()
        if any(w in t for w in ['cora', 'кор', 'кора', 'анимус', 'геката', 'пеймон', 'инанна', 'иссида', 'суммонер', 'пастырь']):
            return 'Cora'
        if any(w in t for w in ['bellato', 'белл', 'белла', 'бб', 'mau', 'мява', 'мау', 'голиаф', 'баллиста', 'минёр']):
            return 'Bellato'
        if any(w in t for w in ['accretia', 'acretia', 'акр', 'акрет', 'ланч', 'пусковик', 'каратель', 'штурмовик', 'спец акр']):
            return 'Accretia'
        return 'All'

    def classify_type(self, text):
        t = text.lower()
        if any(w in t for w in ['character', 'перс', 'персонаж', 'лвл', 'lvl', 'аккаунт', 'мау 50', 'ланч 50', 'спец 44', 'чар', 'char']):
            return 'Character'
        if any(w in t for w in ['weapon', 'релик', 'relic', 'кримсон', 'лук', 'меч', 'копье', 'пулемет', 'бластер', 'посох', 'оружие', 'леон', 'leon', 'knife', 'bow', 'staff', 'gun', 'sword', 'spadona']):
            return 'Weapon'
        if any(w in t for w in ['armor', 'броня', 'сет', 'шлем', 'штаны', 'торс', 'боты', 'перчи', 'sp armor', 'armlet', 'greave', 'amice', 'trouser', 'gauntlets', 'mitten']):
            return 'Armor'
        if any(w in t for w in ['бижа', 'jewelry', 'кольцо', 'амулет', 'цитадель', 'hdh', 'didalo', 'knighwalker', 'earring', 'ring', 'topaz', 'amulet']):
            return 'Jewelry'
        if any(w in t for w in ['excelsiar', 'talic', 'руда', 'ресурс', 'чип', 'платина', 'gold', 'валюта', 'кк', 'cs', 'cash shop', 'катализатор', 'crystal', 'seeds', 'box']):
            return 'Currency / Resource'
        return 'General / Items'

    def parse_price(self, text):
        m = re.search(r'(\d+[\d\s.,]*)\s*(cs|cash\s*shop|kk|кк|шоп|шопа|rub|руб|plat|платины?|\$|usd|r\$)', text, re.IGNORECASE)
        if m:
            raw_num = m.group(1).replace(' ', '').replace(',', '.')
            unit = m.group(2).upper()
            try:
                num_val = float(raw_num)
            except ValueError:
                num_val = None
            return f"{m.group(1).strip()} {unit}", num_val, unit
        return "Negotiable", None, "Cash Shop"

    def scrape_web_auction(self, max_pages=5):
        """
        Scrapes https://cerberus-games.com/market/items
        Authenticates automatically if needed.
        Crawls items across all servers and pages.
        """
        logger.info("Attempting to scrape Web-Auction at https://cerberus-games.com/market/items...")
        items = []

        # Check access
        html, status, _ = self.fetch(MARKET_URL)
        if status == 403 or "template-login" in (html or ""):
            logger.info("Session not active or expired. Logging in...")
            if not self.login():
                msg = "Falha no login do /market/. Verifique as credenciais."
                logger.warning(msg)
                return items, msg
            # Re-fetch after login
            html, status, _ = self.fetch(MARKET_URL)

        if status != 200 or not html:
            msg = f"Failed to fetch market items (HTTP {status})"
            logger.error(msg)
            return items, msg

        # Extract CSRF token
        token_match = re.search(r'name="_xfToken"\s+value="([^"]+)"', html)
        csrf_token = token_match.group(1) if token_match else None

        for srv in SERVERS:
            logger.info(f"Scraping Web-Auction Server: {srv['name']} (ID {srv['id']})...")
            for page in range(1, max_pages + 1):
                post_data = {
                    '_xfToken': csrf_token,
                    'srv': srv['id'],
                    'page': str(page),
                    'sort': 'datedown'
                }
                page_html, p_status, _ = self.fetch(MARKET_URL, method="POST", data=post_data)
                if p_status != 200 or not page_html:
                    break

                soup = BeautifulSoup(page_html, 'html.parser')
                blocks = soup.select('.itemBlock')
                if not blocks:
                    logger.info(f"Server {srv['name']}: no more items at page {page}.")
                    break

                for b in blocks:
                    try:
                        # Extract lot ID
                        lot_id_match = re.search(r'itemDetailsHandler\([^,]+,\s*(\d+)\)', str(b))
                        lot_id = lot_id_match.group(1) if lot_id_match else str(hash(str(b)))

                        name_elem = b.select_one('.itemName')
                        title = name_elem.get_text(strip=True) if name_elem else "Unknown Item"

                        # Level / upgrade
                        level_elem = b.select_one('.itemLevel')
                        level_text = level_elem.get_text(strip=True) if level_elem else ""

                        # Amount
                        amount_elem = b.select_one('.itemAmount')
                        amount_text = amount_elem.get_text(strip=True) if amount_elem else "1 pcs."

                        # Price
                        price_elem = b.select_one('.itemBuy')
                        price_raw = price_elem.get_text(strip=True) if price_elem else "0 CS"
                        price_str, price_val, curr = self.parse_price(price_raw)

                        # Check details element in DOM
                        details_elem = soup.select_one(f'#details{lot_id}')
                        char_text = details_elem.get_text(separator=" | ", strip=True) if details_elem else ""

                        # Determine race
                        race = "All"
                        if "Race: Bellato" in char_text or "bellato" in title.lower():
                            race = "Bellato"
                        elif "Race: Cora" in char_text or "cora" in title.lower():
                            race = "Cora"
                        elif "Race: Accretia" in char_text or "Race: Acretia" in char_text or "acretia" in title.lower() or "accretia" in title.lower():
                            race = "Accretia"
                        else:
                            race = self.classify_race(title)

                        category = self.classify_type(title)

                        item_url = f"https://cerberus-games.com/market/?lot={lot_id}"

                        desc = f"{title} (Qtde: {amount_text})\nNível: {level_text}\nPreço: {price_str}\nServidor: {srv['name']}\nDetalhes: {char_text}"

                        items.append({
                            "source_type": "web_auction",
                            "external_id": f"lot_{lot_id}",
                            "title": f"{title} {level_text}".strip(),
                            "category": category,
                            "race": race,
                            "item_type": category,
                            "price": price_str,
                            "price_val": price_val,
                            "currency": curr,
                            "seller": "Web-Auction",
                            "item_url": item_url,
                            "description": desc,
                            "status": "active",
                            "extra_data": {
                                "server": srv['name'],
                                "server_id": srv['id'],
                                "lot_id": lot_id,
                                "amount": amount_text,
                                "level": level_text,
                                "raw_characteristics": char_text
                            }
                        })
                    except Exception as e:
                        logger.error(f"Error parsing auction block: {e}")

                time.sleep(0.3)

        logger.info(f"Finished Web-Auction scraping! Extracted {len(items)} lots.")
        return items, "OK"

    def scrape_forum_section(self, section, max_pages=3, fetch_details=False):
        items = []
        base_sec_url = section["url"]
        logger.info(f"Starting scrape of forum section: {section['name']} (up to {max_pages} pages)")

        for page in range(1, max_pages + 1):
            page_url = base_sec_url if page == 1 else f"{base_sec_url.rstrip('/')}/page-{page}"
            html, status, _ = self.fetch(page_url)
            if status != 200 or not html:
                break

            soup = BeautifulSoup(html, 'html.parser')
            threads = soup.select('div.structItem--thread')
            if not threads:
                break

            for t_elem in threads:
                try:
                    title_elem = t_elem.select_one('div.structItem-title a[data-xf-init="preview-tooltip"]') or t_elem.select_one('div.structItem-title a[href*="/threads/"]')
                    if not title_elem:
                        continue

                    raw_title = title_elem.get_text(strip=True)
                    href = title_elem.get('href', '')
                    if not href.startswith('http'):
                        href = f"{BASE_URL}{href}"

                    thread_id_match = re.search(r'\.(\d+)/?$', href)
                    thread_id = thread_id_match.group(1) if thread_id_match else href.rstrip('/').split('/')[-1]

                    author = t_elem.get('data-author', 'Anonymous')
                    time_elem = t_elem.select_one('time.u-dt')
                    post_date = time_elem.get('datetime') if time_elem else None

                    race = self.classify_race(raw_title)
                    item_type = self.classify_type(raw_title)
                    price_str, price_val, currency = self.parse_price(raw_title)

                    description = ""
                    if fetch_details:
                        d_html, d_status, _ = self.fetch(href)
                        if d_status == 200 and d_html:
                            d_soup = BeautifulSoup(d_html, 'html.parser')
                            first_post = d_soup.select_one('article.message-body div.bbWrapper')
                            if first_post:
                                description = first_post.get_text(separator="\n", strip=True)
                                if price_str == "Negotiable":
                                    d_price_str, d_price_val, d_curr = self.parse_price(description)
                                    if d_price_str != "Negotiable":
                                        price_str, price_val, currency = d_price_str, d_price_val, d_curr
                                if race == "All":
                                    race = self.classify_race(description)
                        time.sleep(0.3)

                    items.append({
                        "source_type": "forum_marketplace",
                        "external_id": f"th_{thread_id}",
                        "title": raw_title,
                        "category": item_type,
                        "race": race,
                        "item_type": item_type,
                        "price": price_str,
                        "price_val": price_val,
                        "currency": currency,
                        "seller": author,
                        "item_url": href,
                        "description": description or raw_title,
                        "status": "active",
                        "extra_data": {
                            "section": section["name"],
                            "section_id": section["id"],
                            "post_date": post_date
                        }
                    })
                except Exception as e:
                    logger.error(f"Error parsing forum thread: {e}")

        logger.info(f"Finished forum {section['name']}, scraped {len(items)} items.")
        return items

    def run(self, max_forum_pages=2, max_auction_pages=5, fetch_details=False):
        log_id = self.db.start_log(source="all")
        all_items = []
        errors = []

        try:
            # 1. Scrape Web Auction (Authenticated)
            auction_items, auction_msg = self.scrape_web_auction(max_pages=max_auction_pages)
            all_items.extend(auction_items)
            if auction_msg != "OK":
                errors.append(f"Web Auction: {auction_msg}")

            # 2. Scrape Public Marketplace Forums
            for sec in FORUM_SECTIONS:
                sec_items = self.scrape_forum_section(sec, max_pages=max_forum_pages, fetch_details=fetch_details)
                all_items.extend(sec_items)

            # 3. Save to database
            saved_count = 0
            for item in all_items:
                try:
                    self.db.upsert_item(item)
                    saved_count += 1
                except Exception as e:
                    logger.error(f"Failed to upsert item {item.get('title')}: {e}")

            status_str = "success" if saved_count > 0 else "warning"
            err_str = "; ".join(errors) if errors else None
            self.db.finish_log(log_id, items_found=len(all_items), items_saved=saved_count, status=status_str, error_message=err_str)

            # 4. Dump to JSON & CSV files
            self.export_dumps(all_items)

            logger.info(f"Scrape completed! Total: {len(all_items)}, Saved to DB: {saved_count}")
            return {
                "items_found": len(all_items),
                "items_saved": saved_count,
                "auction_items": len(auction_items),
                "status": status_str,
                "notes": errors
            }

        except Exception as e:
            logger.exception("Fatal error during scrape run")
            self.db.finish_log(log_id, items_found=len(all_items), items_saved=0, status="error", error_message=str(e))
            raise

    def export_dumps(self, items, output_dir=None):
        out_dir = output_dir or os.path.join(os.path.dirname(os.path.dirname(__file__)), "exports")
        os.makedirs(out_dir, exist_ok=True)

        json_path = os.path.join(out_dir, "market_data_dump.json")
        csv_path = os.path.join(out_dir, "market_data_dump.csv")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)

        import csv
        if items:
            keys = ["source_type", "external_id", "title", "race", "category", "price", "price_val", "currency", "seller", "item_url", "status"]
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
                writer.writeheader()
                for item in items:
                    writer.writerow(item)

        logger.info(f"Exported dump files: {json_path} and {csv_path}")

if __name__ == "__main__":
    scraper = CerberusScraper()
    scraper.db.init_tables()
    result = scraper.run(max_forum_pages=2, max_auction_pages=5)
    print(json.dumps(result, indent=2))
