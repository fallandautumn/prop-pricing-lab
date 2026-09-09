from fastapi import FastAPI

from app.api.routers import rooms

app = FastAPI(title="prop-pricing-lab", version="0.1.0")

app.include_router(rooms.router)


@app.get("/health")
def health():
    return {"status": "ok"}
