import os
import sys
import re
import json
import time
import logging
import ssl
import urllib.request
from datetime import datetime
from bs4 import BeautifulSoup

from scraper.database import CerberusDatabase

logger = logging.getLogger("cerberus_scraper")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BASE_URL = "https://cerberus-games.com"
MARKET_URL = "https://cerberus-games.com/market"

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

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8,pt-BR;q=0.7',
    'Referer': 'https://cerberus-games.com/'
}

class CerberusScraper:
    def __init__(self, db=None, cookie=None):
        self.db = db or CerberusDatabase()
        self.cookie = cookie or os.getenv("CERBERUS_COOKIE")
        self.ssl_ctx = ssl.create_default_context()
        self.ssl_ctx.check_hostname = False
        self.ssl_ctx.verify_mode = ssl.CERT_NONE

    def set_cookie(self, cookie_str):
        self.cookie = cookie_str

    def fetch(self, url, timeout=20):
        headers = dict(DEFAULT_HEADERS)
        if self.cookie:
            headers['Cookie'] = self.cookie

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=timeout) as resp:
                content = resp.read().decode('utf-8', errors='ignore')
                return content, resp.status, resp.geturl()
        except urllib.error.HTTPError as e:
            content = e.read().decode('utf-8', errors='ignore')
            return content, e.code, e.url
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None, 0, url

    def classify_race(self, text):
        t = text.lower()
        # Cora keywords
        if any(w in t for w in ['cora', 'кор', 'кора', 'анимус', 'геката', 'пеймон', 'инанна', 'иссида', 'суммонер', 'чернокнижник', 'пастырь']):
            return 'Cora'
        # Bellato keywords
        if any(w in t for w in ['bellato', 'белл', 'белла', 'бб', 'mau', 'мява', 'мау', 'голиаф', 'баллиста', 'минёр', 'чуча', 'чучело']):
            return 'Bellato'
        # Accretia keywords
        if any(w in t for w in ['accretia', 'акр', 'акрет', 'ланч', 'пусковик', 'каратель', 'штурмовик', 'спец акр', 'дб акр', 'бб акр']):
            return 'Accretia'
        return 'All'

    def classify_type(self, text):
        t = text.lower()
        if any(w in t for w in ['character', 'перс', 'персонаж', 'лвл', 'lvl', 'аккаунт', 'мау 50', 'ланч 50', 'спец 44', 'чар', 'char']):
            return 'Character'
        if any(w in t for w in ['weapon', 'релик', 'relic', 'кримсон', 'лук', 'меч', 'копье', 'пулемет', 'бластер', 'посох', 'оружие', 'леон', 'leon', 'щит']):
            return 'Weapon'
        if any(w in t for w in ['armor', 'броня', 'сет', 'шлем', 'штаны', 'торс', 'боты', 'перчи', 'sp armor', 'палмас', 'palmas']):
            return 'Armor'
        if any(w in t for w in ['бижа', 'jewelry', 'кольцо', 'амулет', 'цитадель', 'hdh', 'didalo', 'knighwalker', 'оверперф']):
            return 'Jewelry'
        if any(w in t for w in ['тал', 'talic', 'руда', 'ресурс', 'чип', 'платина', 'gold', 'валюта', 'кк', 'cs', 'cash shop', 'катализатор']):
            return 'Currency / Resource'
        return 'General / Items'

    def parse_price(self, text):
        # Look for numbers with cash shop, kk, plat, rub
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

    def scrape_forum_section(self, section, max_pages=3, fetch_details=True):
        items = []
        base_sec_url = section["url"]
        logger.info(f"Starting scrape of forum section: {section['name']} (up to {max_pages} pages)")

        for page in range(1, max_pages + 1):
            if page == 1:
                page_url = base_sec_url
            else:
                page_url = f"{base_sec_url.rstrip('/')}/page-{page}"

            logger.info(f"Fetching page {page}: {page_url}")
            html, status, _ = self.fetch(page_url)
            if status != 200 or not html:
                logger.warning(f"Could not load page {page_url} (HTTP {status})")
                break

            soup = BeautifulSoup(html, 'html.parser')
            threads = soup.select('div.structItem--thread')
            if not threads:
                logger.info(f"No more threads found on page {page}.")
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

                    # Extract thread ID
                    thread_id_match = re.search(r'\.(\d+)/?$', href)
                    thread_id = thread_id_match.group(1) if thread_id_match else href.rstrip('/').split('/')[-1]

                    # Author
                    author = t_elem.get('data-author', 'Anonymous')

                    # Date
                    time_elem = t_elem.select_one('time.u-dt')
                    post_date = time_elem.get('datetime') if time_elem else None

                    # Category / Race / Price
                    race = self.classify_race(raw_title)
                    item_type = self.classify_type(raw_title)
                    price_str, price_val, currency = self.parse_price(raw_title)

                    description = ""
                    # Optionally fetch first post details
                    if fetch_details:
                        detail_html, detail_status, _ = self.fetch(href)
                        if detail_status == 200 and detail_html:
                            detail_soup = BeautifulSoup(detail_html, 'html.parser')
                            first_post = detail_soup.select_one('article.message-body div.bbWrapper')
                            if first_post:
                                description = first_post.get_text(separator="\n", strip=True)
                                # check if price in description is clearer
                                if price_str == "Negotiable":
                                    d_price_str, d_price_val, d_curr = self.parse_price(description)
                                    if d_price_str != "Negotiable":
                                        price_str, price_val, currency = d_price_str, d_price_val, d_curr
                                if race == "All":
                                    race = self.classify_race(description)

                        time.sleep(0.3) # respect server rate

                    item = {
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
                    }
                    items.append(item)
                except Exception as e:
                    logger.error(f"Error parsing thread element: {e}")

        logger.info(f"Finished section {section['name']}, scraped {len(items)} items.")
        return items

    def scrape_web_auction(self):
        """
        Scrapes https://cerberus-games.com/market
        Requires valid session cookie (CERBERUS_COOKIE).
        If not authenticated, logs guidance.
        """
        logger.info(f"Attempting to scrape Web-Auction at {MARKET_URL}")
        html, status, final_url = self.fetch(MARKET_URL)
        items = []

        if status == 403 or "template-login" in (html or ""):
            msg = "Web-Auction at /market/ requires forum authentication. Set CERBERUS_COOKIE (xf_user/xf_session) to enable live auction scraping."
            logger.warning(msg)
            return items, msg

        if status != 200 or not html:
            msg = f"Failed to fetch {MARKET_URL} (Status {status})"
            logger.error(msg)
            return items, msg

        soup = BeautifulSoup(html, 'html.parser')
        # Typical XenForo / custom auction cards: .market-item, .auction-lot, .shop-item, table rows
        cards = soup.select('.market-item, .auction-item, .marketItem, .lot-item, .dataList-row')
        logger.info(f"Found {len(cards)} market cards on {MARKET_URL}")

        for card in cards:
            try:
                title_elem = card.select_one('.title, .item-name, .name, h4, a')
                if not title_elem:
                    continue
                title = title_elem.get_text(strip=True)
                href = title_elem.get('href', MARKET_URL)
                if not href.startswith('http'):
                    href = f"{BASE_URL}{href}"

                price_elem = card.select_one('.price, .cost, .currency')
                price_text = price_elem.get_text(strip=True) if price_elem else "0 CS"
                price_str, price_val, curr = self.parse_price(price_text)

                seller_elem = card.select_one('.seller, .author, .owner')
                seller = seller_elem.get_text(strip=True) if seller_elem else "Anonymous"

                lot_id = card.get('data-id') or re.search(r'\d+', href).group(0) if re.search(r'\d+', href) else str(hash(title))

                race = self.classify_race(title)
                item_type = self.classify_type(title)

                items.append({
                    "source_type": "web_auction",
                    "external_id": f"lot_{lot_id}",
                    "title": title,
                    "category": item_type,
                    "race": race,
                    "item_type": item_type,
                    "price": price_str,
                    "price_val": price_val,
                    "currency": curr,
                    "seller": seller,
                    "item_url": href,
                    "description": card.get_text(separator=" ", strip=True),
                    "status": "active",
                    "extra_data": {"platform": "Cerberus Web-Auction"}
                })
            except Exception as e:
                logger.error(f"Error parsing auction card: {e}")

        return items, "OK"

    def run(self, max_forum_pages=2, fetch_details=True):
        log_id = self.db.start_log(source="all")
        all_items = []
        errors = []

        try:
            # 1. Scrape Web Auction
            auction_items, auction_msg = self.scrape_web_auction()
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

            # 4. Dump to JSON & CSV files for immediate analysis
            self.export_dumps(all_items)

            logger.info(f"Scrape completed! Found: {len(all_items)}, Saved to DB: {saved_count}")
            return {
                "items_found": len(all_items),
                "items_saved": saved_count,
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

        # Write JSON
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)

        # Write CSV
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
    result = scraper.run(max_forum_pages=2, fetch_details=False)
    print(json.dumps(result, indent=2))
