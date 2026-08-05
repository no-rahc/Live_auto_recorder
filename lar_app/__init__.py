"""Application assembly package for Live Auto Recorder.

The legacy recorder core remains in ``live_auto_recorder.py`` while this package
owns deployment bootstrap, release metadata, middleware, and web asset wiring.
Submodules are imported explicitly so importing :mod:`lar_app` has no runtime
side effects.
"""
