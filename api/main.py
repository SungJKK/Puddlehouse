from contextlib import asynccontextmanager
from fastapi import FastAPI
from catalog.manager import CatalogManager, SchemaEvolutionError
from query.engine import QueryEngine
from api.deps import init_shared
from api.errors import (
    key_error_handler,
    schema_evolution_handler,
    value_error_handler,
    internal_error_handler,
)
from api.routers import tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    catalog = CatalogManager()
    engine = QueryEngine(catalog)
    init_shared(catalog, engine)
    yield


app = FastAPI(title="Lakehouse API", version="1.0.0", lifespan=lifespan)

app.add_exception_handler(KeyError, key_error_handler)
app.add_exception_handler(SchemaEvolutionError, schema_evolution_handler)
app.add_exception_handler(ValueError, value_error_handler)
app.add_exception_handler(Exception, internal_error_handler)

app.include_router(tables.router, prefix="/api/v1")
