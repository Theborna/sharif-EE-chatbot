from abc import ABC, abstractmethod
from typing import List, Callable, Any
from telegram.ext import BaseHandler

class BaseService(ABC):
    """Base class for all bot services"""
    
    @abstractmethod
    def get_handlers(self) -> List[tuple[BaseHandler, Callable]]:
        """Return list of (handler, callback_function) tuples"""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Service name for identification"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Service description"""
        pass