import collections
import math
from typing import Sequence, Union, SupportsFloat, Optional

from .estimateworksize import pickfromlist


class PinholeConfiguration(object):
    """This class represents the collimation geometry of a conventional SAS instrument."""

    def __init__(self, L1: Union[Sequence, SupportsFloat], L2: Union[Sequence, SupportsFloat], D1: float, D2: float,
                 ls: float, lbs: float, sd: float, mindist_l1: float = 0.0, mindist_l2: float = 0.0,
                 sealringwidth: float = 0.0, wavelength: float = 0.15418):
        if not isinstance(L1, collections.Iterable):
            L1 = [L1]
        self.l1_elements = L1
        if not isinstance(L2, collections.Iterable):
            L2 = [L2]
        self.l2_elements = L2
        self.mindist_l1 = mindist_l1
        self.mindist_l2 = mindist_l2
        self.sealringwidth = sealringwidth
        self.r1 = D1 * 0.5e-3
        self.r2 = D2 * 0.5e-3
        self.ls = ls
        self.lbs = lbs
        self.sd = sd
        self.wavelength = wavelength

    def __copy__(self) -> 'PinholeConfiguration':
        return PinholeConfiguration(
            self.l1_elements, self.l2_elements, self.D1, self.D2, self.ls,
            self.lbs, self.sd, self.mindist_l1, self.mindist_l2,
            self.sealringwidth, self.wavelength)

    copy = __copy__

    @property
    def l1(self) -> float:
        if isinstance(self.l1_elements, collections.Sequence):
            return float(sum(self.l1_elements) +
                         self.sealringwidth * (1 + len(self.l1_elements)) +
                         self.mindist_l1)
        else:
            return self.l1_elements

    @l1.setter
    def l1(self, value):
        self.l1_elements = value

    @property
    def l2(self) -> float:
        if isinstance(self.l2_elements, collections.Sequence):
            return float(sum(self.l2_elements) +
                         self.sealringwidth * (1 + len(self.l2_elements)) +
                         self.mindist_l2)
        else:
            return self.l2_elements

    @l2.setter
    def l2(self, value):
        self.l2_elements = value

    @property
    def D1(self) -> float:
        return 2000 * self.r1

    @D1.setter
    def D1(self, value):
        self.r1 = value * 0.5e-3

    @property
    def D2(self) -> float:
        return 2000 * self.r2

    @D2.setter
    def D2(self, value):
        self.r2 = value * 0.5e-3

    @property
    def D3(self) -> float:
        return 2000 * self.r3

    @property
    def Dsample_direct(self) -> float:
        return 2 * self.rs_direct

    @property
    def Dsample_parasitic(self) -> float:
        return 2 * self.rs_parasitic

    Dsample = Dsample_direct

    @property
    def Dbs_parasitic(self) -> float:
        return 2 * self.rbs_parasitic

    @property
    def Dbs_direct(self) -> float:
        return 2 * self.rbs_direct

    Dbs = Dbs_parasitic

    @property
    def Ddet_parasitic(self) -> float:
        return 2 * self.rdet_parasitic

    @property
    def Ddet_direct(self) -> float:
        return 2 * self.rdet_direct

    Ddet = Ddet_parasitic

    @property
    def l3(self) -> float:
        return self.sd + self.ls

    @property
    def r3(self) -> float:
        return self.r2 + (self.r1 + self.r2) * self.l2 / self.l1

    @property
    def rs_direct(self) -> float:
        return self.r2 + (self.r1 + self.r2) * (self.l2 + self.ls) / self.l1

    @property
    def rs_parasitic(self) -> float:
        return self.rs_parasitic1(None)

    rs = rs_direct

    @property
    def rbs_direct(self) -> float:
        return (self.r2 + (self.r1 + self.r2) * (self.l2 + self.l3 -
                                                 self.lbs) / self.l1)

    @property
    def rbs_parasitic(self) -> float:
        return self.rbs_parasitic1(None)

    rbs = rbs_parasitic

    @property
    def rdet_direct(self) -> float:
        return (self.r2 + (self.r1 + self.r2) * (self.l2 + self.l3) /
                self.l1)

    @property
    def rdet_parasitic(self) -> float:
        return self.rdet_parasitic1(None)

    rdet = rdet_parasitic

    @property
    def tantthmin(self) -> float:
        return (self.rbs_parasitic / (self.sd - self.lbs))

    @property
    def qmin(self) -> float:
        return (4 * math.pi * math.sin(0.5 * math.atan(self.tantthmin)) /
                self.wavelength)

    @property
    def dmax(self) -> float:
        return 2 * math.pi / self.qmin

    @property
    def intensity(self) -> float:
        return self.D1 ** 2 * self.D2 ** 2 / self.l1 ** 2 / 64 * math.pi

    @property
    def alpha(self) -> float:
        return math.atan2((self.r2 + self.r1), self.l1)

    @property
    def dspheremax(self) -> float:
        return (5 / 3.) ** 0.5 * 2 * self.Rgmax

    @property
    def Rgmax(self) -> float:
        return 1 / self.qmin

    def rdet_parasitic1(self, r3:Optional[float]=None) -> float:
        if r3 is None:
            r3 = self.r3
        return ((self.r2 + r3) * (self.l2 + self.l3) /
                self.l2 - self.r2)

    def rbs_parasitic1(self, r3:Optional[float]=None) -> float:
        if r3 is None:
            r3 = self.r3
        return ((self.r2 + r3) * (self.l2 + self.l3 - self.lbs) /
                self.l2 - self.r2)

    def rs_parasitic1(self, r3:Optional[float]=None) -> float:
        if r3 is None:
            r3 = self.r3
        return r3 + (self.r2 + r3) * (self.ls / self.l2)


    def __str__(self) -> str:
        return 'l1: %.2f mm; l2: %.2f mm; D1: %.0f um; D2: %.0f um;\
D3: %.0f um; I: %.2f; qmin: %.5f 1/nm' % (self.l1, self.l2, self.D1, self.D2,
                                          self.D3, self.intensity, self.qmin)

    @property
    def dominant_constraint(self) -> str:
        lambda1 = (self.ls + self.l2) / self.l1
        lambda0 = (self.l2 / self.l1)
        rho = self.rs / self.rbs
        d_SsBS = (
            (2 * lambda1 * (lambda1 + 1) - rho * (lambda0 + lambda1 +
                                                  2 * lambda0 * lambda1)) /
            (rho * (lambda0 + 2 * lambda1 + 2 * lambda0 * lambda1)) *
            self.l2 + self.lbs - self.ls)
        Discr = 4 * rho ** 2 * lambda0 ** 2 + rho * \
                                              (4 * lambda0 ** 2 - 8 * lambda0 * lambda1) + \
                (lambda0 + 2 * lambda1 + 2 * lambda0 * lambda1) ** 2
        lam2plus = ((2 * lambda1 + lambda0 + 2 * lambda0 * lambda1 -
                     6 * rho * lambda0 - 4 * rho * lambda0 ** 2 + Discr ** 0.5) /
                    (8 * rho * lambda0 + 4 * rho * lambda0 ** 2))
        d_BSsSplus = lam2plus * self.l2 + self.lbs - self.ls
        if self.sd < d_SsBS:
            return 'sample'
        elif self.sd < d_BSsSplus:
            return 'beamstop'
        else:
            return 'neither'

    @classmethod
    def enumerate(cls, spacers: Sequence[float], pinholes: Sequence[float],
                  ls, lbs, sd, mindist_l1, mindist_l2, sealringwidth, wavelength):
        l_seen = []
        for l1_parts in pickfromlist(spacers):
            l1 = mindist_l1 + len(l1_parts) * sealringwidth + sum(l1_parts)
            spacers_remaining = list(spacers[:])
            for s in l1_parts:
                spacers_remaining.remove(s)
            for l2_parts in pickfromlist(spacers_remaining):
                l2 = mindist_l2 + len(l2_parts) * sealringwidth + sum(l2_parts)
                if (l1, l2) in l_seen:
                    continue
                l_seen.append((l1, l2))
                for d1 in pinholes:
                    for d2 in pinholes:
                        yield PinholeConfiguration(l1_parts, l2_parts, d1, d2, ls, lbs, sd, mindist_l1, mindist_l2,
                                                   sealringwidth, wavelength)
