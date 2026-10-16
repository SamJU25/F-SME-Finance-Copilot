from abc import ABC, abstractmethod
from typing import List

from services.decision.types import DecisionDomain, DecisionRequest, DecisionResult


class AbstractDecisionEngine(ABC):
    """Abstract interface defining a pluggable decision engine adapter."""

    @property
    @abstractmethod
    def engine_id(self) -> str:
        """Unique identifier and version of the decision engine backend."""
        pass

    @property
    @abstractmethod
    def supported_domains(self) -> List[DecisionDomain]:
        """List of domains this engine is qualified to evaluate."""
        pass

    def can_evaluate(self, request: DecisionRequest) -> bool:
        """Check if this engine can process the given decision request."""
        return request.domain in self.supported_domains

    @abstractmethod
    def evaluate(self, request: DecisionRequest) -> DecisionResult:
        """Evaluate the decision request and produce a calibrated DecisionResult."""
        pass
