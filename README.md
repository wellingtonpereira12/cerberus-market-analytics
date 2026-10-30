# 🐺 Cerberus Games - Market Scraper & Analytics

Aplicação completa de **Web Scraping, Armazenamento Relacional (MariaDB) e Painel Web de Análise de Dados** para o mercado do **Cerberus Games (RF Online)**: [cerberus-games.com/market](https://cerberus-games.com/market/).

---

## 📌 Visão Geral do Sistema

O sistema foi desenvolvido para capturar e estruturar tudo que está sendo anunciado e comercializado no Cerberus Games, incluindo:
- **Web-Auction oficial (`/market`)**: Itens, personagens e armas do leilão inter-raças com autenticação via sessão/cookie.
- **Marketplace Fórum (`161` Force & Steel e `144` Stage Era)**: Listagens ativas da comunidade, tópicos de venda/compra de contas (MAU, lançadores, animus, sets), preços em Cash Shop (CS), moedas raciais (KK) e platina.
- **Banco de Dados MariaDB**: Gravação relacional persistente com identificadores únicos, evitando duplicidade (`ON DUPLICATE KEY UPDATE`).
- **Dashboard Web Interativo (Porta 3150)**: Visualização em tempo real com gráficos por Raça (Bellato, Cora, Accretia), tipos de itens (Personagens, Armas, Armaduras, Joias, Moedas), filtros de busca avançados, exportação para CSV/JSON e botão para disparar novo scraping sob demanda.
- **CI/CD Automático no GitHub Actions**: Deploy contínuo na VPS via SSH a cada push no repositório.

---

## 🗄️ Estrutura do Banco de Dados (MariaDB)

- **Database**: `cerberus_market`
- **Owner / Usuário Criado**: `cerberus_owner`
- **Senha**: `CerberusMarket2026!`
- **Host**: `localhost` / `%` (porta 3306)

### Tabelas Criadas:
1. `market_items`:
   - `id`: Identificador interno auto incremento
   - `source_type`: Origem (`web_auction` ou `forum_marketplace`)
   - `external_id`: ID do lote ou ID do tópico no fórum
   - `title`: Título do anúncio / item
   - `category`: Tipo classificado (`Character`, `Weapon`, `Armor`, `Jewelry`, `Currency / Resource`, etc.)
   - `race`: Raça associada (`Bellato`, `Cora`, `Accretia`, `All`)
   - `price` / `price_val` / `currency`: Valores extraídos (ex: `500 CS`, `150kk`)
   - `seller`: Vendedor / autor do anúncio
   - `item_url`: Link direto para o anúncio no Cerberus Games
   - `description`: Conteúdo detalhado do post / lote
   - `status`: Status (`active`, `sold`, `expired`)
   - `scraped_at` / `updated_at`: Timestamps de auditoria
2. `scrape_logs`: Histórico das execuções do robô de coleta.

---

## 📊 Painel Web & Analytics (Porta 3150)

O painel web está disponível diretamente em:
```
http://187.127.17.88:3150
```

### Funcionalidades do Dashboard:
- **Cards de Indicadores**: Total de itens coletados, contagem por raça (Cora, Bellato, Accretia), status do último robô.
- **Gráficos Interativos (Chart.js)**: Gráfico de rosca para market share por raça e gráfico de barras por categoria de itens.
- **Tabela com Busca e Filtros Dinâmicos**: Filtragem por raça, categoria, origem (Web-Auction vs Fórum), ordenação por preço e busca textual.
- **Modal de Detalhes**: Visualização completa do texto do anúncio com link para a postagem original.
- **Exportação em 1 Clique**:
  - `GET /api/export/csv`: Download formatado para Excel/Pandas.
  - `GET /api/export/json`: Dump completo estruturado em JSON.
- **Configuração de Cookie /market**: Modal para colar o cookie de sessão do navegador e destravar a raspagem autenticada do `/market/`.

---

## 🚀 Como Executar Localmente ou na VPS

### 1. Com Docker Compose (Recomendado):
```bash
docker compose up -d --build
```

### 2. Manualmente via Python:
```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Executar apenas o Web Scraping
python main.py scrape --pages 2

# 3. Executar o Servidor Web e Scraper em background
python main.py both --port 3150
```

---

## 🔐 Configuração do Web-Auction (`/market`)

A rota `https://cerberus-games.com/market/` requer autenticação do fórum XenForo. Para que o robô faça raspagem dessa área privada:
1. Acesse o site `cerberus-games.com` e faça login com sua conta.
2. Abra as Ferramentas de Desenvolvedor (F12) &rarr; **Application** &rarr; **Cookies**.
3. Copie o cookie `xf_user` (ou o cabeçalho Cookie completo).
4. No Dashboard Web (porta 3150), clique no botão superior **"Cookie /market"** e cole o valor, ou defina a variável `CERBERUS_COOKIE` no `.env`.

---

## 🔄 Deploy Contínuo (CI/CD GitHub Action)

O repositório inclui a action `.github/workflows/deploy.yml` configurada com os Secrets:
- `VPS_HOST`: `187.127.17.88`
- `VPS_USER`: `root`
- `VPS_PASSWORD`: `Nead1075846@`
- `VPS_PORT`: `22`

A cada `git push`, o fluxo conecta via SSH, sincroniza o código em `/root/cerberus-market` e executa `docker compose up -d --build`.
