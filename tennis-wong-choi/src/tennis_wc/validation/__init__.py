"""Data-integrity checks that run against the live database.

Every check here corresponds to a defect that was actually found and measured,
not a hypothetical.  The system's characteristic failure is silence: nothing
errors, the tests pass, the report prints, and the number is wrong.  These turn
that silence into a signal.
"""
