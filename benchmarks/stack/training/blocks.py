"""Structure weighted analog features used by the SBZ residual stacker."""

import numpy as np


class Struct:
    def __init__(self, names, mat):
        self.at = {n: v for n, v in zip(names, mat)}
        self.dim = mat.shape[1]

    def dist2(self, name, others):
        v = self.at.get(name)
        if v is None:
            return None
        mat = np.stack([self.at.get(other, np.full(self.dim, np.nan)) for other in others])
        distance = ((mat - v) ** 2).sum(1)
        distance[~np.isfinite(distance)] = (np.nanmax(distance[np.isfinite(distance)]) * 10
                                            if np.isfinite(distance).any() else 1.0)
        return distance


def mixed_neighbours(analog, lv, mu, ok, q, name, d2_struct, lam, kk=10):
    distance = analog.dist2(lv, mu, ok, name)
    if d2_struct is not None and lam > 0:
        curve_scale = np.median(distance[np.isfinite(distance)]) + 1e-9
        structure_scale = np.median(d2_struct) + 1e-9
        mix = distance / curve_scale + lam * (d2_struct / structure_scale)
        mix[~np.isfinite(distance)] = np.inf
        distance = mix
    nearest = np.argsort(distance)[:kk]
    weights = 1.0 / (distance[nearest] + 1e-3)
    return np.tensordot(weights / weights.sum(), analog.at(q)[nearest], axes=1)
