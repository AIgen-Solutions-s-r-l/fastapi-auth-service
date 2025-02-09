from app.routers.healthchecks.fastapi_healthcheck.service import HealthCheckBase
from app.routers.healthchecks.fastapi_healthcheck.enum import HealthCheckStatusEnum
from app.routers.healthchecks.fastapi_healthcheck.domain import HealthCheckInterface
from typing import List
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text
from app.log.logging import logger
from app.core.config import settings

class HealthCheckSQLAlchemy(HealthCheckBase, HealthCheckInterface):
    _connection_uri: str
    _tags: List[str]

    def __init__(self, connection_uri: str, alias: str, tags: List[str]) -> None:
        self._connection_uri = connection_uri
        self._alias = alias
        self._tags = tags
        self._engine = create_async_engine(self._connection_uri, future=True)

    async def __checkHealth__(self) -> HealthCheckStatusEnum:
        res = HealthCheckStatusEnum.UNHEALTHY
        async with AsyncSession(self._engine) as session:
            try:
                sql = text("SELECT 1")
                result = await session.execute(sql)
                if result.scalar() == 1:
                    res = HealthCheckStatusEnum.HEALTHY
            except Exception as e:
                logger.exception(f"Database health check failed: {e}")
        return res
