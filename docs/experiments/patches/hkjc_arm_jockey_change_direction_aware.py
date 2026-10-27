"""EXP-20261027-13 arm B：換上賽日前 365 日頭 6 騎師就唔扣換騎 −1.5。"""
ARM_NAME = "jockey_change_direction_aware"


def apply():
    from hkjc_racing_engine import scoring
    assert scoring.JOCKEY_CHANGE_SKIP_TOP_UPGRADE is False
    scoring.JOCKEY_CHANGE_SKIP_TOP_UPGRADE = True
