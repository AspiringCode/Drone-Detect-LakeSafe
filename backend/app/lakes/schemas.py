from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LakeCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    centroid_lat: float = Field(ge=24.0, le=50.0)
    centroid_lon: float = Field(ge=-125.0, le=-66.0)
    bbox: list[float] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def valid_bbox(self) -> "LakeCreateRequest":
        west, south, east, north = self.bbox
        if not (-125.0 <= west < east <= -66.0 and 24.0 <= south < north <= 50.0):
            raise ValueError("Bounding box must be within the United States")
        if not (west <= self.centroid_lon <= east and south <= self.centroid_lat <= north):
            raise ValueError("Centroid must be inside bounding box")
        return self
