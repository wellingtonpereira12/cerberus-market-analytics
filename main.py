import os
import sys
import argparse
import uvicorn
import threading
import time

from scraper.database import CerberusDatabase
from scraper.cerberus_scraper import CerberusScraper

def run_scraper_job(pages=2, details=False):
    print("🚀 Iniciando job de Web Scraping do Cerberus Games...")
    db = CerberusDatabase()
    db.init_tables()
    scraper = CerberusScraper(db=db)
    result = scraper.run(max_forum_pages=pages, fetch_details=details)
    print(f"✅ Scraping concluído com sucesso: {result['items_saved']} itens salvos no MariaDB.")
    return result

def periodic_scraper_worker(interval_seconds=3600):
    while True:
        try:
            time.sleep(interval_seconds)
            print("⏰ Executando scraping periódico agendado...")
            run_scraper_job(pages=2, details=False)
        except Exception as e:
            print(f"❌ Erro no scraper periódico: {e}")

def start_server(host="0.0.0.0", port=3150, enable_periodic=True):
    print(f"🌐 Iniciando Cerberus Market Analytics Dashboard em http://{host}:{port}")
    db = CerberusDatabase()
    db.init_tables()

    # Initial quick scrape if database is empty
    stats = db.get_stats()
    if stats["total_items"] == 0:
        print("ℹ️ Banco de dados vazio. Executando primeira carga de dados inicial...")
        try:
            run_scraper_job(pages=2, details=False)
        except Exception as e:
            print(f"⚠️ Aviso na carga inicial: {e}")

    if enable_periodic:
        t = threading.Thread(target=periodic_scraper_worker, args=(3600,), daemon=True)
        t.start()

    uvicorn.run("web.app:app", host=host, port=port, reload=False)

def main():
    parser = argparse.ArgumentParser(description="Cerberus Market Scraper & Analytics Dashboard")
    parser.add_argument("action", nargs="?", default="server", choices=["scrape", "server", "both"],
                        help="Ação a executar: 'scrape' para rodar apenas o crawler, 'server' para rodar a aplicação web.")
    parser.add_argument("--pages", type=int, default=2, help="Número de páginas para scraping por seção")
    parser.add_argument("--details", action="store_true", help="Coleta detalhes aprofundados de cada post")
    parser.add_argument("--port", type=int, default=3150, help="Porta do servidor web (padrão 3150)")
    parser.add_argument("--host", default="0.0.0.0", help="Host do servidor web")

    args = parser.parse_args()

    if args.action == "scrape":
        run_scraper_job(pages=args.pages, details=args.details)
    elif args.action == "both":
        run_scraper_job(pages=args.pages, details=args.details)
        start_server(host=args.host, port=args.port)
    else:
        start_server(host=args.host, port=args.port)

if __name__ == "__main__":
    main()
