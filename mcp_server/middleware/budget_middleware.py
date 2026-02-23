# Copyright (c) 2025-2026 OptimNow. All Rights Reserved.
# Licensed under the Apache License, Version 2.0.
# See LICENSE file in the project root for full license information.

"""Backward-compatibility shim — BudgetTracker has moved to utils.budget_tracker.

All symbols are re-exported so existing imports continue to work.
"""

from ..utils.budget_tracker import (  # noqa: F401
    DEFAULT_MAX_TOOL_CALLS_PER_SESSION,
    DEFAULT_SESSION_TTL_SECONDS,
    BudgetExhaustedError,
    BudgetTracker,
    check_and_consume_budget,
    get_budget_tracker,
    set_budget_tracker,
)
