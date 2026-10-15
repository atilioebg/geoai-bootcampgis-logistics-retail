# Bug Tracker

Document any errors and their solutions here.

## 2026-08-24 - ModuleNotFoundError in pytest
**Error:** `ModuleNotFoundError: No module named 'src'` when running `pytest tests/unit/test_hello_world.py`.
**Root Cause:** Python doesn't automatically add the project root to `PYTHONPATH` when running tests.
**Solution:** Created a `pytest.ini` file at the root with `pythonpath = .` to ensure the `src` module is properly discovered during testing.
