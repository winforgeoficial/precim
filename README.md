# precim 🐷

Caçador de ofertas lúdico: acompanha preços de SSD (e o que mais você quiser) em várias lojas
brasileiras, guarda o histórico e avisa no Telegram quando algo entra em promoção ou cai abaixo do
valor que você definiu — com loja, preço, R$/GB e estoque.

## Status
Fases 1–2 prontas: coleta da **Kabum**, histórico em SQLite, agendador e alertas no Telegram
(envio simples via Bot API). Pichau e Terabyte estão atrás de Cloudflare/manutenção e entram com
Playwright; painel web e comandos do bot vêm nas próximas fases.

### Acompanhar um produto
```bash
curl -X POST localhost:8000/watch -H 'content-type: application/json' \
  -d '{"url":"https://www.kabum.com.br/produto/...","name":"SSD 1TB","capacity_gb":1000,"target_price":400}'
curl localhost:8000/watch
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
```

Uso pessoal; respeite os termos das lojas e mantenha o ritmo de coleta baixo.
