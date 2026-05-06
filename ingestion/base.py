from abc import ABC, abstractmethod

from ingestion.schema import LocationInput, SignalCreate


class BaseIngester(ABC):
    source: str

    @abstractmethod
    async def fetch(self, location: LocationInput) -> list[SignalCreate]:
        raise NotImplementedError
