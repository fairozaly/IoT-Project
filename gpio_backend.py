"""Select the GPIO implementation for the current machine."""

import platform


class _MockGPIO:
    """Small RPi.GPIO-compatible mock for machines without GPIO hardware."""

    BCM = "BCM"
    OUT = "OUT"
    HIGH = 1
    LOW = 0

    def setwarnings(self, *_args, **_kwargs):
        pass

    def setmode(self, *_args, **_kwargs):
        pass

    def setup(self, *_args, **_kwargs):
        pass

    def output(self, *_args, **_kwargs):
        pass


if platform.system() == "Darwin":
    # RPi.GPIO is not available on macOS, and importing it can fail before
    # the application has a chance to start. Select the mock explicitly.
    GPIO = _MockGPIO()
else:
    try:
        import RPi.GPIO as GPIO
    except (ImportError, RuntimeError):
        # Keep local development usable on other non-Pi platforms too.
        GPIO = _MockGPIO()
