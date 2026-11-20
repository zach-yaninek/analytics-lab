"""Verbatim copies from verification/association.py. Do not edit by hand: regenerate with
trends/tests/sync_definitions.py --write (MIT side) and check with trends/tests/test_parity.py.
"""
import numpy as np


def ci(reps):
    """95% percentile interval (A13): NaN replicates (undefined) are left out and counted; +-inf may be endpoints."""
    reps = np.asarray(reps, float)
    undefined = int(np.isnan(reps).sum())
    if undefined == len(reps):
        return np.nan, np.nan, undefined
    lo, hi = np.nanpercentile(reps, [2.5, 97.5], method='inverted_cdf')
    return float(lo), float(hi), undefined
