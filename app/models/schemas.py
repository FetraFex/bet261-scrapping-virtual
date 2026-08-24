from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class TeamModel(BaseModel):
    name: str
    points: Optional[int] = None
    position: Optional[int] = None
    won: Optional[int] = None
    lost: Optional[int] = None
    draw: Optional[int] = None

class EventBetTypeItemModel(BaseModel):
    """Individual odds selection (e.g. '1', 'X', '2')"""
    id: int
    eventBetTypeId: Optional[int] = None
    shortName: str  # "1", "X", "2"
    odds: float
    active: Optional[bool] = None
    bettingAllowed: Optional[bool] = None
    canBeSimulated: Optional[bool] = None

class EventBetTypeModel(BaseModel):
    """A bet type (e.g. '1X2') containing multiple selections"""
    id: int
    eventId: int
    name: str  # e.g. "1X2"
    eventBetTypeItems: List[EventBetTypeItemModel] = []
    betTypeId: Optional[int] = None
    isAsian: Optional[bool] = None
    baseAmount: Optional[float] = None
    minimumAmountIncrement: Optional[float] = None
    maximumAmount: Optional[float] = None
    active: Optional[bool] = None
    bettingAllowed: Optional[bool] = None
    displayPriority: Optional[int] = None
    hasExplanations: Optional[bool] = None
    canBeSimulated: Optional[bool] = None
    isManual: Optional[bool] = None
    allowBetBuilder: Optional[bool] = None

class GoalModel(BaseModel):
    minute: int
    homeScore: float
    awayScore: float

class MatchModel(BaseModel):
    id: int
    entryPointId: int
    round: str
    name: str  # e.g. "Turkiye vs Senegal"
    homeTeam: TeamModel
    awayTeam: TeamModel
    expectedStart: Optional[datetime] = None
    eventBetTypes: List[EventBetTypeModel] = []

class RoundModel(BaseModel):
    expectedStart: Optional[datetime] = None
    expectedEnd: Optional[datetime] = None
    roundNumber: int
    matches: List[MatchModel] = []  # Optional — future rounds may not have matches
    id: Optional[int] = None
    eventCategoryId: Optional[int] = None

class MatchesResponseModel(BaseModel):
    rounds: List[RoundModel]
    betTypes: Optional[list] = None
