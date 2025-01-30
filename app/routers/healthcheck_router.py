from fastapi import FastAPI
from fastapi_sqlalchemy import DBSessionMiddleware
from healthchecks.fastapi_healthcheck import HealthCheckFactory, healthCheckRoute
from healthchecks.fastapi_healthcheck_sqlalchemy import HealthCheckSQLAlchemy
from app.core.config import Settings


app = FastAPI()
settings = Settings()

# Bring SQLAlchemy online first.
app.add_middleware(DBSessionMiddleware, db_url=settings.database_url)

_healthChecks = HealthCheckFactory()
_healthChecks.add(
    HealthCheckSQLAlchemy(
        # The name of the object for your reference
        alias='postgres db',  
        tags=('postgres', 'db', 'sql01')
    )
)

app.add_api_route('/health', endpoint=healthCheckRoute(factory=_healthChecks))