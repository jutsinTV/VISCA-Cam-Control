import serial
import time
from pynput import keyboard

# Windows COM Port (Check Device Manager for your specific port)
COM_PORT = 'COM3' 

camID = 0x81

current_modifiers = set()

np1 = 97
np2 = 98
np3 = 99
np4 = 100
np5 = 101
np6 = 102
np7 = 103
np8 = 104
np9 = 105
npdiv = 111
npmul = 106
npmin = 109
npplu = 107
npent = 13
npdec = 110

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

# =========================================================================
# BASIC FUNCTIONS
# =========================================================================
    def send_visca_command(command_bytes):
        """Helper to clear buffer, send a command, and check for ACK/Completion."""
        ser.reset_input_buffer()
        ser.write(bytes(command_bytes))
        ser.flush()
        
        # Read the feedback bytes from the camera (typically 4-5 bytes max)
        response = ser.read(5)
        return response

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

# =========================================================================
# MOVEMENT FUNCTIONS
# =========================================================================
    def move_camera(pan_dir, tilt_dir, pan_speed=0x0F, tilt_speed=0x0F):
        """
        Controls motion direction.
        Directions: 
          pan_dir:  0x01 (Left), 0x02 (Right), 0x03 (Stop)
          tilt_dir: 0x01 (Up),   0x02 (Down),  0x03 (Stop)
        """
        # VISCA Command Structure: Pan/Tilt Drive
        cmd = [camID, 0x01, 0x06, 0x01, pan_speed, tilt_speed, pan_dir, tilt_dir, 0xFF]
        send_visca_command(cmd)

    def stop_camera():
        """Sends the stop command to halt all active pan/tilt movements."""
        response = send_visca_command(
            [camID, 0x01, 0x06, 0x01, 0x10, 0x10, 0x03, 0x03, 0xFF]
        )
        if response:
            print(f"Stop response: {response.hex(' ').upper()}")
        else:
            print("No VISCA response to stop command.")

# =========================================================================
# ZOOM FUNCTIONS
# =========================================================================
    def zoom_in(speed=0x04):
        """Zoom In closer. Variable speed from 0x00 (low) to 0x07 (high)."""
        # Form: 81 01 04 07 2X FF (where X is 0-7 speed parameter combined into upper nibble)
        cmd = [camID, 0x01, 0x04, 0x07, (0x20 | (speed & 0x0F)), 0xFF]
        send_visca_command(cmd)

    def zoom_out(speed=0x04):
        """Zoom Out further. Variable speed from 0x00 (low) to 0x07 (high)."""
        # Form: 81 01 04 07 2X FF (where X is 0-7 speed parameter combined into upper nibble)
        cmd = [camID, 0x01, 0x04, 0x07, (0x30 | (speed & 0x0F)), 0xFF]
        send_visca_command(cmd)

    def zoom_stop():
        send_visca_command([camID, 0x01, 0x04, 0x07, 0x00, 0xFF])

# =========================================================================
# FOCUS FUNCTIONS
# =========================================================================
    def set_focus_mode(auto=True):
        """Switch focal system between Auto Focus and Manual Focus."""
        mode_byte = 0x02 if auto else 0x03
        send_visca_command([camID, 0x01, 0x04, 0x38, mode_byte, 0xFF])

    def focus_far(speed=0x06):
        """Manually drive focus further away (Far). Speed 0x00 to 0x07."""
        cmd = [camID, 0x01, 0x04, 0x08, (0x20 | (speed & 0x0F)), 0xFF]
        send_visca_command(cmd)

    def focus_near(speed=0x06):
        """Manually drive focus up close (Near). Speed 0x00 to 0x07."""
        cmd = [camID, 0x01, 0x04, 0x08, (0x30 | (speed & 0x0F)), 0xFF]
        send_visca_command(cmd)

    def focus_stop():
        """Halt manual adjustment lines on the focus lens."""
        send_visca_command([camID, 0x01, 0x04, 0x08, 0x00, 0xFF])

# =========================================================================
# POSITION PRESET MEMORY FUNCTIONS
# =========================================================================
    def preset_store(preset_number):
        """
        Saves current pan, tilt, zoom, and focus values into internal memory.
        The BRC-300 typically supports slots 0 through 5.
        """
        if not (0 <= preset_number <= 5):
            print("Error: BRC-300 standard presets range from 0 to 5.")
            return
        # Form: 81 01 04 3F 01 [Memory #] FF
        cmd = [camID, 0x01, 0x04, 0x3F, 0x01, preset_number, 0xFF]
        send_visca_command(cmd)
        print(f"Stored current position to Preset #{preset_number}")

    def preset_recall(preset_number):
        """Instantly commands the hardware to run to a stored memory index."""
        if not (0 <= preset_number <= 5):
            return
        # Form: 81 01 04 3F 02 [Memory #] FF
        cmd = [camID, 0x01, 0x04, 0x3F, 0x02, preset_number, 0xFF]
        send_visca_command(cmd)
        print(f"Recalling Preset #{preset_number}...")

# =========================================================================
# KEYBINDINGS
# =========================================================================
    def on_press(key):
        if key in {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}:
            current_modifiers.add(key)
            return

        try:
            if hasattr(key, 'vk') and key.vk == np4:
                move_camera(pan_dir=0x01,tilt_dir=0x03,pan_speed=0x10)

            elif hasattr(key, 'vk') and key.vk == np6:
                move_camera(pan_dir=0x02,tilt_dir=0x03,pan_speed=0x10)

            elif hasattr(key, 'vk') and key.vk == np8:
                move_camera(pan_dir=0x03,tilt_dir=0x01,tilt_speed=0x10)

            elif hasattr(key, 'vk') and key.vk == np2:
                move_camera(pan_dir=0x03,tilt_dir=0x02,tilt_speed=0x10)

            elif hasattr(key, 'vk') and key.vk == np1:
                move_camera(pan_dir=0x01,tilt_dir=0x02,pan_speed=0x10,tilt_speed=0x10)

            elif hasattr(key, 'vk') and key.vk == np3:
                move_camera(pan_dir=0x02,tilt_dir=0x02,pan_speed=0x10,tilt_speed=0x10)

            elif hasattr(key, 'vk') and key.vk == np7:
                move_camera(pan_dir=0x01,tilt_dir=0x01,pan_speed=0x10,tilt_speed=0x10)

            elif hasattr(key, 'vk') and key.vk == np9:
                move_camera(pan_dir=0x02,tilt_dir=0x01,pan_speed=0x10,tilt_speed=0x10)

            elif hasattr(key, 'vk') and key.vk == npplu:
                zoom_in()

            elif hasattr(key, 'vk') and key.vk == npmin:
                zoom_out()

            elif hasattr(key, 'vk') and key.vk == npdiv:
                focus_near()

            elif hasattr(key, 'vk') and key.vk == npmul:
                focus_far()

            elif hasattr(key, 'vk') and key.vk == np5:
                set_focus_mode()


            else:
                digit = getattr(key, 'char', None)
                virtual_key = getattr(key, 'vk', None)
                if digit not in {'1', '2', '3', '4', '5', '6'} and isinstance(virtual_key, int):
                    if 49 <= virtual_key <= 54:
                        digit = chr(virtual_key)

                if digit in {'1', '2', '3', '4', '5', '6'}:
                    preset_number = int(digit) - 1
                    if current_modifiers:
                        preset_store(preset_number)
                    else:
                        preset_recall(preset_number)

        except AttributeError:
            # Handles special non-character keys like Shift, Ctrl, etc.
            pass


        
        
        if key == keyboard.Key.esc:
            close_port()
            return False

    def on_release(key):
        if key in {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}:
            current_modifiers.discard(key)
        try:
            if hasattr(key, 'vk') and key.vk == np1:
                stop_camera()

            elif hasattr(key, 'vk') and key.vk == np2:
                stop_camera()

            elif hasattr(key, 'vk') and key.vk == np3:
                stop_camera()

            elif hasattr(key, 'vk') and key.vk == np4:
                stop_camera()

            elif hasattr(key, 'vk') and key.vk == np5:
                stop_camera()
            
            elif hasattr(key, 'vk') and key.vk == np6:
                stop_camera()
            
            elif hasattr(key, 'vk') and key.vk == np7:
                stop_camera()

            elif hasattr(key, 'vk') and key.vk == np8:
                stop_camera()

            elif hasattr(key, 'vk') and key.vk == np9:
                stop_camera()

            elif hasattr(key, 'vk') and key.vk == npplu:
                zoom_stop()

            elif hasattr(key, 'vk') and key.vk == npmin:
                zoom_stop()

            elif hasattr(key, 'vk') and key.vk == npdiv:
                focus_stop()

            elif hasattr(key, 'vk') and key.vk == npmul:
                focus_stop()

            elif hasattr(key, 'char') and key.char == 'a':
                global camID
                if camID == 0x81:
                    camID = 0x82
                    print("Switched to camera 2")
                elif camID == 0x82:
                    camID = 0x81
                    print("Switched to camera 1")
                
        except AttributeError:
            # Handles special non-character keys like Shift, Ctrl, etc.
            pass


    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()

except serial.SerialException as e:
    print(f"Serial Error: {e}")