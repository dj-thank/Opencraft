from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True, order=True)
class ChunkCoord:
    x: int
    z: int


def chunk_for_position(x: float, z: float, *, chunk_size: float = 32.0) -> ChunkCoord:
    if not math.isfinite(x) or not math.isfinite(z):
        raise ValueError("position must be finite")
    if not math.isfinite(chunk_size) or chunk_size <= 0:
        raise ValueError("chunk_size must be a positive finite number")
    return ChunkCoord(math.floor(x / chunk_size), math.floor(z / chunk_size))
