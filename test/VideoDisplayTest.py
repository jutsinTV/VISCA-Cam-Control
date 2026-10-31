import cv2

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Error opening video stream or file")
    exit()

print("Video stream opened successfully. Press 'q' to quit.")

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        cv2.imshow('Video', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
except Exception as e:
    print(f"Error occurred: {e}")
finally:
    cap.release()
    cv2.destroyAllWindows()