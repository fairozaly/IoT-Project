import RPi.GPIO as GPIO

import time
from time import sleep

SUCCESS_INDICATOR_IO = 23
FAILURE_INDICATOR_IO = 22

def indicate_failure() -> None:
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(FAILURE_INDICATOR_IO, GPIO.OUT)
    GPIO.output(FAILURE_INDICATOR_IO, GPIO.HIGH)
    sleep(1)
    GPIO.output(FAILURE_INDICATOR_IO, GPIO.LOW)

def indicate_success() -> None:
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(SUCCESS_INDICATOR_IO, GPIO.OUT)
    GPIO.output(SUCCESS_INDICATOR_IO, GPIO.HIGH)
    sleep(1)
    GPIO.output(SUCCESS_INDICATOR_IO, GPIO.LOW)