import os
import sys
import argparse
import uvicorn
import threading
import time

from scraper.database import CerberusDatabase
from scraper.cerberus_scraper import CerberusScraper

def run_scraper_job(pages=0, auction_pages=10, details=False, race=None, category=None, search=None, source="web_auction", server=None):
    filters_info = []
    if race and race != 'All': filters_info.append(f"Raça={race}")
    if category and category != 'All': filters_info.append(f"Categoria={category}")
    if search: filters_info.append(f"Busca='{search}'")
    if source and source != 'All': filters_info.append(f"Origem={source}")
    if server and server != 'All': filters_info.append(f"Servidor={server}")

    filter_str = f" [Filtros: {', '.join(filters_info)}]" if filters_info else " [Apenas Web-Auction /market]"
    print(f"🚀 Iniciando job de Web Scraping do Cerberus Games (Apenas Web-Auction){filter_str}...")
    db = CerberusDatabase()
    db.init_tables()
    scraper = CerberusScraper(db=db)
    result = scraper.run(
        max_forum_pages=pages,
        max_auction_pages=auction_pages,
        fetch_details=details,
        filter_race=race,
        filter_category=category,
        filter_search=search,
        filter_source=source,
        filter_server=server
    )
    print(f"✅ Scraping concluído: {result['items_saved']} itens do Web-Auction salvos no MariaDB.")
    return result

def periodic_scraper_worker(interval_seconds=3600):
    while True:
        try:
            time.sleep(interval_seconds)
            print("⏰ Executando scraping periódico agendado (Web-Auction)...")
            run_scraper_job(pages=0, auction_pages=10, details=False, source="web_auction")
        except Exception as e:
            print(f"❌ Erro no scraper periódico: {e}")

def start_server(host="0.0.0.0", port=3150, enable_periodic=True):
    print(f"🌐 Iniciando Cerberus Market Analytics Dashboard em http://{host}:{port}")
    db = CerberusDatabase()
    db.init_tables()

    # Initial quick scrape if database is empty
    stats = db.get_stats()
    if stats["total_items"] == 0:
        print("ℹ️ Banco de dados vazio. Executando primeira carga de dados inicial (Web-Auction)...")
        try:
            run_scraper_job(pages=0, auction_pages=10, details=False, source="web_auction")
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
    parser.add_argument("--pages", type=int, default=0, help="Número de páginas para scraping por seção de fórum (padrão: 0)")
    parser.add_argument("--auction-pages", type=int, default=10, help="Número de páginas para scraping do Web-Auction (padrão: 10)")
    parser.add_argument("--details", action="store_true", help="Coleta detalhes aprofundados de cada post")
    parser.add_argument("--race", default=None, choices=["All", "Bellato", "Cora", "Accretia"], help="Filtro prévio por raça")
    parser.add_argument("--category", default=None, help="Filtro prévio por categoria (Character, Weapon, Armor, etc.)")
    parser.add_argument("--search", default=None, help="Palavra-chave ou termo para filtrar durante a coleta")
    parser.add_argument("--source", default="web_auction", choices=["web_auction", "forum_marketplace", "All"], help="Origem da coleta (padrão: web_auction)")
    parser.add_argument("--server", default=None, help="ID do servidor (1 para Force & Steel, 0 para Stage Era)")
    parser.add_argument("--port", type=int, default=3150, help="Porta do servidor web (padrão 3150)")
    parser.add_argument("--host", default="0.0.0.0", help="Host do servidor web")

    args = parser.parse_args()

    if args.action == "scrape":
        run_scraper_job(
            pages=args.pages,
            auction_pages=args.auction_pages,
            details=args.details,
            race=args.race,
            category=args.category,
            search=args.search,
            source=args.source,
            server=args.server
        )
    elif args.action == "both":
        run_scraper_job(
            pages=args.pages,
            auction_pages=args.auction_pages,
            details=args.details,
            race=args.race,
            category=args.category,
            search=args.search,
            source=args.source,
            server=args.server
        )
        start_server(host=args.host, port=args.port)
    else:
        start_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
