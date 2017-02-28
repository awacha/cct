def pickfromlist(sequence):
    yield []
    for i in range(len(sequence)):
        for l in pickfromlist(sequence[i+1:]):
            yield [sequence[i]]+l

def estimate_worksize_C(spacers, pinholes, float sealringwidth):
    l_seen = []
    count = 0
    lastpulse = 0

    for l1_parts in pickfromlist(spacers):
        l1 = len(l1_parts) * sealringwidth + sum(l1_parts)
        spacers_remaining = list(spacers[:])
        for s in l1_parts:
            spacers_remaining.remove(s)
        for l2_parts in pickfromlist(spacers_remaining):
            l2 =len(l2_parts) * sealringwidth + sum(l2_parts)
            if (l1, l2) in l_seen:
                continue
            l_seen.append((l1, l2))
            count += 1
    return count * len(pinholes) ** 2
