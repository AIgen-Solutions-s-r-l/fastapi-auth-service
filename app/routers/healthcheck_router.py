from fastapi import APIRouter, Request, Depends
from fastapi import HTTPException
import time
from typing import Dict, Any

from app.routers.healthchecks.fastapi_healthcheck import HealthCheckFactory, healthCheckRoute
from app.routers.healthchecks.fastapi_healthcheck_sqlalchemy import HealthCheckSQLAlchemy
from app.core.config import settings
from app.log.logging import logger
from app.core.database import check_db_health, get_db, _in_degraded_mode, _connection_error_count
from app.schemas.health_schemas import (
    HealthCheckResponse, HealthStatus, ComponentHealth, ServiceStatus,
    ReadinessResponse, LivenessResponse
)

# Flag to track shutdown state for readiness probe
_is_shutting_down = False


def set_shutdown_state(shutting_down: bool):
    """Set the shutdown state for health checks."""
    global _is_shutting_down
    _is_shutting_down = shutting_down

router = APIRouter(tags=["Health"])

# Track service start time for uptime calculation
_service_start_time = time.time()

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


@router.get(
    "/healthcheck/ready",
    response_model=ReadinessResponse,
    summary="Kubernetes readiness probe",
    description="Check if the service is ready to accept traffic",
    responses={
        200: {"description": "Service is ready"},
        503: {"description": "Service is not ready"}
    }
)
async def readiness_probe():
    """
    Kubernetes-style readiness probe.

    Checks if all required dependencies are available and the service
    can accept traffic. Returns 503 if any critical check fails or if
    the service is shutting down (for graceful shutdown support).
    """
    checks = {}

    # Check if service is shutting down (for graceful shutdown)
    checks["not_shutting_down"] = not _is_shutting_down
    if _is_shutting_down:
        logger.info(
            "Readiness check returning not ready due to shutdown",
            event_type="readiness_shutdown"
        )

    # Check database connectivity
    try:
        db_health = await check_db_health()
        checks["database"] = db_health.get("status") == "healthy"
    except Exception:
        checks["database"] = False

    # Check configuration is valid
    checks["configuration"] = bool(settings.secret_key and settings.database_url)

    # Service is ready if all checks pass
    is_ready = all(checks.values())

    if not is_ready:
        logger.warning(
            "Readiness check failed",
            event_type="readiness_check_failed",
            checks=checks
        )
        raise HTTPException(
            status_code=503,
            detail=ReadinessResponse(ready=False, checks=checks).model_dump()
        )

    return ReadinessResponse(ready=True, checks=checks)


@router.get(
    "/healthcheck/live",
    response_model=LivenessResponse,
    summary="Kubernetes liveness probe",
    description="Check if the service is alive",
    responses={
        200: {"description": "Service is alive"}
    }
)
async def liveness_probe():
    """
    Kubernetes-style liveness probe.

    Simple check to verify the service process is running and responsive.
    Does not check external dependencies.
    """
    uptime = round(time.time() - _service_start_time, 2)
    return LivenessResponse(alive=True, uptime_seconds=uptime)


@router.get(
    "/healthcheck/full",
    response_model=HealthCheckResponse,
    summary="Comprehensive health check",
    description="Detailed health check of all service components",
    responses={
        200: {"description": "Health check completed"},
        503: {"description": "Service is unhealthy"}
    }
)
async def full_health_check():
    """
    Comprehensive health check that tests all service components.

    Returns detailed status for each component including response times.
    """
    start_time = time.time()
    components = []
    overall_status = HealthStatus.HEALTHY

    # Check database
    try:
        db_start = time.time()
        db_health = await check_db_health()
        db_time = round((time.time() - db_start) * 1000, 2)

        db_status = ServiceStatus.UP if db_health.get("status") == "healthy" else ServiceStatus.DEGRADED
        if db_health.get("status") == "unhealthy":
            db_status = ServiceStatus.DOWN
            overall_status = HealthStatus.UNHEALTHY
        elif db_status == ServiceStatus.DEGRADED:
            if overall_status != HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.DEGRADED

        components.append(ComponentHealth(
            name="database",
            status=db_status,
            response_time_ms=db_time,
            message=db_health.get("error") if db_status != ServiceStatus.UP else "Connection successful",
            details={"in_degraded_mode": _in_degraded_mode, "error_count": _connection_error_count}
        ))
    except Exception as e:
        components.append(ComponentHealth(
            name="database",
            status=ServiceStatus.DOWN,
            message=str(e)
        ))
        overall_status = HealthStatus.UNHEALTHY

    # Check Stripe configuration (not actual API call to avoid rate limits)
    stripe_configured = bool(settings.STRIPE_SECRET_KEY)
    components.append(ComponentHealth(
        name="stripe",
        status=ServiceStatus.UP if stripe_configured else ServiceStatus.DEGRADED,
        message="Configured" if stripe_configured else "Not configured"
    ))
    if not stripe_configured and overall_status == HealthStatus.HEALTHY:
        overall_status = HealthStatus.DEGRADED

    # Check email configuration
    email_configured = bool(settings.SENDGRID_API_KEY)
    components.append(ComponentHealth(
        name="email",
        status=ServiceStatus.UP if email_configured else ServiceStatus.DEGRADED,
        message="Configured" if email_configured else "Not configured"
    ))

    check_time_ms = round((time.time() - start_time) * 1000, 2)
    uptime = round(time.time() - _service_start_time, 2)

    response = HealthCheckResponse(
        status=overall_status,
        version="1.0.0",
        uptime_seconds=uptime,
        check_time_ms=check_time_ms,
        components=components
    )

    if overall_status == HealthStatus.UNHEALTHY:
        raise HTTPException(status_code=503, detail=response.model_dump())

    return response
