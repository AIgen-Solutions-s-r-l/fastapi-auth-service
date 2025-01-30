from fastapi import APIRouter
from app.routers.healthchecks.fastapi_healthcheck import HealthCheckFactory, healthCheckRoute
from app.routers.healthchecks.fastapi_healthcheck_sqlalchemy import HealthCheckSQLAlchemy
from app.core.config import Settings
from fastapi import HTTPException

router = APIRouter(tags=["healthcheck"])
settings = Settings()

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
            connection_uri="postgresql+asyncpg://testuser:testpassword@172.17.0.1:5432/main_db",
            alias='postgres db',
            tags=('postgres', 'db', 'sql01')
        )
    )
    
    try:
        return await healthCheckRoute(factory=_healthChecks)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
