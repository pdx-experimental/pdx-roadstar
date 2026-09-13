from __future__ import annotations

import os
import json
import time
import uuid
import threading
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_FLEET_STORAGE_DIR = BASE_DIR / "data" / "fleet_reservations"


@dataclass(frozen=True)
class ResourceSlot:
    resource_type: str  # 'truck', 'driver', or 'order'
    resource_id: str
    start_time: datetime
    end_time: datetime
    trip_id: str


class ResourceConflictError(Exception):
    """Raised when a truck, driver, or order is already reserved for an overlapping time interval
    or when an order bill is double-booked on any trip.
    """
    pass


class CorruptedStateError(Exception):
    """Raised when the persistent resource reservation state file is corrupted, empty,
    or missing required structure.
    """
    pass


class FileTransactionLock:
    """OS-owned lock for the fleet store; death releases it without PID probing.

    The lock file is permanent. Never unlink it: replacing its inode can let
    two processes lock different files for the same resource store.
    """

    def __init__(self, lock_file: Path, timeout_sec: float = 10.0) -> None:
        self.lock_file = Path(lock_file)
        self.timeout_sec = timeout_sec
        self.fd: Optional[int] = None

    def __enter__(self) -> "FileTransactionLock":
        import errno
        fd = os.open(str(self.lock_file), os.O_CREAT | os.O_RDWR, 0o600)
        deadline = time.monotonic() + self.timeout_sec
        try:
            while True:
                try:
                    if os.name == "nt":
                        import msvcrt
                        os.lseek(fd, 0, os.SEEK_SET)
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self.fd = fd
                    return self
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"Timed out waiting for reservation lock: {self.lock_file}") from exc
                    time.sleep(0.015)
        except BaseException:
            os.close(fd)
            raise

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.fd is not None:
            fd, self.fd = self.fd, None
            os.close(fd)  # OS releases ownership, including after process death.


class FleetResourceManager:
    """Thread-safe, cross-instance, and cross-process fleet resource reservation manager
    covering trucks, drivers, and freight orders (bills).
    
    Guarantees:
    1. Cross-instance / cross-process mutual exclusion via an OS-owned FileTransactionLock.
    2. Atomic reload of disk state before every evaluation.
    3. Empty or malformed state files are rejected with CorruptedStateError (never treated as empty reservations).
    4. Freight orders are non-reentrant single-use physical shipments (cannot be double-booked at any time).
    5. Shared persistent storage directory configured by default, easily injectable for test isolation.
    """
    _instance: Optional["FleetResourceManager"] = None
    _class_lock = threading.Lock()

    def __init__(self, storage_dir: Optional[Path | str] = None) -> None:
        self._thread_lock = threading.Lock()
        if storage_dir is not None:
            self.storage_dir = Path(storage_dir).resolve()
        else:
            self.storage_dir = DEFAULT_FLEET_STORAGE_DIR.resolve()

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = self.storage_dir / ".resource_reservations.json"
        self._lock_file = self.storage_dir / ".resource_reservations.lock"

        self._reservations: Dict[Tuple[str, str], List[ResourceSlot]] = {}
        self._trip_reservations: Dict[str, List[ResourceSlot]] = {}

    @classmethod
    def get_global_manager(cls, storage_dir: Optional[Path | str] = None) -> "FleetResourceManager":
        with cls._class_lock:
            if storage_dir is None and cls._instance is not None:
                return cls._instance
            target_dir = Path(storage_dir).resolve() if storage_dir is not None else DEFAULT_FLEET_STORAGE_DIR.resolve()
            if cls._instance is None or cls._instance.storage_dir != target_dir:
                cls._instance = cls(storage_dir=target_dir)
            return cls._instance

    def _load_disk_state_unlocked(self) -> None:
        """Reload reservations from disk file. Must be called under FileTransactionLock."""
        self._reservations.clear()
        self._trip_reservations.clear()

        if self._state_file.exists():
            try:
                raw_text = self._state_file.read_text(encoding="utf-8")
                if not raw_text.strip():
                    raise CorruptedStateError(f"Persisted reservation state file at {self._state_file} is empty.")
                data = json.loads(raw_text)
            except CorruptedStateError:
                raise
            except Exception as exc:
                raise CorruptedStateError(
                    f"Persisted reservation state file at {self._state_file} is corrupted: {exc}"
                ) from exc

            if not isinstance(data, dict) or "slots" not in data or not isinstance(data["slots"], list):
                raise CorruptedStateError(
                    f"Persisted reservation state file at {self._state_file} is missing required 'slots' array."
                )

            for item in data["slots"]:
                try:
                    slot = ResourceSlot(
                        resource_type=item["resource_type"],
                        resource_id=item["resource_id"],
                        start_time=datetime.fromisoformat(item["start_time"]),
                        end_time=datetime.fromisoformat(item["end_time"]),
                        trip_id=item["trip_id"],
                    )
                    key = (slot.resource_type, slot.resource_id)
                    self._reservations.setdefault(key, []).append(slot)
                    self._trip_reservations.setdefault(slot.trip_id, []).append(slot)
                except Exception as exc:
                    raise CorruptedStateError(
                        f"Invalid slot entry in {self._state_file}: {exc}"
                    ) from exc

    def _save_disk_state_unlocked(self) -> None:
        """Atomically persist state to disk via .tmp and os.replace. Must be called under FileTransactionLock."""
        all_slots = []
        for slots in self._trip_reservations.values():
            for s in slots:
                all_slots.append({
                    "resource_type": s.resource_type,
                    "resource_id": s.resource_id,
                    "start_time": s.start_time.isoformat(),
                    "end_time": s.end_time.isoformat(),
                    "trip_id": s.trip_id,
                })

        tmp_file = self.storage_dir / f".res_{os.getpid()}_{uuid.uuid4().hex[:8]}.tmp"
        tmp_file.write_text(json.dumps({"slots": all_slots}, indent=2), encoding="utf-8")
        os.replace(tmp_file, self._state_file)

    def reset(self) -> None:
        """Clear all active reservations across instances and storage."""
        with self._thread_lock, FileTransactionLock(self._lock_file):
            self._reservations.clear()
            self._trip_reservations.clear()
            if self._state_file.exists():
                self._state_file.unlink()

    def is_available(
        self,
        resource_type: str,
        resource_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> bool:
        """Check if resource (truck, driver, or order) is free during [start_time, end_time].
        For orders, checks whether the order has been booked for ANY trip (non-reentrant).
        """
        with self._thread_lock, FileTransactionLock(self._lock_file):
            self._load_disk_state_unlocked()
            key = (resource_type, resource_id)
            slots = self._reservations.get(key, [])
            if resource_type == "order":
                return len(slots) == 0
            for slot in slots:
                if max(start_time, slot.start_time) < min(end_time, slot.end_time):
                    return False
            return True

    def acquire_reservation(
        self,
        *,
        truck_id: str,
        driver_id: str,
        order_bill: Optional[str] = None,
        start_time: datetime,
        end_time: datetime,
        trip_id: str,
    ) -> List[ResourceSlot]:
        """Atomically acquire reservations across truck, driver, and freight order bill.
        
        Rules:
        - Truck & Driver: Must not have overlapping time interval reservations.
        - Order Bill: Physical shipment is single-use and non-reentrant. It cannot be booked
          for ANY trip once reserved, even at non-overlapping times.
        - Entire transaction is protected under cross-instance/cross-process FileTransactionLock.
        - If ANY resource is unavailable, aborts immediately and reserves NONE (atomic all-or-nothing).
        """
        if start_time >= end_time:
            raise ValueError(f"start_time ({start_time}) must be before end_time ({end_time})")

        with self._thread_lock, FileTransactionLock(self._lock_file):
            self._load_disk_state_unlocked()

            if trip_id in self._trip_reservations:
                raise ResourceConflictError(f"Trip {trip_id} already owns a reservation")

            # 1. Check truck availability (interval overlap)
            truck_key = ("truck", truck_id)
            for slot in self._reservations.get(truck_key, []):
                if max(start_time, slot.start_time) < min(end_time, slot.end_time):
                    raise ResourceConflictError(
                        f"Truck {truck_id} is already reserved for trip {slot.trip_id} "
                        f"({slot.start_time.isoformat()} to {slot.end_time.isoformat()})"
                    )

            # 2. Check driver availability (interval overlap)
            driver_key = ("driver", driver_id)
            for slot in self._reservations.get(driver_key, []):
                if max(start_time, slot.start_time) < min(end_time, slot.end_time):
                    raise ResourceConflictError(
                        f"Driver {driver_id} is already reserved for trip {slot.trip_id} "
                        f"({slot.start_time.isoformat()} to {slot.end_time.isoformat()})"
                    )

            # 3. Check order bill availability (strictly NON-REENTRANT across all trips and times)
            order_key = ("order", order_bill) if order_bill else None
            if order_key:
                existing_order_slots = self._reservations.get(order_key, [])
                if existing_order_slots:
                    prev = existing_order_slots[0]
                    raise ResourceConflictError(
                        f"Order bill {order_bill} has already been assigned to trip {prev.trip_id} "
                        f"and cannot be hauled a second time."
                    )

            # ALL resources free: atomically commit slots together
            truck_slot = ResourceSlot("truck", truck_id, start_time, end_time, trip_id)
            driver_slot = ResourceSlot("driver", driver_id, start_time, end_time, trip_id)
            slots_to_commit = [truck_slot, driver_slot]

            self._reservations.setdefault(truck_key, []).append(truck_slot)
            self._reservations.setdefault(driver_key, []).append(driver_slot)

            if order_key:
                order_slot = ResourceSlot("order", order_bill, start_time, end_time, trip_id)
                self._reservations.setdefault(order_key, []).append(order_slot)
                slots_to_commit.append(order_slot)

            self._trip_reservations[trip_id] = slots_to_commit
            self._save_disk_state_unlocked()

            return slots_to_commit

    def release_reservation(self, trip_id: str) -> bool:
        """Atomically releases all reservations associated with trip_id (truck, driver, order)."""
        with self._thread_lock, FileTransactionLock(self._lock_file):
            self._load_disk_state_unlocked()
            slots = self._trip_reservations.pop(trip_id, None)
            if not slots:
                return False
            for slot in slots:
                key = (slot.resource_type, slot.resource_id)
                if key in self._reservations:
                    self._reservations[key] = [
                        s for s in self._reservations[key] if s.trip_id != trip_id
                    ]
            self._save_disk_state_unlocked()
            return True

    def get_active_slots_for_trip(self, trip_id: str) -> List[ResourceSlot]:
        with self._thread_lock, FileTransactionLock(self._lock_file):
            self._load_disk_state_unlocked()
            return list(self._trip_reservations.get(trip_id, []))
