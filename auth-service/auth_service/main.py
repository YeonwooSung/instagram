from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from sqlmodel import SQLModel
import sys

# Add the parent directory to the sys.path list
sys.path.append(".")
sys.path.append("..")

# import custom modules
from auth_service.utils import limiter, Logger
from auth_service.utils.db import engine
from auth_service.middlewares import RequestLogger, RequestID
from auth_service.api import (
    subscription_router,
    token_router,
    users_router,
)


app = FastAPI(title="Movie API server")
app.state.limiter = limiter  # add rate limiter

# add middlewares
app.add_middleware(
    ProxyHeadersMiddleware, trusted_hosts="*"
)  # add proxy headers to prevent logging IP address of the proxy server instead of the client
app.add_middleware(GZipMiddleware, minimum_size=500)  # add gzip compression

# add custom middlewares
app.add_middleware(RequestLogger)
app.add_middleware(RequestID)


@app.on_event("startup")
def on_startup() -> None:
    Logger().get_logger() # init logger
    SQLModel.metadata.create_all(engine)

@app.on_event("shutdown")
def on_shutdown() -> None:
    pass


# add routers
app.include_router(subscription_router)
app.include_router(token_router)
app.include_router(users_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run('main:app', port=8000, reload=True)
