from fastapi import FastAPI

app = FastAPI(
    title="Elliott API Service",
    version="0.1.0",
    description="REST API for Elliott read-only commands",
)


@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}


from elliott_service.routers import advisory, bugs, tasks  # noqa: E402

app.include_router(bugs.router)
app.include_router(tasks.router)
app.include_router(advisory.router)
