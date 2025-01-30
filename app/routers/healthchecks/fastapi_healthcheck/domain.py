from abc import ABC, abstractmethod, classmethod
from typing import List, Optional
from .enum import HealthCheckStatusEnum


class HealthCheckInterface(ABC):
    _connectionUri: str
    _alias: str
    _tags: Optional[List[str]]

    @classmethod
    @abstractmethod
    def setConnectionUri(self, value: str) -> None:
        """ConnectionUri will be the value that is requested to check the health of an endpoint."""
        pass

    @classmethod
    @abstractmethod
    def setName(self, value: str) -> None:
        """The Name is the friendly name of the health object."""
        pass

    @classmethod
    @abstractmethod
    def getService(self) -> str:
        """The Service is a definition of what kind of endpoint we are checking on."""
        pass

    @classmethod
    @abstractmethod
    def getTags(self) -> List[str]:
        pass

    @classmethod
    @abstractmethod
    def __checkHealth__(self) -> HealthCheckStatusEnum:
        """Requests data from the endpoint to validate health."""
        pass
