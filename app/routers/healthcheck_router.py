from fastapi import APIRouter, Request
from app.routers.healthchecks.fastapi_healthcheck import HealthCheckFactory, healthCheckRoute
from app.routers.healthchecks.fastapi_healthcheck_sqlalchemy import HealthCheckSQLAlchemy
from app.core.config import settings
from fastapi import HTTPException
from app.log.logging import logger

router = APIRouter(tags=["healthcheck"])

@router.get(
    "/healthcheck",
    description="Health check endpoint",
    responses={
        200: {"description": "Health check passed"},
        500: {"description": "Health check failed"}
    }
)
async def health_check(withlog: bool = False):
    if withlog:
        logger.debug("healthcheck debug log")
        logger.info("healthcheck info log")
        logger.warning("healthcheck warning log")
        logger.error("healthcheck error log")
        logger.critical("healthcheck critical log")

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
        logger.error("This is an error log")
        raise HTTPException(status_code=500, detail=str(e))
        
