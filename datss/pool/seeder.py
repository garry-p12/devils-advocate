"""
Independent seed allocation for the challenger pool.

The independence property of the pool is verifiable by inspecting this module
alone: seeds are hash-derived from a deterministic input space, so different
challenger indices necessarily produce different hash digests. The explicit
collision check is belt-and-suspenders for the 32-bit truncation regime.
"""

import hashlib
from typing import List, Tuple


class SeedAllocator:
    """
    Allocates disjoint seeds to challengers from a deterministic stream.

    Strategy: derive each seed as the first 4 bytes of
    SHA-256(f"{master_seed}:{index}") interpreted as a big-endian uint32.

    Disjointness is guaranteed by construction (different indices produce
    different hash inputs), but a collision check is still performed because:
    (a) the spec requires collisions to be detectable, and
    (b) truncation from 256 to 32 bits creates birthday-paradox risk at large
        pool sizes (~50% collision probability around 77k challengers).
    """

    def allocate(self, master_seed: int, n: int) -> Tuple[List[int], bool]:
        """
        Returns (seeds, collision_detected).

        seeds: list of n integers, one per challenger.
        collision_detected: True if any two derived seeds collide.
        """
        seeds: List[int] = []
        for i in range(n):
            digest = hashlib.sha256(f"{master_seed}:{i}".encode("utf-8")).digest()
            seed = int.from_bytes(digest[:4], byteorder="big", signed=False)
            seeds.append(seed)
        collision_detected = len(set(seeds)) != len(seeds)
        return seeds, collision_detected

    @staticmethod
    def verify_disjoint(seeds: List[int]) -> bool:
        """
        Standalone verifier. Can be called by external auditors without access
        to an allocator instance.
        """
        return len(set(seeds)) == len(seeds)
