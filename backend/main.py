import os
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import stocks, sentiment, options, news, screener, insider, earnings, market, ai, simulator

app = FastAPI(
    title="Daydream Believer — Day Trader Assistant API",
    description="Aggregates market data, technical analysis, sentiment, options flow, news, and insider activity.",
    version="1.0.0",
)

_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stocks.router)
app.include_router(sentiment.router)
app.include_router(options.router)
app.include_router(news.router)
app.include_router(screener.router)
app.include_router(insider.router)
app.include_router(earnings.router)
app.include_router(market.router)
app.include_router(ai.router)
app.include_router(simulator.router)


@app.get("/")
async def root():
    return {"status": "ok", "message": "Daydream Believer API running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
