from pydantic import BaseModel
from typing import Optional
from enum import Enum


class AspectRatio(str, Enum):
    AUTO = "auto"
    RATIO_1_1 = "1:1"
    RATIO_16_9 = "16:9"
    RATIO_9_16 = "9:16"
    RATIO_4_3 = "4:3"
    RATIO_3_4 = "3:4"
    RATIO_3_2 = "3:2"
    RATIO_2_3 = "2:3"


class Resolution(str, Enum):
    RES_480P = "480p"
    RES_720P = "720p"


class GenerateRequest(BaseModel):
    prompt: str
    image_data: Optional[str] = None
    duration: int = 15
    aspect_ratio: AspectRatio = AspectRatio.AUTO
    resolution: Resolution = Resolution.RES_720P
