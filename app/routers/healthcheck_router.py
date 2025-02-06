from fastapi import APIRouter
from app.routers.healthchecks.fastapi_healthcheck import HealthCheckFactory, healthCheckRoute
from app.routers.healthchecks.fastapi_healthcheck_sqlalchemy import HealthCheckSQLAlchemy
from app.core.config import settings
from fastapi import HTTPException

router = APIRouter(tags=["healthcheck"])

@router.get(
    "/healthcheck",
    description="Health check endpoint",
    responses={
        200: {"description": "Health check passed"},
        500: {"description": "Health check failed"}
    }
)
async def health_check():
    
    _healthChecks = HealthCheckFactory()
    _healthChecks.add(
        HealthCheckSQLAlchemy(
            connection_uri=settings.database_url,
            alias='postgres db',
            tags=('postgres', 'db', 'sql01')
        )
    )
    
    try:
        return await healthCheckRoute(factory=_healthChecks)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
