# precim 🐷

Caçador de ofertas lúdico: acompanha preços de SSD (e o que mais você quiser) em várias lojas
brasileiras, guarda o histórico e avisa no Telegram quando algo entra em promoção ou cai abaixo do
valor que você definiu — com loja, preço, R$/GB e estoque.

## Status
**Painel web pronto** (mascote Precinho, caça do dia com termômetro de R$/GB, histórico em gráfico,
conquistas). Abra `http://127.0.0.1:8000/` após `docker compose up`.

Prontos: coleta direta da **Kabum**, busca por **Buscapé/Zoom** (cobre Amazon, Kabum e Magalu),
histórico em SQLite e alertas no Telegram. **Pichau e Terabyte não aparecem nos agregadores e
bloqueiam acesso automatizado** — ficam de fora por ora. Comandos do bot do Telegram: próxima fase.

### Cadência anti-bloqueio
As varreduras seguem um ciclo rotativo **30 → 50 → 60 min → volta** (mais alguns segundos aleatórios),
configurável em `PRECIM_SCAN_CYCLE_MINUTES`. Se o Buscapé falhar, o Zoom (mesmos dados) é usado.

### Acompanhar uma busca em agregador
```bash
curl -X POST localhost:8000/api/search-watch -H 'content-type: application/json' \
  -d '{"query":"ssd nvme 1tb","min_capacity_gb":1000,"max_price_per_gb":0.5}'
```
Cada oferta só é avisada de novo se cair pelo menos 3%.

### Acompanhar um produto
```bash
curl -X POST localhost:8000/api/watch -H 'content-type: application/json' \
  -d '{"url":"https://www.kabum.com.br/produto/...","name":"SSD 1TB","capacity_gb":1000,"target_price":400}'
curl localhost:8000/api/watch
```
Configure `PRECIM_TELEGRAM_TOKEN` e `PRECIM_TELEGRAM_CHAT_ID` no `.env` para receber os avisos.

## Rodar
```bash
cp .env.example .env
docker compose up --build   # http://127.0.0.1:8000/health
```

## Desenvolver
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
uvicorn app.main:app --app-dir backend --reload   # API em :8000
```
Painel com hot reload (proxy para a API em :8000):
```bash
cd frontend && npm install && npm run dev
```

Uso pessoal; respeite os termos das lojas e mantenha o ritmo de coleta baixo.
