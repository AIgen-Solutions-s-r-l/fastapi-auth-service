# PostgreSQL Database Error Handling Strategy

This document outlines the comprehensive strategy implemented for handling PostgreSQL database connection failures in the Auth Service.

## Overview

The Auth Service implements a robust error handling approach for database connections, providing:

- Specialized exception types for different error scenarios
- Detailed error logging with structured data
- User-friendly error messages with appropriate HTTP status codes
- Connection retry mechanism with exponential backoff
- Service degradation detection and graceful fallback
- Health monitoring endpoints for system observability

## Error Types and Classification

### Database Error Codes

The system classifies PostgreSQL errors into the following categories:

| Error Type | Description | HTTP Status | Recovery Approach |
|------------|-------------|-------------|-------------------|
| `CONNECTION_REFUSED` | Initial connection to database server failed | 503 | Automatic retry with backoff |
| `CONNECTION_LOST` | Established connection was lost during operation | 503 | Automatic retry with backoff |
| `CONNECTION_TIMEOUT` | Connection attempt timed out | 503 | Automatic retry with backoff |
| `AUTH_FAILED` | Invalid database credentials | 500 | Manual intervention required |
| `INSUFFICIENT_RESOURCES` | Database server out of memory/connections | 503 | Automatic retry with backoff |
| `INTEGRITY_ERROR` | Constraint violation | 409 | Application-specific handling |
| `DATA_ERROR` | Invalid data for operation | 400 | Application-specific handling |
| `SYSTEM_ERROR` | Database system error | 500 | Manual investigation required |
| `UNKNOWN_ERROR` | Unclassified error | 500 | Default error handling |

PostgreSQL error codes are mapped to these internal error types, ensuring consistent handling across the application.

## Retry Mechanism with Exponential Backoff

For transient errors (connection issues, resource limitations), the system implements an exponential backoff mechanism:

```
Initial delay: 0.5 seconds
Backoff factor: 2.0
Maximum delay: 30.0 seconds
Maximum retries: 3
Jitter: 20% random variation
```

This means:
- First retry: ~0.5 seconds
- Second retry: ~1.0 seconds
- Third retry: ~2.0 seconds

Jitter is added to prevent the "thundering herd" problem when multiple instances retry simultaneously.

## Service Degradation Detection

The system tracks database connection errors to detect service degradation:

- Error count threshold: 3 errors within 5 minutes
- When threshold is exceeded: enters "degraded mode"
- Degradation reset: After successful connection and 5 minutes without errors

In degraded mode, the system:
- Continues to attempt database operations with retries
- Logs additional warnings for monitoring alerts
- Exposes degradation status via health check endpoints

## Error Logging

All database errors are logged with structured data to facilitate analysis:

```json
{
  "event_type": "db_session_error",
  "error_type": "ConnectionRefusedError",
  "error_details": "[Errno 111] Connect call failed ('172.20.8.100', 5432)",
  "classified_as": "ConnectionRefusedError",
  "attempt": 2,
  "max_retries": 3,
  "in_degraded_mode": true,
  "error_count": 4,
  "pg_code": "08001"  // When available
}
```

Logging consistently includes:
- Original error message and exception type
- Classified error type for consistent handling
- PostgreSQL error code when available
- Connection attempt count and retry information
- System degradation status

## Monitoring Integration

### Health Check Endpoint

The system provides a dedicated database health check endpoint at `/healthcheck/db` that returns:

```json
{
  "status": "healthy|degraded|unhealthy",
  "response_time_ms": 12.34,
  "check_time_ms": 15.67,
  "service_state": "normal|degraded",
  "recent_connection_errors": 2,
  "message": "Database connection successful",
  "error": "Error message if applicable",
  "error_type": "Error type if applicable",
  "error_details": { /* Additional details */ }
}
```

This endpoint should be monitored by your infrastructure monitoring system (e.g., Prometheus, Datadog).

### Log-based Alerts

Configure alerts based on the following log patterns:

1. Immediate critical alerts:
   - `event_type="db_degraded_mode_enter"`
   - `error_type="DatabaseAuthError"`

2. Warning alerts:
   - Multiple `event_type="db_session_error"` within 5 minutes
   - `event_type="db_operation_retry"` with high frequency

## Troubleshooting Procedures

When database connection issues occur, follow these steps:

1. **Check Database Health**
   - Query the `/healthcheck/db` endpoint
   - Review error details and status

2. **Verify Network Connectivity**
   - Ensure database server is reachable from application servers
   - Check for network policy/firewall issues
   - Verify correct database URL in configuration

3. **Examine Database Logs**
   - Check PostgreSQL server logs for errors
   - Look for connection limits, memory issues, or authentication failures

4. **Review Application Logs**
   - Search for `event_type="db_session_error"` and related events
   - Check error classification and PostgreSQL error codes
   - Note connection retry attempts and timing

5. **Check Resource Utilization**
   - Verify database server has sufficient resources (CPU, memory)
   - Check connection pool utilization
   - Look for long-running queries that might block connections

6. **Service Recovery**
   - Restart database service if needed
   - Scale up resources if resource constraints are the issue
   - Update credentials if authentication errors are occurring
   - Adjust connection pool settings if connection limits are reached

## Configuration Options

The following environment variables control database connection behavior:

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_POOL_SIZE` | 5 | Maximum number of connections in the pool |
| `DB_MAX_OVERFLOW` | 10 | Maximum number of connections that can be created beyond pool size |
| `DB_POOL_TIMEOUT` | 30 | Seconds to wait for a connection from the pool |
| `DB_POOL_RECYCLE` | 1800 | Seconds after which a connection is recycled (30 minutes) |

## Implementation Details

The enhanced database error handling is implemented across these files:

1. `app/core/db_exceptions.py` - Specialized exception types
2. `app/core/db_utils.py` - Retry logic and error classification
3. `app/core/database.py` - Connection management and degradation tracking
4. `app/core/error_handlers.py` - FastAPI exception handlers
5. `app/routers/healthcheck_router.py` - Health check endpoints

## Future Improvements

Consider the following future enhancements:

1. Circuit breaker pattern implementation for complete database outages
2. Read-only mode operation when write operations fail but reads succeed
3. Caching layer for critical data to serve during database unavailability
4. Asynchronous job queue for operations that can be deferred during outages
5. Automatic alerting integration with PagerDuty or similar service