"""Health check response schemas."""

from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    """Health status enumeration."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ServiceStatus(str, Enum):
    """Individual service status."""
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class ComponentHealth(BaseModel):
    """Health status of an individual component."""
    name: str = Field(..., description="Component name")
    status: ServiceStatus = Field(..., description="Component status")
    response_time_ms: Optional[float] = Field(None, description="Response time in milliseconds")
    message: Optional[str] = Field(None, description="Additional status message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "database",
                "status": "up",
                "response_time_ms": 5.2,
                "message": "Connection successful"
            }
        }
    }


class HealthCheckResponse(BaseModel):
    """Comprehensive health check response."""
    status: HealthStatus = Field(..., description="Overall service health status")
    version: str = Field(..., description="Service version")
    uptime_seconds: Optional[float] = Field(None, description="Service uptime in seconds")
    check_time_ms: float = Field(..., description="Total health check duration in milliseconds")
    components: List[ComponentHealth] = Field(default=[], description="Individual component health statuses")

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "healthy",
                "version": "1.0.0",
                "uptime_seconds": 3600.5,
                "check_time_ms": 15.3,
                "components": [
                    {
                        "name": "database",
                        "status": "up",
                        "response_time_ms": 5.2
                    },
                    {
                        "name": "stripe",
                        "status": "up",
                        "response_time_ms": 120.5
                    }
                ]
            }
        }
    }


class ReadinessResponse(BaseModel):
    """Kubernetes-style readiness probe response."""
    ready: bool = Field(..., description="Whether the service is ready to accept traffic")
    checks: Dict[str, bool] = Field(default={}, description="Individual readiness checks")

    model_config = {
        "json_schema_extra": {
            "example": {
                "ready": True,
                "checks": {
                    "database": True,
                    "configuration": True
                }
            }
        }
    }


class LivenessResponse(BaseModel):
    """Kubernetes-style liveness probe response."""
    alive: bool = Field(..., description="Whether the service is alive")
    uptime_seconds: Optional[float] = Field(None, description="Service uptime in seconds")

    model_config = {
        "json_schema_extra": {
            "example": {
                "alive": True,
                "uptime_seconds": 3600.5
            }
        }
    }
