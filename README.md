# precim 🐷

Caçador de ofertas lúdico: acompanha preços de SSD (e o que mais você quiser) em várias lojas
brasileiras, guarda o histórico e avisa no Telegram quando algo entra em promoção ou cai abaixo do
valor que você definiu — com loja, preço, R$/GB e estoque.

## Status
Fundação (fase 1). Coleta de lojas, bot do Telegram e painel vêm nas próximas fases.

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
