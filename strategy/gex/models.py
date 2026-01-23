# strategy/gex/models.py

from pydantic import BaseModel, Field
from typing import List

# --- Models for Gexbot (Option 1) ---

class GexbotStrikeData(BaseModel):
    strike: float
    long_gamma: float
    short_gamma: float

class GexbotResponse(BaseModel):
    success: bool
    data: List[GexbotStrikeData]

# --- Models for Massive Data (Option 3) ---

class MassiveDataGreeks(BaseModel):
    gamma: float

class MassiveDataOption(BaseModel):
    strike: float
    type: str  # 'call' or 'put'
    open_interest: int = Field(alias='openInterest')
    greeks: MassiveDataGreeks

class MassiveDataResponse(BaseModel):
    expiration: str
    options: List[MassiveDataOption]
