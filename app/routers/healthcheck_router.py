from fastapi import APIRouter, Request, Depends
from fastapi import HTTPException
import time
from typing import Dict, Any

from app.routers.healthchecks.fastapi_healthcheck import HealthCheckFactory, healthCheckRoute
from app.routers.healthchecks.fastapi_healthcheck_sqlalchemy import HealthCheckSQLAlchemy
from app.core.config import settings
from app.log.logging import logger
from app.core.database import check_db_health, get_db, _in_degraded_mode, _connection_error_count

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


@router.get(
    "/healthcheck/db",
    description="Enhanced database health check with detailed status information",
    responses={
        200: {"description": "Database health check information"},
        500: {"description": "Database check failed critically"}
    }
)
async def db_health_check():
    """
    Enhanced database health check endpoint that provides detailed status
    information about the database connection, including connection time,
    error states, and degraded mode status.
    
    Returns:
        Dict[str, Any]: Detailed database health information
    """
    start_time = time.time()
    
    try:
        # Use our specialized db health check function
        db_health = await check_db_health()
        
        # Calculate total check time
        check_time_ms = round((time.time() - start_time) * 1000, 2)
        
        # Add service information
        response = {
            **db_health,
            "check_time_ms": check_time_ms,
            "service_state": "degraded" if _in_degraded_mode else "normal",
            "recent_connection_errors": _connection_error_count,
        }
        
        # Set response status code based on health status
        if db_health.get("status") == "healthy":
            logger.info(
                "Database health check passed",
                event_type="db_healthcheck_success",
                response_time_ms=db_health.get("response_time_ms", 0),
                check_time_ms=check_time_ms
            )
        else:
            logger.warning(
                "Database health check returned degraded status",
                event_type="db_healthcheck_degraded",
                status=db_health.get("status"),
                error=db_health.get("error", "Unknown error"),
                check_time_ms=check_time_ms
            )
            
        return response
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}", event_type="db_healthcheck_error", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database health check failed: {str(e)}")
