import serial
import time
from pynput import keyboard

# Windows COM Port (Check Device Manager for your specific port)
COM_PORT = 'COM3' 

try:
    # Open connection to the BRC-300 using Sony VISCA specs
    ser = serial.Serial(
        port=COM_PORT,
        baudrate=9600,             # Matches Switch 2 OFF
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=1.0
    )
    
    # 1. Initialize Address Command (Tells the camera chain to assign IDs)
    # Camera 1 receives 0x81 as its header address.
    ser.write(bytes([0x88, 0x30, 0x01, 0xFF]))
    time.sleep(0.5)
    ser.reset_input_buffer()
    
    print(f"Connected to BRC-300 on {COM_PORT}. Ready for commands.")

    def send_visca_command(command_bytes):
        """Helper to clear buffer, send a command, and check for ACK/Completion."""
        ser.reset_input_buffer()
        ser.write(bytes(command_bytes))
        ser.flush()
        
        # Read the feedback bytes from the camera (typically 4-5 bytes max)
        response = ser.read(5)
        return response

    def move_camera(pan_dir, tilt_dir, pan_speed=0x0F, tilt_speed=0x0F):
        """
        Controls motion direction.
        Directions: 
          pan_dir:  0x01 (Left), 0x02 (Right), 0x03 (Stop)
          tilt_dir: 0x01 (Up),   0x02 (Down),  0x03 (Stop)
        """
        # VISCA Command Structure: Pan/Tilt Drive
        cmd = [0x81, 0x01, 0x06, 0x01, pan_speed, tilt_speed, pan_dir, tilt_dir, 0xFF]
        send_visca_command(cmd)

    def stop_camera():
        """Sends the stop command to halt all active pan/tilt movements."""
        response = send_visca_command(
            [0x81, 0x01, 0x06, 0x01, 0x10, 0x10, 0x03, 0x03, 0xFF]
        )
        if response:
            print(f"Stop response: {response.hex(' ').upper()}")
        else:
            print("No VISCA response to stop command.")

    def close_port():
        if ser.is_open:
            # Make sure the camera isn't stuck moving before disconnecting
            try:
                stop_camera()
            except serial.SerialException as e:
                print(f"Could not send stop command: {e}")
            finally:
                ser.close()
                print("Port safely closed.")

    def on_press(key):
        if key == keyboard.Key.left:
            move_camera(pan_dir=0x01,tilt_dir=0x03,pan_speed=0x10)

        elif key == keyboard.Key.right:
            move_camera(pan_dir=0x02,tilt_dir=0x03,pan_speed=0x10)

        elif key == keyboard.Key.up:
            move_camera(pan_dir=0x03,tilt_dir=0x01,tilt_speed=0x10)

        elif key == keyboard.Key.down:
            move_camera(pan_dir=0x03,tilt_dir=0x02,tilt_speed=0x10)

        elif key == keyboard.Key.esc:
            close_port()
            return False

    def on_release(key):
        if key == keyboard.Key.left:
            stop_camera()
        if key == keyboard.Key.right:
            stop_camera()
        if key == keyboard.Key.up:
            stop_camera()
        if key == keyboard.Key.down:
            stop_camera()

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()

except serial.SerialException as e:
    print(f"Serial Error: {e}")