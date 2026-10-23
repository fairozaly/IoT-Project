import RPi.GPIO as GPIO

FAN_ENABLE_IO = 22
FAN_INPUT_1_IO = 27
FAN_INPUT_2_IO = 17

_fan_running = False
_pins_ready = False


def _setup_pins():
    global _pins_ready

    if _pins_ready:
        return

    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(FAN_ENABLE_IO, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(FAN_INPUT_1_IO, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(FAN_INPUT_2_IO, GPIO.OUT, initial=GPIO.LOW)

    _pins_ready = True


def is_fan_running():
    return _fan_running


def start_fan():
    global _fan_running

    _setup_pins()

    GPIO.output(FAN_INPUT_1_IO, GPIO.LOW)
    GPIO.output(FAN_INPUT_2_IO, GPIO.HIGH)
    GPIO.output(FAN_ENABLE_IO, GPIO.HIGH)

    _fan_running = True


def stop_fan():
    global _fan_running

    _setup_pins()

    GPIO.output(FAN_ENABLE_IO, GPIO.LOW)
    GPIO.output(FAN_INPUT_1_IO, GPIO.LOW)
    GPIO.output(FAN_INPUT_2_IO, GPIO.LOW)

    _fan_running = False
