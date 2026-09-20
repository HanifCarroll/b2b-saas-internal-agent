"""Select live or deterministic investigation execution."""

import os
from typing import Literal, cast

InvestigationMode = Literal["live", "fixture"]


def get_investigation_mode() -> InvestigationMode:
    mode = os.getenv("SWITCHBOARD_INVESTIGATION_MODE", "live")
    if mode not in {"live", "fixture"}:
        raise ValueError("SWITCHBOARD_INVESTIGATION_MODE must be live or fixture")
    if mode == "fixture" and os.getenv("SWITCHBOARD_RUNTIME") != "local":
        raise ValueError(
            "Fixture investigations are available only in local development"
        )
    return cast(InvestigationMode, mode)
