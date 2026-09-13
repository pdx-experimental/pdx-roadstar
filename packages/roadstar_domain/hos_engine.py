"""Transport Canada Commercial Vehicle Drivers Hours of Service (South of 60°N)."""
from typing import Tuple, List
from .models import HOSStatus

MAX_DRIVING_HOURS_PER_SHIFT = 13.0
MAX_ON_DUTY_HOURS_PER_SHIFT = 14.0
MAX_ELAPSED_WINDOW_HOURS = 16.0
MIN_OFF_DUTY_DAILY = 10.0
CYCLE_1_LIMIT_HOURS = 70.0


def evaluate_hos_compliance(
    hos: HOSStatus,
    planned_drive_hours: float = 0.0,
    planned_on_duty_hours: float = 0.0
) -> Tuple[bool, List[str]]:
    violations = []
    
    # 1. 13-Hour Driving Limit
    projected_drive = hos.shift_driving_hours + planned_drive_hours
    if projected_drive > MAX_DRIVING_HOURS_PER_SHIFT:
        violations.append(
            f"13-Hour Driving Limit Exceeded: Projected {projected_drive:.1f}h exceeds {MAX_DRIVING_HOURS_PER_SHIFT}h limit."
        )

    # 2. 14-Hour On-Duty Limit
    projected_on_duty = hos.shift_on_duty_hours + planned_on_duty_hours
    if projected_on_duty > MAX_ON_DUTY_HOURS_PER_SHIFT:
        violations.append(
            f"14-Hour On-Duty Limit Exceeded: Projected {projected_on_duty:.1f}h exceeds {MAX_ON_DUTY_HOURS_PER_SHIFT}h limit."
        )

    # 3. 16-Hour Elapsed Window
    projected_elapsed = hos.shift_elapsed_hours + planned_on_duty_hours
    if projected_elapsed > MAX_ELAPSED_WINDOW_HOURS:
        violations.append(
            f"16-Hour Elapsed Window Exceeded: Shift elapsed time {projected_elapsed:.1f}h exceeds {MAX_ELAPSED_WINDOW_HOURS}h window."
        )

    # 4. Cycle 1 Limit (70h/7 days)
    if hos.remaining_hours_can_7 < planned_on_duty_hours:
        violations.append(
            f"Cycle 1 (70h) Limit Exceeded: Driver has only {hos.remaining_hours_can_7:.1f}h remaining, needs {planned_on_duty_hours:.1f}h."
        )

    is_compliant = len(violations) == 0
    return is_compliant, violations


def update_hos_tick(hos: HOSStatus, elapsed_hours: float, duty_mode: int) -> HOSStatus:
    """Updates driver HOS state over time during simulation tick."""
    hos.current_duty = duty_mode
    if duty_mode == 2:  # Driving
        hos.duty_status_desc = "Driving"
        hos.shift_driving_hours += elapsed_hours
        hos.shift_on_duty_hours += elapsed_hours
        hos.shift_elapsed_hours += elapsed_hours
        hos.remaining_hours_can_7 = max(0.0, hos.remaining_hours_can_7 - elapsed_hours)
    elif duty_mode == 3:  # On-duty not driving (dock wait, loading)
        hos.duty_status_desc = "On-Duty (Dock)"
        hos.shift_on_duty_hours += elapsed_hours
        hos.shift_elapsed_hours += elapsed_hours
        hos.remaining_hours_can_7 = max(0.0, hos.remaining_hours_can_7 - elapsed_hours)
    else:  # Off-duty / Sleeper
        hos.duty_status_desc = "Off-Duty"
        hos.shift_elapsed_hours += elapsed_hours

    is_comp, viols = evaluate_hos_compliance(hos, 0.0, 0.0)
    hos.is_compliant = is_comp
    hos.violations = viols
    return hos
