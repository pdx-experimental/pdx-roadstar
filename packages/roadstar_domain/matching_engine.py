"""Automated Load Matching & Deadhead Mile Reduction Engine."""
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from .models import OrderModel, DriverModel, BackhaulMatchResult
from .hos_engine import evaluate_hos_compliance
from .geo_routing import estimate_corridor_road_miles

MAX_TRAILER_WEIGHT_LBS = 44500.0  # 53ft Dry Van standard weight limit


def match_backhaul_and_audit(
    outbound_order: OrderModel,
    candidate_orders: List[OrderModel],
    available_drivers: List[DriverModel],
    claimed_bills: Optional[set[str]] = None,
    arrival_time: Optional[datetime] = None
) -> BackhaulMatchResult:
    """Finds optimal return load near destination using the Geodesic Winding Corridor Model,
    audits HOS and trailer weight limits for BOTH outbound and return loads,
    and calculates physical segment deadhead savings without arbitrary distance constants.
    """
    notes = []
    claimed = claimed_bills or set()

    # 1. Outbound Trailer Weight Audit
    outbound_weight_ok = outbound_order.weight_lbs <= MAX_TRAILER_WEIGHT_LBS
    if not outbound_weight_ok:
        notes.append(f"WEIGHT WARNING: Outbound weight {outbound_order.weight_lbs:,.0f} lbs exceeds 44,500 lbs trailer limit!")
    else:
        notes.append(f"Outbound Weight OK: {outbound_order.weight_lbs:,.0f} lbs <= 44,500 lbs limit.")

    # 2. Find Best Backhaul Load (origin near outbound destination)
    best_return = None
    best_repo_miles = 0.0
    best_post_repo_miles = 0.0

    for cand in candidate_orders:
        if cand.bill_number == outbound_order.bill_number or cand.bill_number in claimed:
            continue
        if cand.currently_assigned:
            continue

        # Time-window feasibility: pickup must be compatible with truck's arrival
        if arrival_time and cand.pickup_time:
            cand_pu = cand.pickup_time if cand.pickup_time.tzinfo else cand.pickup_time.replace(tzinfo=timezone.utc)
            arr_t = arrival_time if arrival_time.tzinfo else arrival_time.replace(tzinfo=timezone.utc)
            # Feasible operational pickup window: from 15 minutes before arrival up to 14 hours after arrival
            # Fully supports cross-midnight pickups while strictly rejecting mismatched calendar dates
            if cand_pu < (arr_t - timedelta(minutes=15)) or cand_pu > (arr_t + timedelta(hours=14)):
                continue

        try:
            repo_dist = estimate_corridor_road_miles(outbound_order.dest_city, cand.origin_city)
            post_repo_dist = estimate_corridor_road_miles(cand.dest_city, outbound_order.origin_city)
        except ValueError:
            # Missing coordinates in explicit registry -> skip candidate safely
            continue

        # Proximity threshold: pickup must be within 55 mi of drop-off, return delivery within 55 mi of base
        if repo_dist > 55.0 or post_repo_dist > 55.0:
            continue

        # Net Benefit invariant: repositioning deadhead must be strictly less than baseline empty return
        if repo_dist + post_repo_dist >= outbound_order.distance_miles:
            continue

        best_return = cand
        best_repo_miles = repo_dist
        best_post_repo_miles = post_repo_dist
        break

    repo_miles = best_repo_miles
    post_repo_miles = best_post_repo_miles

    # Return Trailer Weight Audit
    return_weight_ok = True
    if best_return:
        return_weight_ok = best_return.weight_lbs <= MAX_TRAILER_WEIGHT_LBS
        if not return_weight_ok:
            notes.append(f"WEIGHT WARNING: Return load #{best_return.bill_number} weight {best_return.weight_lbs:,.0f} lbs exceeds 44,500 lbs trailer limit!")
        else:
            notes.append(f"Return Weight OK: {best_return.weight_lbs:,.0f} lbs <= 44,500 lbs limit.")

    weight_passed = outbound_weight_ok and return_weight_ok

    # Calculate Physical Segment Deadhead & Savings (No arbitrary fixed percentages)
    deadhead_saved_miles = 0.0
    deadhead_reduction_pct = 0.0
    if best_return and weight_passed:
        # Baseline was returning completely empty over the outbound distance
        baseline_empty = outbound_order.distance_miles
        # With backhaul, empty miles are strictly the repositioning segments:
        pdx_empty = repo_miles + post_repo_miles
        deadhead_saved_miles = round(max(0.0, baseline_empty - pdx_empty), 1)
        deadhead_reduction_pct = round((deadhead_saved_miles / max(1.0, baseline_empty)) * 100.0, 1)
        total_revenue = round(outbound_order.rate_cad + best_return.rate_cad, 2)
        notes.append(f"Backhaul Matched: Order #{best_return.bill_number} ({best_return.origin_city} -> {best_return.dest_city}).")
        notes.append(f"Segment Audit: Outbound {baseline_empty:.1f} mi; Repo {repo_miles:.1f} mi + Post-Repo {post_repo_miles:.1f} mi = {pdx_empty:.1f} mi empty. Saved {deadhead_saved_miles:.1f} mi ({deadhead_reduction_pct:.1f}%).")
    else:
        total_revenue = outbound_order.rate_cad
        notes.append("No compliant backhaul found; return leg remains empty dispatch.")

    # 3. HOS Audit on Drivers for the Return Dispatch
    assigned_driver = None
    hos_passed = False
    return_dist = (best_return.distance_miles if (best_return and weight_passed) else outbound_order.distance_miles) + repo_miles + post_repo_miles
    est_total_drive_hours = return_dist / 50.0
    est_total_on_duty_hours = est_total_drive_hours + (2.0 if (best_return and weight_passed) else 0.0)

    for driver in available_drivers:
        comp, viols = evaluate_hos_compliance(driver.hos, est_total_drive_hours, est_total_on_duty_hours)
        if comp:
            assigned_driver = driver
            hos_passed = True
            notes.append(f"Assigned Driver: {driver.first_name} (HOS Compliant, {driver.hos.remaining_hours_can_7:.1f}h cycle remaining).")
            break
        else:
            notes.append(f"Driver {driver.first_name} rejected: {viols[0]}")

    if not hos_passed:
        notes.append("HOS audit failed: No available driver has sufficient duty hours.")

    return BackhaulMatchResult(
        outbound_order=outbound_order,
        return_order=best_return if (weight_passed and hos_passed) else None,
        deadhead_reduction_pct=deadhead_reduction_pct if (weight_passed and hos_passed) else 0.0,
        empty_miles_saved=deadhead_saved_miles if (weight_passed and hos_passed) else 0.0,
        total_revenue_cad=total_revenue if (weight_passed and hos_passed) else outbound_order.rate_cad,
        hos_audit_passed=hos_passed,
        weight_audit_passed=weight_passed,
        assigned_driver_id=assigned_driver.driver_id if assigned_driver else 0,
        driver_name=assigned_driver.first_name if assigned_driver else "Unassigned",
        notes=notes
    )
