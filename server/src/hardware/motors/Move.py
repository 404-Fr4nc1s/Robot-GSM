#!/usr/bin/env/python3
# File name   : Move.py
# Website     : www.Adeept.com
# Author      : Adeept
# Date        : 2025/03/25
import time
from gpiozero import Motor, OutputDevice

Motor_A_EN    = 4
Motor_B_EN    = 17

Motor_A_Pin1  = 26
Motor_A_Pin2  = 21
Motor_B_Pin1  = 27
Motor_B_Pin2  = 18



motor_left = Motor(forward=Motor_B_Pin2, backward=Motor_B_Pin1, enable=Motor_B_EN)
motor_right = Motor(forward=Motor_A_Pin2, backward=Motor_A_Pin1, enable=Motor_A_EN)

def motorStop():#Motor stops
    motor_left.stop()
    motor_right.stop()


def setup():#Motor initialization
    pass


SPEED = 100

def set_speed_level(level):
    global SPEED
    SPEED = level

def forward():
    move(SPEED, 'forward', 'no')

def backward():
    move(SPEED, 'backward', 'no')

def left():
    move(SPEED, 'forward', 'left')

def right():
    move(SPEED, 'forward', 'right')

def stop():
    motorStop()

def move(speed, direction, turn, radius=0.6):   # 0 < radius <= 1
    speed = speed / 100 
    if direction == 'forward':
        if turn == 'right':
            motor_left.backward(speed * radius)
            motor_right.forward(speed)
        elif turn == 'left':
            motor_left.forward(speed)
            motor_right.backward(speed * radius)
        else:
            motor_left.forward(speed)
            motor_right.forward(speed)
    elif direction == 'backward':
        if turn == 'right':
            motor_left.forward(speed * radius)
            motor_right.backward(speed)
        elif turn == 'left':
            motor_left.backward(speed)
            motor_right.forward(speed * radius)
        else:
            motor_left.backward(speed)
            motor_right.backward(speed)
    elif direction == 'no':
        if turn == 'right':
            motor_left.backward(speed)
            motor_right.forward(speed)
        elif turn == 'left':
            motor_left.forward(speed)
            motor_right.backward(speed)
        else:
            motorStop()
    else:
        pass


def destroy():
    motorStop()

def set_speed(left: int, right: int):
    """
    Sets motor speeds directly.
    Args:
        left (int): Speed for left motor (-100 to 100)
        right (int): Speed for right motor (-100 to 100)
    """
    # Clamp values
    left = max(-100, min(100, left))
    right = max(-100, min(100, right))

    # Left Motor
    if left >= 0:
        motor_left.forward(left / 100.0)
    else:
        motor_left.backward(abs(left) / 100.0)

    # Right Motor
    if right >= 0:
        motor_right.forward(right / 100.0)
    else:
        motor_right.backward(abs(right) / 100.0)

def get_state():
    """
    Returns current motor speeds.
    Returns:
        tuple: (left_speed, right_speed) in range -100 to 100
    """
    l_val = motor_left.value  # 0..1
    r_val = motor_right.value # 0..1
    
    # Determine direction based on active pins (gpiozero Motor doesn't give signed value directly easily without checking is_active)
    # Actually gpiozero Motor.value is speed (0..1). We need to check which way it's turning.
    # motor.forward_device.value vs backward_device.value
    
    l_speed = 0
    if motor_left.forward_device.value > 0:
        l_speed = int(motor_left.forward_device.value * 100)
    elif motor_left.backward_device.value > 0:
        l_speed = -int(motor_left.backward_device.value * 100)
        
    r_speed = 0
    if motor_right.forward_device.value > 0:
        r_speed = int(motor_right.forward_device.value * 100)
    elif motor_right.backward_device.value > 0:
        r_speed = -int(motor_right.backward_device.value * 100)
        
    return (l_speed, r_speed)

def video_Tracking_Move(speed, direction):   # 0 < radius <= 1  
    #speed:0~100. direction:1/-1.
    if speed == 0:
        motorStop() #all motor stop.
    else:
        if direction == 1: 			# forward
            move(speed, 'forward', 'no', 0.5)

        elif direction == -1: 		# backward
            move(speed, 'backward', 'no', 0.5)

if __name__ == '__main__':
    try:
        speed_set = 50
        setup()
        for i in range(10):
            move(speed_set, 'forward', 'no', 0.8)
            print("Forward")
            time.sleep(2)
            move(speed_set, 'backward', 'no', 0.8)
            print("backward")
            time.sleep(2)

        destroy()
    except KeyboardInterrupt:
        destroy()
    
