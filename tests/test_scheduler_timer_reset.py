"""Tests for the cycle-timer reset behavior when a photo is shown manually.

Bug: selecting a photo (or clicking next/prev) did not reset the APScheduler
interval job, so the next auto-cycle could fire much sooner than the configured
rotation interval — making the just-chosen photo disappear almost immediately.

These tests exercise show_specific_photo / show_next_photo / show_previous_photo
after start_slideshow() and assert that the job's next_run_time is close to
`interval_minutes` from now, not anchored to the original start time.
"""

from datetime import datetime, timedelta

import pytest


@pytest.fixture
def sched(monkeypatch, tmp_path):
    """Fresh scheduler module state + stubs for display and photos."""
    import importlib
    import models
    import scheduler

    # Isolate settings file so tests don't touch real config.
    monkeypatch.setattr(models, "SETTINGS_PATH", tmp_path / "settings.json")

    # Reset module-level state between tests.
    if scheduler._scheduler is not None:
        try:
            scheduler._scheduler.shutdown(wait=False)
        except Exception:
            pass
    scheduler._scheduler = None
    scheduler._current_path = None
    scheduler._shuffle_bag = []
    scheduler._history = []
    scheduler._initialized = True  # skip disk load in tests

    # Stub out the display so scheduler.show_photo is a no-op.
    monkeypatch.setattr(scheduler.display, "show_photo", lambda *a, **kw: None)

    # Provide a fake photo library.
    fake_photos = ["/fake/p1.png", "/fake/p2.png", "/fake/p3.png"]
    monkeypatch.setattr(scheduler.models, "get_display_photos", lambda: fake_photos)
    monkeypatch.setattr(
        scheduler.models,
        "get_photo",
        lambda pid: {"id": pid, "display_path": f"/fake/p{pid}.png"},
    )
    monkeypatch.setattr(scheduler.models, "get_photo_count", lambda: len(fake_photos))

    # Seed settings with a known short interval (5 minutes — must be in INTERVAL_OPTIONS).
    models.save_settings({
        "slideshow": {
            "order": "sequential",
            "interval_minutes": 5,
            "enabled": True,
            "auto_start": False,
        },
        "display": {"saturation": 0.5},
    })

    yield scheduler

    # Cleanup: tear the scheduler down so tests don't leak threads.
    if scheduler._scheduler is not None:
        try:
            scheduler._scheduler.shutdown(wait=False)
        except Exception:
            pass
    scheduler._scheduler = None
    # Reload module-level state to a clean slate for subsequent imports.
    importlib.reload(scheduler)


def _next_run_offset_seconds(sched_module):
    job = sched_module.get_scheduler().get_job("photo_cycle")
    assert job is not None, "photo_cycle job should exist"
    assert job.next_run_time is not None
    # next_run_time is tz-aware; make "now" tz-aware to match.
    now = datetime.now(job.next_run_time.tzinfo)
    return (job.next_run_time - now).total_seconds()


def test_show_specific_photo_resets_cycle_timer(sched):
    """Manually selecting a photo must re-anchor the next cycle to now + interval."""
    sched.start_slideshow()

    # Simulate time elapsing: the job was scheduled for ~5 min from slideshow start.
    # Force the job's next_run_time to be very soon, then manually show a photo
    # and verify the timer is pushed back out to ~5 min again.
    job = sched.get_scheduler().get_job("photo_cycle")
    near_future = datetime.now(job.next_run_time.tzinfo) + timedelta(seconds=10)
    sched.get_scheduler().modify_job("photo_cycle", next_run_time=near_future)

    # Sanity check the pre-condition: timer is about to fire.
    assert _next_run_offset_seconds(sched) < 30

    # Act: user picks a photo.
    sched.show_specific_photo(2)

    # Assert: the next run is now ~5 minutes out, not ~10 seconds.
    offset = _next_run_offset_seconds(sched)
    assert offset > 4 * 60, (
        f"Expected next_run_time to reset to ~5 minutes after manual show, "
        f"got {offset:.1f}s"
    )


def test_manual_next_resets_cycle_timer(sched):
    """Clicking 'next' must also re-anchor the cycle timer."""
    sched.start_slideshow()

    job = sched.get_scheduler().get_job("photo_cycle")
    near_future = datetime.now(job.next_run_time.tzinfo) + timedelta(seconds=10)
    sched.get_scheduler().modify_job("photo_cycle", next_run_time=near_future)

    sched.show_next_photo()

    offset = _next_run_offset_seconds(sched)
    assert offset > 4 * 60, f"Expected reset after manual next, got {offset:.1f}s"


def test_manual_prev_resets_cycle_timer(sched):
    """Clicking 'prev' must also re-anchor the cycle timer."""
    sched.start_slideshow()

    job = sched.get_scheduler().get_job("photo_cycle")
    near_future = datetime.now(job.next_run_time.tzinfo) + timedelta(seconds=10)
    sched.get_scheduler().modify_job("photo_cycle", next_run_time=near_future)

    sched.show_previous_photo()

    offset = _next_run_offset_seconds(sched)
    assert offset > 4 * 60, f"Expected reset after manual prev, got {offset:.1f}s"


def test_scheduler_tick_does_not_double_reset(sched):
    """When the scheduler's own tick fires _cycle_photo_job, it should NOT
    reset the timer on top of APScheduler's own rescheduling — the next run
    should still be ~1 interval out, not ~2 intervals."""
    sched.start_slideshow()

    # Simulate the scheduler tick by calling _cycle_photo_job directly.
    sched._cycle_photo_job()

    offset = _next_run_offset_seconds(sched)
    # Should be <= interval (5 min = 300s), with some slack for execution time.
    assert offset <= 5 * 60 + 5, (
        f"Scheduler tick should not double-reset; next run was {offset:.1f}s "
        f"(expected <= ~300s)"
    )


def test_manual_show_when_slideshow_stopped_is_noop_for_timer(sched):
    """If the slideshow is stopped, manual show should not create or touch the job."""
    # Don't start slideshow — just call show_specific_photo directly.
    sched.show_specific_photo(1)

    job = sched.get_scheduler().get_job("photo_cycle")
    assert job is None, "No photo_cycle job should exist when slideshow is stopped"
