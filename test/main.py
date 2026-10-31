import time
import serial
import keyboard

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

    # ==========================================
    # EXECUTION DEMO
    # ==========================================
    
    # Pan Left and Up simultaneously
    print("Moving Left and Up...")
    move_camera(pan_dir=0x01, tilt_dir=0x01, pan_speed=0x10, tilt_speed=0x10)
    time.sleep(5.0)

    # Pan Right and Down at a moderate speed (0x10) for 2 seconds
    print("Panning Right and Down...")
    move_camera(pan_dir=0x02, tilt_dir=0x02, pan_speed=0x10, tilt_speed=0x10)
    time.sleep(2.0)
    
    # Crucial: Always stop the motor loop, otherwise it keeps moving indefinitely!
    print("Stopping motion.")
    stop_camera()

except serial.SerialException as e:
    print(f"Serial Error: {e}")
finally:
    if 'ser' in locals() and ser.is_open:
        # Make sure the camera isn't stuck moving before disconnecting
        try:
            stop_camera()
        except:
            pass
        ser.close()
        print("Port safely closed.")


# Action pan_dir	    tilt_dir	Complete Packet Sequence (at Speed 0x0F)
# Up	 0x03 (Stop)	0x01 (Up)	81 01 06 01 0F 0F 03 01 FF
# Down	 0x03 (Stop)	0x02 (Down)	81 01 06 01 0F 0F 03 02 FF
# Left	 0x01 (Left)	0x03 (Stop)	81 01 06 01 0F 0F 01 03 FF
# Right	 0x02 (Right)   0x03 (Stop)	81 01 06 01 0F 0F 02 03 FF
# Stop	 0x03 (Stop)	0x03 (Stop)	81 01 06 01 00 00 03 03 FF