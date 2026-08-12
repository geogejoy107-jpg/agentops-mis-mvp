"""Research Lab Template v1 domain implementation.

The package intentionally contains no database.  Every persisted record and
event is written through :class:`ResearchCorePort`, whose implementation is
owned by MIS Core.  This keeps Research domain behavior independently
testable without creating a second Task/Run/Approval/Audit authority.
"""

from .contracts import (
    ClaimStatus,
    ExperimentStage,
    JobAttemptState,
    ResearchError,
    ResearchProtocol,
    TrialState,
)
from .repository import ResearchRepository
from .service import ResearchService

__all__ = [
    "ClaimStatus",
    "ExperimentStage",
    "JobAttemptState",
    "ResearchError",
    "ResearchProtocol",
    "ResearchRepository",
    "ResearchService",
    "TrialState",
]

__version__ = "1.0.0"
