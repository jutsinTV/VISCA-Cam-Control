import cv2
import mediapipe as mp
import os
import serial
import time
from pynput import keyboard
from threading import Event, Lock

# Windows COM Port (Check Device Manager for your specific port)
COM_PORT = 'COM3' 
CAMERA_INDEX = 1
FACE_MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "blaze_face_short_range.tflite"
)
OBJECT_MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "efficientdet_lite0.tflite"
)
TRACKING_PAN_SPEED = 0x14 # Max is 0x18
TRACKING_TILT_SPEED = 0x14 # Max is 0x14
TRACKING_ZOOM_SPEED = 0x07 # Max is 0x07
TRACKING_DEADBAND_X = 0.13
TRACKING_DEADBAND_Y = 0.13
TRACKING_ZOOM_IN_THRESHOLD = 0.20
TRACKING_ZOOM_OUT_THRESHOLD = 0.34

cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
if not cap.isOpened():
    cap.release()
    cap = cv2.VideoCapture(CAMERA_INDEX)

camID = 0x81

current_modifiers = set()
stop_event = Event()
serial_lock = Lock()
serial_warning_shown = False
ser = None
tracking_enabled = False
object_detection_enabled = False
tracking_zoom_enabled = False
detection_overlay_enabled = True
face_detector = None
object_detector = None
tracking_command = (0x03, 0x03)
tracking_zoom_direction = 0x00

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
overlay_toggle_vk = 86
object_detection_toggle_vk = 79

camera_control_vks = {
    np1, np2, np3, np4, np5, np6, np7, np8, np9,
    npplu, npmin, npdiv, npmul, overlay_toggle_vk,
    object_detection_toggle_vk,
}
pressed_camera_controls = set()

if not cap.isOpened():
    raise RuntimeError(
        f"Could not open camera index {CAMERA_INDEX}. Check that the camera is connected, "
        "not in use by another application, and that the correct camera index is selected."
    )

try:
    # Open connection to the BRC-300 using Sony VISCA specs
    try:
        ser = serial.Serial(
            port=COM_PORT,
            baudrate=9600,             # Matches Switch 2 OFF
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0
        )

        # Initialize the camera chain address without blocking video startup.
        ser.write(bytes([0x88, 0x30, 0x01, 0xFF]))
        ser.flush()
        time.sleep(0.5)
        ser.reset_input_buffer()
    except serial.SerialException as e:
        if ser is not None and ser.is_open:
            ser.close()
        ser = None
        print(
            f"VISCA unavailable on {COM_PORT}: {e}. "
            "Video preview will continue, but PTZ control will not work."
        )
    
    if ser is not None:
        print(f"Connected to BRC-300 on {COM_PORT}. Ready for commands.")
    print("Camera preview starting. Press T to toggle face tracking.")

# =========================================================================
# BASIC FUNCTIONS
# =========================================================================
    def send_visca_command(command_bytes):
        """Send a VISCA command without blocking the video loop for a reply."""
        global serial_warning_shown, ser

        if ser is None or not ser.is_open:
            if not serial_warning_shown:
                print("PTZ command skipped because the VISCA serial connection is unavailable.")
                serial_warning_shown = True
            return b""

        try:
            with serial_lock:
                ser.reset_input_buffer()
                ser.write(bytes(command_bytes))
                ser.flush()
        except serial.SerialException as e:
            print(f"VISCA connection lost on {COM_PORT}: {e}. Video preview will continue.")
            try:
                if ser.is_open:
                    ser.close()
            except serial.SerialException as close_error:
                print(f"Could not close the disconnected VISCA port: {close_error}")
            ser = None
        return b""

    def close_port():
        if ser is not None and ser.is_open:
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

    def create_face_detector():
        if not os.path.isfile(FACE_MODEL_PATH):
            raise FileNotFoundError(
                f"Face tracking model not found: {FACE_MODEL_PATH}. "
                "Download blaze_face_short_range.tflite from the MediaPipe "
                "face detector model repository and place it beside this script."
            )

        options = mp.tasks.vision.FaceDetectorOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=FACE_MODEL_PATH),
            min_detection_confidence=0.5,
        )
        return mp.tasks.vision.FaceDetector.create_from_options(options)

    def create_object_detector():
        if not os.path.isfile(OBJECT_MODEL_PATH):
            raise FileNotFoundError(
                f"Object detection model not found: {OBJECT_MODEL_PATH}."
            )

        options = mp.tasks.vision.ObjectDetectorOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=OBJECT_MODEL_PATH),
            score_threshold=0.3,
        )
        return mp.tasks.vision.ObjectDetector.create_from_options(options)

    def stop_face_tracking():
        global tracking_command, tracking_zoom_direction

        if tracking_command != (0x03, 0x03):
            move_camera(
                pan_dir=0x03,
                tilt_dir=0x03,
                pan_speed=TRACKING_PAN_SPEED,
                tilt_speed=TRACKING_TILT_SPEED,
            )
            tracking_command = (0x03, 0x03)
        if tracking_zoom_direction != 0x00:
            zoom_stop()
            tracking_zoom_direction = 0x00

    def track_face(frame):
        global tracking_command, tracking_zoom_direction

        if face_detector is None:
            raise RuntimeError("Face detector has not been initialized.")

        height, width = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = face_detector.detect(image)
        detections = result.detections
        if not detections:
            stop_face_tracking()
            return None

        face = max(
            detections,
            key=lambda detection: (
                detection.bounding_box.width * detection.bounding_box.height
            ),
        )
        box = face.bounding_box
        center_x = box.origin_x + box.width / 2
        center_y = box.origin_y + box.height / 2
        error_x = center_x / width - 0.5
        error_y = center_y / height - 0.5

        pan_dir = 0x03
        if error_x < -TRACKING_DEADBAND_X:
            pan_dir = 0x01
        elif error_x > TRACKING_DEADBAND_X:
            pan_dir = 0x02

        tilt_dir = 0x03
        if error_y < -TRACKING_DEADBAND_Y:
            tilt_dir = 0x01
        elif error_y > TRACKING_DEADBAND_Y:
            tilt_dir = 0x02

        command = (pan_dir, tilt_dir)
        if command != tracking_command:
            move_camera(
                pan_dir=pan_dir,
                tilt_dir=tilt_dir,
                pan_speed=TRACKING_PAN_SPEED,
                tilt_speed=TRACKING_TILT_SPEED,
            )
            tracking_command = command

        zoom_direction = 0x00
        face_width = box.width / width
        if tracking_zoom_enabled:
            if face_width < TRACKING_ZOOM_IN_THRESHOLD:
                zoom_direction = 0x20
            elif face_width > TRACKING_ZOOM_OUT_THRESHOLD:
                zoom_direction = 0x30

        if zoom_direction != tracking_zoom_direction:
            if zoom_direction == 0x20:
                zoom_in(speed=TRACKING_ZOOM_SPEED)
            elif zoom_direction == 0x30:
                zoom_out(speed=TRACKING_ZOOM_SPEED)
            elif tracking_zoom_direction != 0x00:
                zoom_stop()
            tracking_zoom_direction = zoom_direction

        return (
            box.origin_x,
            box.origin_y,
            box.origin_x + box.width,
            box.origin_y + box.height,
        )

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
        global tracking_enabled, object_detection_enabled
        global tracking_zoom_enabled, detection_overlay_enabled

        if key == keyboard.Key.esc:
            stop_event.set()
            return False

        virtual_key = getattr(key, 'vk', None)
        if virtual_key in camera_control_vks:
            if virtual_key in pressed_camera_controls:
                return
            pressed_camera_controls.add(virtual_key)

        pressed_char = getattr(key, 'char', None)
        if pressed_char in {'t', 'T'}:
            tracking_enabled = not tracking_enabled
            if tracking_enabled:
                object_detection_enabled = False
            print(f"Face tracking {'enabled' if tracking_enabled else 'disabled'}.")
            return
        if pressed_char in {'o', 'O'}:
            object_detection_enabled = not object_detection_enabled
            if object_detection_enabled:
                tracking_enabled = False
            print(
                f"Object detection "
                f"{'enabled' if object_detection_enabled else 'disabled'}."
            )
            return
        if pressed_char in {'z', 'Z'}:
            tracking_zoom_enabled = not tracking_zoom_enabled
            print(f"Tracking zoom {'enabled' if tracking_zoom_enabled else 'disabled'}.")
            return
        if pressed_char in {'v', 'V'}:
            detection_overlay_enabled = not detection_overlay_enabled
            print(f"Detection overlay {'shown' if detection_overlay_enabled else 'hidden'}.")
            return

        if key in {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}:
            current_modifiers.add(key)
            return

        if tracking_enabled:
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

    def on_release(key):
        virtual_key = getattr(key, 'vk', None)
        pressed_camera_controls.discard(virtual_key)

        if key in {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}:
            current_modifiers.discard(key)
        if tracking_enabled and virtual_key in {
            np1, np2, np3, np4, np5, np6, np7, np8, np9,
            npplu, npmin, npdiv, npmul,
        }:
            return
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


    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    cv2.namedWindow('Video', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Video', 960, 720)

    tracking_was_enabled = False
    detection_error = None
    while not stop_event.is_set():
        ret, frame = cap.read()
        if not ret:
            print(f"Could not read a frame from camera index {CAMERA_INDEX}; stopping preview.")
            break

        face_box = None
        object_detections = None
        if tracking_enabled:
            try:
                if face_detector is None:
                    face_detector = create_face_detector()
                    detection_error = None
                if not tracking_was_enabled:
                    move_camera(
                        pan_dir=0x03,
                        tilt_dir=0x03,
                        pan_speed=TRACKING_PAN_SPEED,
                        tilt_speed=TRACKING_TILT_SPEED,
                    )
                    zoom_stop()
                    tracking_command = (0x03, 0x03)
                    tracking_zoom_direction = 0x00
                face_box = track_face(frame)
                tracking_was_enabled = True
            except (FileNotFoundError, OSError, RuntimeError, ValueError) as e:
                detection_error = str(e)
                print(f"Face tracking error: {detection_error}")
                tracking_enabled = False
                stop_face_tracking()
                tracking_was_enabled = False
        elif tracking_was_enabled:
            stop_face_tracking()
            tracking_was_enabled = False
        if object_detection_enabled:
            try:
                if object_detector is None:
                    object_detector = create_object_detector()
                    detection_error = None
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                object_detections = object_detector.detect(image).detections
            except (FileNotFoundError, OSError, RuntimeError, ValueError) as e:
                detection_error = str(e)
                print(f"Object detection error: {detection_error}")
                object_detection_enabled = False
        if detection_overlay_enabled:
            if face_box is not None:
                left, top, right, bottom = face_box
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
            if object_detections is not None:
                for detection in object_detections:
                    box = detection.bounding_box
                    left = box.origin_x
                    top = box.origin_y
                    right = left + box.width
                    bottom = top + box.height
                    cv2.rectangle(
                        frame, (left, top), (right, bottom), (255, 180, 0), 2
                    )

                    category = detection.categories[0] if detection.categories else None
                    if category is not None:
                        label = f"{category.category_name} {category.score:.0%}"
                        cv2.putText(
                            frame,
                            label,
                            (left, max(15, top - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (255, 180, 0),
                            2,
                        )
            tracking_status = "ON" if tracking_enabled else "OFF"
            object_status = "ON" if object_detection_enabled else "OFF"
            zoom_status = "ON" if tracking_zoom_enabled else "OFF"
            cv2.putText(
                frame,
                f"Face tracking: {tracking_status} (T) | "
                f"Object detection: {object_status} (O) | "
                f"Auto zoom: {zoom_status} (Z)",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0) if tracking_enabled or object_detection_enabled
                else (255, 255, 255),
                2,
            )
        if detection_error:
            cv2.putText(
                frame,
                detection_error[:100],
                (10, 58),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 0, 255),
                1,
            )
        if ser is None:
            cv2.putText(
                frame,
                f"VISCA offline: check {COM_PORT}",
                (10, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 255),
                1,
            )
        cv2.imshow('Video', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

except serial.SerialException as e:
    print(f"Serial Error: {e}")
except Exception as e:
    print(f"Error occurred: {e}")

finally:
    if 'listener' in locals() and listener.is_alive():
        listener.stop()
        listener.join()
    if 'stop_face_tracking' in locals():
        try:
            stop_face_tracking()
        except serial.SerialException as e:
            print(f"Could not stop face tracking: {e}")
    if 'close_port' in locals():
        close_port()
    if face_detector is not None:
        face_detector.close()
    if object_detector is not None:
        object_detector.close()
    cap.release()
    cv2.destroyAllWindows()
