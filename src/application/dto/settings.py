from typing import Optional

from pydantic import Field

from .base import TrackableDTO


class SettingsDTO(TrackableDTO):
    id: Optional[int] = Field(default=None, frozen=True)
