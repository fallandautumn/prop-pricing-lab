from fastapi import FastAPI

from app.api.routers import rooms

app = FastAPI(title="prop-arbitrage-v2", version="0.1.0")

app.include_router(rooms.router)


@app.get("/health")
def health():
    return {"status": "ok"}
