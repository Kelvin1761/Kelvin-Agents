"""Remove the SIP +1.0 raw boost (EXP-20261010-05)."""
ARM_NAME = "no_sip"
def apply():
    import hkjc_auto_orchestrator as orch
    orch._apply_sip_enhancements = lambda horses: None
