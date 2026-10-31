import cv2
import tkinter as tk
import serial
import time
from pynput import keyboard
from threading import Event
from tkinter import messagebox
from PIL import Image, ImageTk


class SingleVideoApp:
    def __init__(self, window, title="PTZ Camera Feed"):
        self.window = window
        self.window.title(title)
        self.video_image = None

        self.COM_PORT = "COM3"  # Update this to your camera's serial port
        
        # 1. Initialize the single video capture device
        # 0 is typically the built-in webcam. Change to 1 or 2 if using an external device.
        self.cap = cv2.VideoCapture(0)

        # Default camera ID for the device, can be modified if needed
        self.camID = 0x81

        # Initialize the keyboard listener for modifier key detection
        self.current_modifiers = set()

        # Initialize a threading event to manage the video feed loop
        self.stop_event = Event()

        # Numpad key mapping for camera motion control
        self.np0 = 96  # Numpad 0
        self.np1 = 97  # Numpad 1
        self.np2 = 98  # Numpad 2
        self.np3 = 99  # Numpad 3
        self.np4 = 100 # Numpad 4
        self.np5 = 101 # Numpad 5
        self.np6 = 102 # Numpad 6
        self.np7 = 103 # Numpad 7
        self.np8 = 104 # Numpad 8
        self.np9 = 105 # Numpad 9
        self.np_plus = 107  # Numpad +
        self.np_minus = 109 # Numpad -
        self.np_enter = 13   # Numpad Enter
        self.np_divide = 111 # Numpad /
        self.np_multiply = 106 # Numpad *
        self.np_decimal = 110 # Numpad Decimal
        
        if not self.cap.isOpened():
            messagebox.showerror("Device Error", "Could not open the video capture device.")
            exit()
            self.window.destroy()
            return

        # 2. Setup Tkinter UI Layout Elements
        self.main_frame = tk.Frame(self.window, padx=10, pady=10)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Label layout acting as the video view screen
        self.video_label = tk.Label(
            self.main_frame, bd=2, relief="groove", width=640, height=480
        )
        self.video_label.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=5)
        
        # Clean control button beneath the frame layout
        self.quit_button = tk.Button(
            self.main_frame, 
            text="Exit Stream", 
            command=self.on_closing,
            width=15,
            bg="#d9534f",
            fg="white"
        )
        self.quit_button.pack(side=tk.BOTTOM, pady=5)
        
        # Handle the standard window close 'X' frame action safely
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # 3. Kick off the asynchronous video rendering cycle
        self.update_video_feed()

    def update_video_feed(self):
        # Capture a single frame from the device matrix
        ret, frame = self.cap.read()
        
        if ret:
            # Convert OpenCV's standard BGR array format to RGB format for PIL
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Convert arrays to PIL Image objects, then bind to Tkinter PhotoImage references
            pil_img = Image.fromarray(rgb_frame)
            available_width = max(self.video_label.winfo_width() - 4, 1)
            available_height = max(self.video_label.winfo_height() - 4, 1)
            scale = min(
                available_width / pil_img.width,
                available_height / pil_img.height,
            )
            if scale != 1:
                pil_img = pil_img.resize(
                    (
                        max(int(pil_img.width * scale), 1),
                        max(int(pil_img.height * scale), 1),
                    ),
                    Image.Resampling.LANCZOS,
                )
            tk_img = ImageTk.PhotoImage(image=pil_img)
            
            # Save an explicit structural reference to block garbage collection cleanup
            self.video_image = tk_img
            self.video_label.configure(image=tk_img)
            
        # Schedule next loop step execution iteration roughly 15ms out (~60 FPS target range)
        self.window.after(15, self.update_video_feed)

    def on_closing(self):
        # Safe breakdown routine releasing hardware handles
        self.stop_event.set()
        if self.cap.isOpened():
            self.cap.release()
        self.window.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = SingleVideoApp(root)
    try:
        # Open serial connection to the camera device for PTZ control
        ser = serial.Serial(
            port=app.COM_PORT,
            baudrate=9600,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1.0
        )

        # Initialize Address Command to set the camera chain IDs
        address_command = bytes([0xFF, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        ser.write(address_command)
        time.sleep(0.5)  # Allow time for the command to be processed
        ser.reset_input_buffer()  # Clear any residual data in the input buffer

        print(f"Serial port {app.COM_PORT} opened successfully for camera control.")

        def send_visca_command(command_bytes):
            """Send a VISCA command to the camera via serial."""
            try:
                ser.write(bytes(command_bytes))
                time.sleep(0.1)  # Allow time for the command to be processed
                ser.flush()  # Ensure all data is sent
            except serial.SerialException as e:
                messagebox.showerror("Serial Port Error", f"Failed to send command: {e}")

        def close_port():
            """Close the serial port safely."""
            if ser.is_open:
                try:
                    stop_camera()  # Ensure the camera is stopped before closing
                except serial.SerialException as e:
                    messagebox.showerror("Serial Port Error", f"Failed to close serial port: {e}")
                finally:
                    ser.close()
                    print(f"Serial port {app.COM_PORT} closed.")

        def switch_camera(cam_id):
            """Switch between camera IDs (0x81 or 0x82)."""
            if cam_id in {0x81, 0x82}:
                app.camID = cam_id
                print(f"Switched to camera ID: {hex(cam_id)}")
            else:
                print("Error: Invalid camera ID. Use 0x81 or 0x82.")

        def move_camera(pan_dir, tilt_dir, pan_speed=0x18, tilt_speed=0x14):
            """Move the camera in the specified direction with given speeds."""
            command = [
                app.camID, 0x01, 0x06, 0x01,
                pan_speed, tilt_speed, pan_dir, tilt_dir, 0xFF
            ]
            send_visca_command(command)

        def stop_camera():
            """Stop the camera's movement."""
            command = [app.camID, 0x01, 0x06, 0x01, 0x10, 0x10, 0x03, 0x03, 0xFF]
            send_visca_command(command)

        def zoom_in(speed=0x04):
            """Zoom In closer. Variable speed from 0x00 (low) to 0x07 (high)."""
            # Form: 81 01 04 07 2X FF (where X is 0-7 speed parameter combined into upper nibble)
            cmd = [app.camID, 0x01, 0x04, 0x07, (0x20 | (speed & 0x0F)), 0xFF]
            send_visca_command(cmd)

        def zoom_out(speed=0x04):
            """Zoom Out farther. Variable speed from 0x00 (low) to 0x07 (high)."""
            # Form: 81 01 04 07 3X FF (where X is 0-7 speed parameter combined into upper nibble)
            cmd = [app.camID, 0x01, 0x04, 0x07, (0x30 | (speed & 0x0F)), 0xFF]
            send_visca_command(cmd)

        def zoom_stop():
            """Stop the camera's zoom action."""
            cmd = [app.camID, 0x01, 0x04, 0x07, 0x00, 0xFF]
            send_visca_command(cmd)

        def set_focus_mode(auto=True):
            """Switch focal system between Auto Focus and Manual Focus."""
            mode_byte = 0x02 if auto else 0x03
            send_visca_command([app.camID, 0x01, 0x04, 0x38, mode_byte, 0xFF])

        def focus_far(speed=0x06):
            """Manually drive focus further away (Far). Speed 0x00 to 0x07."""
            cmd = [app.camID, 0x01, 0x04, 0x08, (0x20 | (speed & 0x0F)), 0xFF]
            send_visca_command(cmd)

        def focus_near(speed=0x06):
            """Manually drive focus up close (Near). Speed 0x00 to 0x07."""
            cmd = [app.camID, 0x01, 0x04, 0x08, (0x30 | (speed & 0x0F)), 0xFF]
            send_visca_command(cmd)

        def focus_stop():
            """Halt manual adjustment lines on the focus lens."""
            send_visca_command([app.camID, 0x01, 0x04, 0x08, 0x00, 0xFF])

        def preset_store(preset_number):
            """
            Saves current pan, tilt, zoom, and focus values into internal memory.
            The BRC-300 typically supports slots 0 through 5.
            """
            if not (0 <= preset_number <= 5):
                print("Error: BRC-300 standard presets range from 0 to 5.")
                return
            # Form: 81 01 04 3F 01 [Memory #] FF
            cmd = [app.camID, 0x01, 0x04, 0x3F, 0x01, preset_number, 0xFF]
            send_visca_command(cmd)
            print(f"Stored current position to Preset #{preset_number}")

        def preset_recall(preset_number):
            """Instantly commands the hardware to run to a stored memory index."""
            if not (0 <= preset_number <= 5):
                return
            # Form: 81 01 04 3F 02 [Memory #] FF
            cmd = [app.camID, 0x01, 0x04, 0x3F, 0x02, preset_number, 0xFF]
            send_visca_command(cmd)
            print(f"Recalling Preset #{preset_number}...")

        def on_press(key):
            if key == keyboard.Key.esc:
                app.stop_event.set()
                app.window.after(0, app.on_closing)
                return False

            if key in {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}:
                app.current_modifiers.add(key)
                return

            try:
                if hasattr(key, 'vk') and key.vk == app.np4:
                    move_camera(pan_dir=0x01,tilt_dir=0x03,pan_speed=0x10)

                elif hasattr(key, 'vk') and key.vk == app.np6:
                    move_camera(pan_dir=0x02,tilt_dir=0x03,pan_speed=0x10)

                elif hasattr(key, 'vk') and key.vk == app.np8:
                    move_camera(pan_dir=0x03,tilt_dir=0x01,tilt_speed=0x10)

                elif hasattr(key, 'vk') and key.vk == app.np2:
                    move_camera(pan_dir=0x03,tilt_dir=0x02,tilt_speed=0x10)

                elif hasattr(key, 'vk') and key.vk == app.np1:
                    move_camera(pan_dir=0x01,tilt_dir=0x02,pan_speed=0x10,tilt_speed=0x10)

                elif hasattr(key, 'vk') and key.vk == app.np3:
                    move_camera(pan_dir=0x02,tilt_dir=0x02,pan_speed=0x10,tilt_speed=0x10)

                elif hasattr(key, 'vk') and key.vk == app.np7:
                    move_camera(pan_dir=0x01,tilt_dir=0x01,pan_speed=0x10,tilt_speed=0x10)

                elif hasattr(key, 'vk') and key.vk == app.np9:
                    move_camera(pan_dir=0x02,tilt_dir=0x01,pan_speed=0x10,tilt_speed=0x10)

                elif hasattr(key, 'vk') and key.vk == app.np_plus:
                    zoom_in()

                elif hasattr(key, 'vk') and key.vk == app.np_minus:
                    zoom_out()

                elif hasattr(key, 'vk') and key.vk == app.np_divide:
                    focus_near()

                elif hasattr(key, 'vk') and key.vk == app.np_multiply:
                    focus_far()

                elif hasattr(key, 'vk') and key.vk == app.np5:
                    set_focus_mode()


                else:
                    digit = getattr(key, 'char', None)
                    virtual_key = getattr(key, 'vk', None)
                    if digit not in {'1', '2', '3', '4', '5', '6'} and isinstance(virtual_key, int):
                        if 49 <= virtual_key <= 54:
                            digit = chr(virtual_key)

                    if digit in {'1', '2', '3', '4', '5', '6'}:
                        preset_number = int(digit) - 1
                        if app.current_modifiers:
                            preset_store(preset_number)
                        else:
                            preset_recall(preset_number)

            except AttributeError:
                # Handles special non-character keys like Shift, Ctrl, etc.
                pass

        def on_release(key):
            if key in {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}:
                app.current_modifiers.discard(key)
            try:
                if hasattr(key, 'vk') and key.vk == app.np1:
                    stop_camera()

                elif hasattr(key, 'vk') and key.vk == app.np2:
                    stop_camera()

                elif hasattr(key, 'vk') and key.vk == app.np3:
                    stop_camera()

                elif hasattr(key, 'vk') and key.vk == app.np4:
                    stop_camera()

                elif hasattr(key, 'vk') and key.vk == app.np5:
                    stop_camera()
                
                elif hasattr(key, 'vk') and key.vk == app.np6:
                    stop_camera()
                
                elif hasattr(key, 'vk') and key.vk == app.np7:
                    stop_camera()

                elif hasattr(key, 'vk') and key.vk == app.np8:
                    stop_camera()

                elif hasattr(key, 'vk') and key.vk == app.np9:
                    stop_camera()

                elif hasattr(key, 'vk') and key.vk == app.np_plus:
                    zoom_stop()

                elif hasattr(key, 'vk') and key.vk == app.np_minus:
                    zoom_stop()

                elif hasattr(key, 'vk') and key.vk == app.np_divide:
                    focus_stop()

                elif hasattr(key, 'vk') and key.vk == app.np_multiply:
                    focus_stop()

                elif hasattr(key, 'char') and key.char == 'a':
                    global camID
                    if app.camID == 0x81:
                        app.camID = 0x82
                        print("Switched to camera 2")
                    elif app.camID == 0x82:
                        app.camID = 0x81
                        print("Switched to camera 1")
                    
            except AttributeError:
                # Handles special non-character keys like Shift, Ctrl, etc.
                pass

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()
        root.mainloop()

    except serial.SerialException as e:
        messagebox.showerror("Serial Port Error", f"Could not open serial port {app.COM_PORT}: {e}")
        exit()

    except Exception as e:
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")
        exit()

    finally:
        if 'listener' in locals() and listener.is_alive():
            listener.stop()
            listener.join()
        if 'close_port' in locals():
            close_port()
        app.cap.release()
        cv2.destroyAllWindows()