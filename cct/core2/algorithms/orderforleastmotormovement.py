from typing import Tuple, List, TypeVar

T = TypeVar("T")


def orderForLeastMotorMovement(positions: List[Tuple[T, Tuple[float, float]]], startposition: Tuple[float, float]) -> List[T]:
    xpositions = set([p[1][0] for p in positions] + [startposition[0]])
    ypositions = set([p[1][1] for p in positions] + [startposition[1]])

    if len(xpositions) < len(ypositions):
        # there are more unique Y coordinates than X coordinates: go by X coordinates first
        slow = 0
        fast = 1
    else:
        slow = 1
        fast = 0
    # put the slowest moving sample (not starting position!) coordinates first in increasing order
    slow_ordered = sorted(
        set([p[1][slow] for p in positions if p[1][slow] != startposition[slow]]))
    if not slow_ordered:
        # only one position, which is the start position:
        slow_ordered = []
    else:
        # see which end we must start. Start from that end which is nearest to the empty beam measurement
        if abs(slow_ordered[-1] - startposition[slow]) < abs(slow_ordered[0] - startposition[slow]):
            slow_ordered = reversed(slow_ordered)
        slow_ordered = list(slow_ordered)
    lastfastcoord = startposition[fast]
    objects_ordered = []
    for slowpos in [startposition[slow]] + slow_ordered:
        # sort those samples which have this X coordinate first by increasing Y coordinate
        objects = sorted([p for p in positions if p[1][slow] == slowpos],
                         key = lambda p:p[1][fast])
        if not objects:
            # no samples with this slow coordinate
            continue
        # see which end of the fastest coordinate is nearest to the last fast coordinate position
        if abs(objects[0][1][fast] - lastfastcoord) < abs(objects[-1][1][fast] - lastfastcoord):
            objects = reversed(objects)
        objects = list(objects)
        objects_ordered.extend(objects)
        lastfastcoord = objects_ordered[-1][1][fast]
    assert len(objects_ordered) == len(positions)
    return [o[0] for o in objects_ordered]
