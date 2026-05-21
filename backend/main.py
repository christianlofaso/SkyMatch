from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cache import init_db
from routes.run import router as run_router
from routes.profile import router as profile_router
from routes.connections import router as connections_router
from routes.internships import router as internships_router

app = FastAPI(title="Pathfinder API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    init_db()


app.include_router(run_router)
app.include_router(profile_router)
app.include_router(connections_router)
app.include_router(internships_router)


@app.get("/health")
def health():
    return {"status": "ok"}
