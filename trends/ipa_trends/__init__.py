"""IPA service-ticket trends: unplanned tickets per 100 installed machine-months by issue, per reporting period,
for a rerun frequency that is a free parameter (quarterly by default, monthly as the alternative).

    from ipa_trends import run
    result = run({'RERUN_FREQUENCY': 'monthly'})

See trends/README.md (how to run it) and trends/METHOD.md (definitions and statistics).
"""
__version__ = '1.0.0'
METHOD_VERSION = '1.0'


def run(params=None, publish=True, verbose=True):
    """Run the analysis; see engine.run."""
    from .engine import run as _run
    return _run(params, publish=publish, verbose=verbose)
