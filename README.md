# VISCA-Cam-Control-RS232

## Face tracking and object detection prototype

Run `test/faceDetectTest.py` with the camera and VISCA serial connection configured.
Set `COM_PORT` and `CAMERA_INDEX` near the top of the script to match your setup.
The preview still opens if the VISCA serial port is unavailable, but pan/tilt
commands require a working serial connection. The script expects the MediaPipe
`blaze_face_short_range.tflite` face model beside the script. Download it from:

https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite

For object detection, place the `efficientdet_lite0.tflite` model beside the
script. Download it from:

https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/int8/1/efficientdet_lite0.tflite

- Press **T** to toggle face tracking.
- Press **O** to toggle object detection.
- Press **Z** to toggle automatic zoom while face tracking.
- Press **V** to show or hide detection boxes and status.
- Press **A** to switch the video preview between camera indexes 0 and 1; it
  also switches the VISCA camera address.
- Press **Q** in the video window or **Esc** to exit.

Face tracking and object detection are mutually exclusive. Object detection
draws labeled boxes in the preview and does not move the camera.

Automatic zoom is off by default. When tracking is on, numpad manual camera
commands are ignored to prevent them from fighting the tracker.

Tracking uses the camera's maximum VISCA pan, tilt, and zoom speed settings.
If the motion is still too fast or too slow for your setup, adjust
`TRACKING_PAN_SPEED`, `TRACKING_TILT_SPEED`, and `TRACKING_ZOOM_SPEED` near the
top of the script (the BRC-300 limits are `0x18`, `0x14`, and `0x07`).
