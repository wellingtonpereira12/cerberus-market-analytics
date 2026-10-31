import os
import json
import logging
from datetime import datetime

logger = logging.getLogger("cerberus_db")

try:
    import pymysql
    from pymysql.cursors import DictCursor
    HAS_PYMYSQL = True
except ImportError:
    HAS_PYMYSQL = False

class CerberusDatabase:
    def __init__(self, host=None, port=None, user=None, password=None, database=None):
        self.host = host or os.getenv("DB_HOST", "127.0.0.1")
        self.port = int(port or os.getenv("DB_PORT", "3306"))
        self.user = user or os.getenv("DB_USER", "cerberus_owner")
        self.password = password or os.getenv("DB_PASSWORD", "CerberusMarket2026!")
        self.database = database or os.getenv("DB_NAME", "cerberus_market")

    def get_connection(self):
        if not HAS_PYMYSQL:
            raise RuntimeError("pymysql is required to connect to MariaDB")

        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            charset='utf8mb4',
            cursorclass=DictCursor,
            autocommit=True,
            connect_timeout=10
        )

    def init_tables(self):
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                    CREATE TABLE IF NOT EXISTS market_items (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        source_type VARCHAR(50) NOT NULL,
                        external_id VARCHAR(100) NOT NULL,
                        title VARCHAR(255) NOT NULL,
                        category VARCHAR(100) DEFAULT 'General',
                        race VARCHAR(50) DEFAULT 'All',
                        item_type VARCHAR(100) DEFAULT NULL,
                        price VARCHAR(100) DEFAULT NULL,
                        price_val DECIMAL(14,2) DEFAULT NULL,
                        currency VARCHAR(50) DEFAULT 'Cash Shop',
                        seller VARCHAR(100) DEFAULT 'Anonymous',
                        item_url VARCHAR(500) NOT NULL,
                        description MEDIUMTEXT DEFAULT NULL,
                        status VARCHAR(50) DEFAULT 'active',
                        extra_data JSON DEFAULT NULL,
                        scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        UNIQUE KEY uq_source_ext (source_type, external_id),
                        INDEX idx_category (category),
                        INDEX idx_race (race),
                        INDEX idx_status (status),
                        INDEX idx_scraped_at (scraped_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                    """)

                    cur.execute("""
                    CREATE TABLE IF NOT EXISTS scrape_logs (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        finished_at DATETIME NULL,
                        source VARCHAR(100),
                        items_found INT DEFAULT 0,
                        items_saved INT DEFAULT 0,
                        status VARCHAR(50) DEFAULT 'running',
                        error_message TEXT DEFAULT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                    """)
            logger.info("Database tables initialized successfully.")
            return True
        except Exception as e:
            logger.error(f"Error initializing MariaDB tables: {e}")
            return False

    def upsert_item(self, item):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                sql = """
                INSERT INTO market_items (
                    source_type, external_id, title, category, race, item_type,
                    price, price_val, currency, seller, item_url, description,
                    status, extra_data
                ) VALUES (
                    %(source_type)s, %(external_id)s, %(title)s, %(category)s, %(race)s, %(item_type)s,
                    %(price)s, %(price_val)s, %(currency)s, %(seller)s, %(item_url)s, %(description)s,
                    %(status)s, %(extra_data)s
                )
                ON DUPLICATE KEY UPDATE
                    title = VALUES(title),
                    category = VALUES(category),
                    race = VALUES(race),
                    item_type = VALUES(item_type),
                    price = VALUES(price),
                    price_val = VALUES(price_val),
                    currency = VALUES(currency),
                    seller = VALUES(seller),
                    item_url = VALUES(item_url),
                    description = VALUES(description),
                    status = VALUES(status),
                    extra_data = VALUES(extra_data),
                    updated_at = CURRENT_TIMESTAMP
                """
                extra_json = json.dumps(item.get("extra_data", {}), ensure_ascii=False) if item.get("extra_data") else None
                params = {
                    "source_type": item.get("source_type", "forum_marketplace"),
                    "external_id": str(item.get("external_id")),
                    "title": (item.get("title") or "")[:255],
                    "category": item.get("category", "General"),
                    "race": item.get("race", "All"),
                    "item_type": item.get("item_type", "General"),
                    "price": str(item.get("price")) if item.get("price") is not None else "Negotiable",
                    "price_val": item.get("price_val"),
                    "currency": item.get("currency", "Cash Shop"),
                    "seller": (item.get("seller") or "Anonymous")[:100],
                    "item_url": (item.get("item_url") or "")[:500],
                    "description": item.get("description", ""),
                    "status": item.get("status", "active"),
                    "extra_data": extra_json
                }
                cur.execute(sql, params)

    def start_log(self, source="all"):
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO scrape_logs (source, status) VALUES (%s, 'running')",
                        (source,)
                    )
                    return cur.lastrowid
        except Exception as e:
            logger.error(f"Failed to start scrape log: {e}")
            return None

    def finish_log(self, log_id, items_found, items_saved, status="success", error_message=None):
        if not log_id:
            return
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE scrape_logs
                        SET finished_at = CURRENT_TIMESTAMP,
                            items_found = %s,
                            items_saved = %s,
                            status = %s,
                            error_message = %s
                        WHERE id = %s
                    """, (items_found, items_saved, status, error_message, log_id))
        except Exception as e:
            logger.error(f"Failed to finish scrape log {log_id}: {e}")

    def query_items(self, page=1, per_page=25, race=None, category=None, search=None, source=None, sort="scraped_at DESC"):
        with self.get_connection() as conn:
            where_clauses = ["1=1"]
            params = []

            if race and race.lower() != 'all':
                where_clauses.append("race = %s")
                params.append(race)

            if category and category.lower() != 'all':
                where_clauses.append("category = %s")
                params.append(category)

            if source and source.lower() != 'all':
                where_clauses.append("source_type = %s")
                params.append(source)

            if search:
                where_clauses.append("(title LIKE %s OR description LIKE %s OR seller LIKE %s)")
                like_val = f"%{search}%"
                params.extend([like_val, like_val, like_val])

            where_sql = " AND ".join(where_clauses)
            offset = (page - 1) * per_page

            allowed_sorts = {
                "scraped_at DESC": "scraped_at DESC",
                "scraped_at ASC": "scraped_at ASC",
                "price_val DESC": "price_val DESC",
                "price_val ASC": "price_val ASC",
                "title ASC": "title ASC",
                "title DESC": "title DESC"
            }
            order_sql = allowed_sorts.get(sort, "scraped_at DESC")

            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) as total FROM market_items WHERE {where_sql}", params)
                total = cur.fetchone()["total"]

                query_sql = f"""
                    SELECT id, source_type, external_id, title, category, race, item_type,
                           price, price_val, currency, seller, item_url, description,
                           status, extra_data, scraped_at, updated_at
                    FROM market_items
                    WHERE {where_sql}
                    ORDER BY {order_sql}
                    LIMIT %s OFFSET %s
                """
                page_params = list(params) + [per_page, offset]
                cur.execute(query_sql, page_params)
                items = cur.fetchall()

                for item in items:
                    if isinstance(item.get("scraped_at"), datetime):
                        item["scraped_at"] = item["scraped_at"].strftime("%Y-%m-%d %H:%M:%S")
                    if isinstance(item.get("updated_at"), datetime):
                        item["updated_at"] = item["updated_at"].strftime("%Y-%m-%d %H:%M:%S")
                    if isinstance(item.get("extra_data"), str):
                        try:
                            item["extra_data"] = json.loads(item["extra_data"])
                        except Exception:
                            pass

                return {
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "total_pages": (total + per_page - 1) // per_page if total > 0 else 1,
                    "items": items
                }

    def get_stats(self):
        with self.get_connection() as conn:
            stats = {
                "total_items": 0,
                "by_race": {},
                "by_category": {},
                "by_source": {},
                "latest_logs": []
            }
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) as count FROM market_items")
                stats["total_items"] = cur.fetchone()["count"]

                cur.execute("SELECT race, COUNT(*) as count FROM market_items GROUP BY race")
                for row in cur.fetchall():
                    stats["by_race"][row["race"]] = row["count"]

                cur.execute("SELECT category, COUNT(*) as count FROM market_items GROUP BY category")
                for row in cur.fetchall():
                    stats["by_category"][row["category"]] = row["count"]

                cur.execute("SELECT source_type, COUNT(*) as count FROM market_items GROUP BY source_type")
                for row in cur.fetchall():
                    stats["by_source"][row["source_type"]] = row["count"]

                cur.execute("SELECT * FROM scrape_logs ORDER BY id DESC LIMIT 5")
                logs = cur.fetchall()
                for l in logs:
                    if isinstance(l.get("started_at"), datetime):
                        l["started_at"] = l["started_at"].strftime("%Y-%m-%d %H:%M:%S")
                    if isinstance(l.get("finished_at"), datetime):
                        l["finished_at"] = l["finished_at"].strftime("%Y-%m-%d %H:%M:%S")
                stats["latest_logs"] = logs

            return stats

    def get_all_items(self):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM market_items ORDER BY id DESC")
                items = cur.fetchall()
                for item in items:
                    if isinstance(item.get("scraped_at"), datetime):
                        item["scraped_at"] = item["scraped_at"].strftime("%Y-%m-%d %H:%M:%S")
                    if isinstance(item.get("updated_at"), datetime):
                        item["updated_at"] = item["updated_at"].strftime("%Y-%m-%d %H:%M:%S")
                return items
