#!/bin/bash

sudo modprobe usbserial vendor=0x0483 product=0x5750
sudo apt update && sudo apt install python3-serial