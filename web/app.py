import os
import sys
import json
import csv
import io
import asyncio
from typing import Optional
from fastapi import FastAPI, Query, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scraper.database import CerberusDatabase
from scraper.cerberus_scraper import CerberusScraper

app = FastAPI(title="Cerberus Market Analytics API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = CerberusDatabase()
scraper_instance = CerberusScraper(db=db)
is_scraping = False

class CookiePayload(BaseModel):
    cookie: str

class ScrapeTriggerPayload(BaseModel):
    pages: Optional[int] = 2
    fetch_details: Optional[bool] = False

@app.on_event("startup")
def startup_event():
    try:
        db.init_tables()
    except Exception as e:
        print(f"Startup DB init warning: {e}")

@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "cerberus-market-analytics"}

@app.get("/api/items")
def get_items(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    race: Optional[str] = None,
    category: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    sort: Optional[str] = "scraped_at DESC"
):
    try:
        data = db.query_items(
            page=page,
            per_page=per_page,
            race=race,
            category=category,
            source=source,
            search=search,
            sort=sort
        )
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats")
def get_stats():
    try:
        stats = db.get_stats()
        stats["is_scraping"] = is_scraping
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def run_scraper_task(pages: int, fetch_details: bool):
    global is_scraping
    is_scraping = True
    try:
        scraper_instance.run(max_forum_pages=pages, fetch_details=fetch_details)
    except Exception as e:
        print(f"Background scraper error: {e}")
    finally:
        is_scraping = False

@app.post("/api/scrape")
def trigger_scrape(payload: ScrapeTriggerPayload, background_tasks: BackgroundTasks):
    global is_scraping
    if is_scraping:
        return {"status": "already_running", "message": "Scraping is already in progress"}
    
    background_tasks.add_task(run_scraper_task, payload.pages or 2, payload.fetch_details or False)
    return {"status": "started", "message": f"Scraping started for {payload.pages or 2} pages"}

@app.post("/api/cookie")
def set_cookie(payload: CookiePayload):
    scraper_instance.set_cookie(payload.cookie)
    return {"status": "success", "message": "Cookie updated successfully for Web-Auction scraper"}

@app.get("/api/export/csv")
def export_csv():
    items = db.get_all_items()
    output = io.StringIO()
    keys = ["id", "source_type", "external_id", "title", "race", "category", "item_type", "price", "price_val", "currency", "seller", "item_url", "status", "scraped_at"]
    writer = csv.DictWriter(output, fieldnames=keys, extrasaction="ignore")
    writer.writeheader()
    for it in items:
        writer.writerow(it)
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=cerberus_market_items.csv"}
    )

@app.get("/api/export/json")
def export_json():
    items = db.get_all_items()
    json_bytes = json.dumps(items, ensure_ascii=False, indent=2).encode('utf-8')
    return StreamingResponse(
        io.BytesIO(json_bytes),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=cerberus_market_items.json"}
    )

@app.get("/", response_class=HTMLResponse)
def index_page():
    html_file = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    if os.path.exists(html_file):
        with open(html_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Cerberus Market Analytics Dashboard</h1>"
