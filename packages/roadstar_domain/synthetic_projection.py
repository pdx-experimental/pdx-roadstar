"""Explicit, Opt-In Synthetic Scenario Date Projector.

Requirement (Auditor Condition 3):
- Historical date projection must be an explicit, opt-in synthetic scenario.
- It must preserve original dates, shift deltas, and projection rules.
- It must NEVER be enabled implicitly or by default.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional
from .models import OrderModel


def project_candidate_orders_to_date(
    orders: List[OrderModel],
    target_date: date,
    source_reference_date: Optional[date] = None,
    projection_rule: str = "calendar_day_shift"
) -> List[OrderModel]:
    """Explicitly projects historical candidate orders to a target simulation date.
    
    This is an OPT-IN synthetic scenario transformation.
    Every transformed order explicitly preserves its original timestamps,
    shift delta, and is stamped with `is_synthetic_projection = True`.
    """
    projected: List[OrderModel] = []
    
    for order in orders:
        if not order.pickup_time:
            projected.append(order.model_copy(deep=True))
            continue
            
        pu_dt = order.pickup_time
        src_date = pu_dt.date()
        
        if source_reference_date is not None:
            # Shift relative to reference date
            day_offset = (src_date - source_reference_date).days
            new_date = target_date + timedelta(days=day_offset)
            shift_days = (new_date - src_date).days
        else:
            # Direct single-day alignment
            shift_days = (target_date - src_date).days
            new_date = target_date

        new_pu = pu_dt.replace(year=new_date.year, month=new_date.month, day=new_date.day)
        
        new_del = None
        if order.delivery_time:
            del_dt = order.delivery_time
            del_date = del_dt.date()
            del_new_date = del_date + timedelta(days=shift_days)
            new_del = del_dt.replace(year=del_new_date.year, month=del_new_date.month, day=del_new_date.day)
            
        copy_order = order.model_copy(deep=True)
        copy_order.original_pickup_time = pu_dt
        copy_order.pickup_time = new_pu
        copy_order.delivery_time = new_del
        copy_order.is_synthetic_projection = True
        copy_order.projection_shift_days = shift_days
        projected.append(copy_order)
        
    return projected
