from fastapi import FastAPI

app = FastAPI(title="precim", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mascote": "🐷 de olho nas ofertas"}
