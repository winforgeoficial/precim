# precim 🐷

Caçador de ofertas lúdico: acompanha preços de SSD (e o que mais você quiser) em várias lojas
brasileiras, guarda o histórico e avisa no Telegram quando algo entra em promoção ou cai abaixo do
valor que você definiu — com loja, preço, R$/GB e estoque.

## Status
**Painel web pronto** (mascote Precinho, caça do dia com termômetro de R$/GB, histórico em gráfico,
conquistas). Abra `http://127.0.0.1:8000/` após `docker compose up`.

Prontos: coleta direta da **Kabum**, busca por **Buscapé/Zoom** (cobre Amazon, Kabum e Magalu),
histórico em SQLite e alertas no Telegram. **Pichau e Terabyte não aparecem nos agregadores e
bloqueiam acesso automatizado** — ficam de fora por ora. **Bot do Telegram** com comandos (abaixo).

### Ofertas conferidas × não verificadas
O Buscapé/Zoom é um agregador: muitas ofertas (principalmente da Magalu, inclusive vendedores
terceiros) já não existem na loja. Por isso cada oferta é rotulada:
- **✅ conferida** — preço e estoque lidos direto na página da loja (**Kabum**, descoberta pelo
  sitemap público; roda a cada 3 h, com pausas entre páginas).
- **✅ conferida (Amazon)** — o precim abre a busca da Amazon BR num navegador (Chromium/Playwright)
  e lê preço e título. Uma página por busca da caça, com pausas de 8–15 s, a cada 3 h. **Sem
  disfarce**: se a Amazon pedir captcha/verificação, a coleta **para por 12 h** (não há tentativa de
  contornar). Os termos de uso da Amazon proíbem acesso automatizado — o uso é por sua conta e risco.
  Desligue com `PRECIM_AMAZON_ENABLED=false`. O preço pode ser de vendedor terceiro.
- **⚠️ não verificada** — veio do Buscapé; pode já não estar disponível. O painel tem o filtro
  "Só conferidas na loja" e o Telegram avisa isso em cada mensagem.

O precim **não clica** nos links de redirecionamento do Buscapé para checar ofertas (são links de
anúncio pago).

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

## Bot do Telegram
1. No Telegram, fale com o **@BotFather**, crie um bot (`/newbot`) e copie o token para `PRECIM_TELEGRAM_TOKEN` no `.env`.
2. Suba o precim e mande `/start` ao seu bot: ele responde com o **chat id**. Coloque em `PRECIM_TELEGRAM_CHAT_ID` e reinicie.
3. Pronto: só esse chat consegue comandar o bot e receber alertas. Qualquer outro chat recebe "uso pessoal".

| Comando | O que faz |
|---|---|
| `/resumo` | melhores ofertas agora |
| `/cacar` | caça agora (espera de 5 min entre usos) |
| `/lista` | caças (`c1`) e produtos (`p1`) acompanhados |
| `/caca ssd nvme 1tb min=1000 alvo=700 rgb=0,6` | cria caça por busca |
| `/url <link-kabum> Kingston A400 gb=480 alvo=450` | acompanha um produto |
| `/alvo c1 650` | muda preço-alvo |
| `/pausar c1` · `/retomar c1` · `/remover c1` | gerenciar |

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
