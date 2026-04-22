from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.routes import templates, processing, logs, validation, models

app = FastAPI(title="Excel2DB")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(templates.router)
app.include_router(processing.router)
app.include_router(logs.router)
app.include_router(validation.router)
app.include_router(models.router)


@app.get("/")
async def root():
    return RedirectResponse(url="/process")
