import RPi.GPIO as GPIO

FAN_ENABLE_IO = 22
FAN_INPUT_1_IO = 27
FAN_INPUT_2_IO = 17

_fan_running = False


def is_fan_running():
    return _fan_running


def start_fan():
    global _fan_running

    GPIO.setmode(GPIO.BCM)

    GPIO.setup(FAN_ENABLE_IO, GPIO.OUT)
    GPIO.setup(FAN_INPUT_1_IO, GPIO.OUT)
    GPIO.setup(FAN_INPUT_2_IO, GPIO.OUT)

    GPIO.output(FAN_INPUT_1_IO, GPIO.LOW)
    GPIO.output(FAN_INPUT_2_IO, GPIO.HIGH)
    GPIO.output(FAN_ENABLE_IO, GPIO.HIGH)

    _fan_running = True


def stop_fan():
    global _fan_running

    GPIO.setmode(GPIO.BCM)

    GPIO.setup(FAN_ENABLE_IO, GPIO.OUT)
    GPIO.setup(FAN_INPUT_1_IO, GPIO.OUT)
    GPIO.setup(FAN_INPUT_2_IO, GPIO.OUT)

    GPIO.output(FAN_ENABLE_IO, GPIO.LOW)
    GPIO.output(FAN_INPUT_1_IO, GPIO.LOW)
    GPIO.output(FAN_INPUT_2_IO, GPIO.LOW)

    _fan_running = False
