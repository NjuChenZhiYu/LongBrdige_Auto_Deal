from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

class BaseMonitor(ABC):
    """
    Abstract base class for market monitors.
    """
    
    @abstractmethod
    async def start(self):
        """Start the monitor service."""
        pass

    @abstractmethod
    async def stop(self):
        """Stop the monitor service."""
        pass
