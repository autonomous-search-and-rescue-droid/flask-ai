import cv2
import numpy as np
from PIL import Image
import time
from threading import Thread
import tensorflow as tf
import requests

# ====================== CONFIGURATION ======================
# Initial speed (0.0 to 1.0) - kept for reference logic
speed = 0.7 

# Detection settings
# Stream setup
IP_ADDRESS = input("Enter IP Address of Raspberry Pi : ")
BASE_URL = f"http://{IP_ADDRESS}:5000"
STREAM_URL = f"http://{IP_ADDRESS}:5000/video"
print(f"Connecting to video stream at: {STREAM_URL}")

# Initialize persistent session
session = requests.Session()

class VideoStream:
    """
    Dedicated thread for grabbing frames from the video stream.
    This ensures the main loop always gets the *latest* frame
    instead of processing buffered frames.
    """
    def __init__(self, src=0):
        self.stream = cv2.VideoCapture(src)
        (self.grabbed, self.frame) = self.stream.read()
        self.stopped = False

    def start(self):
        Thread(target=self.update, args=(), daemon=True).start()
        return self

    def update(self):
        while not self.stopped:
            if not self.stream.isOpened():
                continue
            (self.grabbed, self.frame) = self.stream.read()

    def read(self):
        return self.frame

    def stop(self):
        self.stopped = True
        self.stream.release()

# Try to capture from URL using threaded stream
# cap = cv2.VideoCapture(STREAM_URL)  # OLD: Blocking
cap = VideoStream(STREAM_URL).start()

threshold = 0.5  # Increased slightly for better accuracy
top_k = 5
model_dir = './models'
model_file = 'mobilenet_ssd_v2_coco_quant_postprocess.tflite'
label_file = 'coco_labels.txt'

# Robot control variables
tolerance = 0.1
x_deviation = 0
y_max = 0
bbox_area = 0
frame_area = 0
area_threshold = 0.85  # Stop when person is this close (85% of screen)
no_person_start_time = None
PERSON_DETECTION_TIMEOUT = 10  # Seconds to wait before stopping/searching

# ====================== MOVEMENT ACTION ======================
last_action = None

def send_command(endpoint):
    """Sends command to Pi in a separate thread"""
    def _req():
        try:
            # Construct command URL (e.g. http://192.168.95.243:5000/up_side)
            url = f"{BASE_URL}{endpoint}"
            # Use session for connection pooling and increased timeout
            session.get(url, timeout=2.0)
            # print(f"Sent: {endpoint}")
        except Exception as e:
            print(f"Error sending command {endpoint}: {e}")
    
    Thread(target=_req, daemon=True).start()

def print_action(action, details=""):
    global last_action
    
    # Map action to endpoint
    # FORWARD -> up_side (w)
    # LEFT    -> left_side (a)
    # RIGHT   -> right_side (d)
    # STOP    -> stop
    
    endpoint = None
    if action == "FORWARD":
        endpoint = "/up_side"
    elif action == "LEFT":
        endpoint = "/left_side"
    elif action == "RIGHT":
        endpoint = "/right_side"
    elif action == "STOP":
        endpoint = "/stop"
        
    # Only send if action changed
    if action != last_action:
        if endpoint:
            send_command(endpoint)
            print(f"ACTION CHANGED: {action} ({endpoint}) | {details}")
        else:
            print(f"ACTION: {action} | {details}")
            
        last_action = action
    else:
        # Optional: Print periodically or just pass
        # print(f"Keeping: {action} | {details}")
        pass

# ====================== TFLITE FUNCTIONS ======================
def load_model(model_dir, model_file, label_file):
    model_path = f"{model_dir}/{model_file}"
    label_path = f"{model_dir}/{label_file}"
    
    try:
        # Use simple file reading for labels
        with open(label_path, 'r') as f:
            labels = {i: line.strip() for i, line in enumerate(f.readlines())}
            
        # Initialize Interpreter
        interpreter = tf.lite.Interpreter(model_path=model_path)
        interpreter.allocate_tensors()
        
        return interpreter, labels
    except Exception as e:
        print(f"Error loading model/labels: {e}")
        return None, None

def set_input(interpreter, image):
    input_details = interpreter.get_input_details()[0]
    height = input_details['shape'][1]
    width = input_details['shape'][2]
    
    resized_image = image.resize((width, height), Image.Resampling.LANCZOS)
    input_data = np.expand_dims(np.array(resized_image), axis=0)
    
    # Check if model expects INT8 or FLOAT32
    if input_details['dtype'] == np.uint8:
        input_data = input_data.astype(np.uint8)
    else:
        # Normalize to [0,1] if float model
        input_data = (input_data / 255.0).astype(np.float32)
    
    interpreter.set_tensor(input_details['index'], input_data)

def get_output(interpreter, score_threshold, top_k):
    output_details = interpreter.get_output_details()
    
    boxes = interpreter.get_tensor(output_details[0]['index'])[0]
    classes = interpreter.get_tensor(output_details[1]['index'])[0]
    scores = interpreter.get_tensor(output_details[2]['index'])[0]
    # Check if num_detections is available (index 3), otherwise ignore
    # num_detections = int(interpreter.get_tensor(output_details[3]['index'])[0])
    
    detections = []
    for i in range(len(scores)):
        if scores[i] > score_threshold:
            detections.append({
                'bbox': boxes[i],
                'class': int(classes[i]),
                'score': scores[i]
            })
            if len(detections) >= top_k:
                break
    return detections

def draw_boxes(frame, detections, labels):
    height, width = frame.shape[:2]
    person_count = 0
    
    for detection in detections:
        class_id = detection['class']
        # Class ID 0 is usually "person" in COCO models
        # Also check label text just in case
        label_text = labels.get(class_id, "Unknown").lower()
        if class_id != 0 and "person" not in label_text: 
            continue
        
        person_count += 1
        ymin, xmin, ymax, xmax = detection['bbox']
        xmin = int(xmin * width)
        xmax = int(xmax * width)
        ymin = int(ymin * height)
        ymax = int(ymax * height)
        
        cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), (0, 255, 0), 2)
        text = f"Person: {detection['score']:.2f}"
        cv2.putText(frame, text, (xmin, ymin - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    
    detection_text = f"Persons: {person_count}"
    cv2.putText(frame, detection_text, (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
    
    return person_count

# ====================== LOGIC & TRACKING ======================
def track_object(detections, labels, frame_height, frame_width):
    global x_deviation, y_max, tolerance, bbox_area, frame_area
    
    frame_area = frame_height * frame_width
    
    if len(detections) == 0:
        print_action("STOP", "No detections")
        return
    
    # Find the largest person
    target_person = None
    max_area = 0

    for detection in detections:
        class_id = detection['class']
        label_text = labels.get(class_id, "Unknown").lower()
        
        if class_id == 0 or "person" in label_text: # Person
            ymin, xmin, ymax, xmax = detection['bbox']
            
            # Calculate area to track the closest person
            w = (xmax - xmin) * frame_width
            h = (ymax - ymin) * frame_height
            area = w * h
            
            if area > max_area:
                max_area = area
                target_person = detection

    if target_person is None:
        print_action("STOP", "No person found")
        return
    
    # Process the target person
    ymin, xmin, ymax, xmax = target_person['bbox']
    
    # Convert to pixel values
    xmin_px = int(xmin * frame_width)
    xmax_px = int(xmax * frame_width)
    ymin_px = int(ymin * frame_height)
    ymax_px = int(ymax * frame_height)
    
    # Calculate bounding box area
    bbox_width = xmax_px - xmin_px
    bbox_height = ymax_px - ymin_px
    bbox_area = bbox_width * bbox_height
    
    # Calculate center point deviation (-0.5 to 0.5)
    # xmin, xmax are normalized [0,1]
    x_center = xmin + ((xmax - xmin) / 2)
    x_deviation = round(0.5 - x_center, 3)
    y_max = round(ymax, 3)
    
    # Run logic (directly, no separate thread needed for print-only if fast enough)
    # Using thread to mimic original structure if preferred, but simple call is fine here.
    move_robot()

def move_robot():
    global x_deviation, bbox_area, frame_area, area_threshold, tolerance
    
    if frame_area == 0: return

    area_ratio = bbox_area / frame_area
    
    # 1. Stop if too close
    if area_ratio >= area_threshold:
        print_action("STOP", f"Target Reached (Too Close, Area: {area_ratio:.2f})")
        return
    
    # 2. Turn if off-center
    if abs(x_deviation) > tolerance:
        if x_deviation > 0: # Target is to the LEFT (x_center < 0.5)
            # x_deviation = 0.5 - x_center. If x_center is 0.2, dev is 0.3 (>0).
            print_action("LEFT", f"Deviation: {x_deviation}")
        else: # Target is to the RIGHT
            print_action("RIGHT", f"Deviation: {x_deviation}")
            
    # 3. Move forward if centered
    else:
        print_action("FORWARD", f"Centered (Dev: {x_deviation}, Area: {area_ratio:.2f})")

def search_mode():
    """
    Simple behavior when no person is found:
    Print search action.
    """
    global no_person_start_time
    
    # Check timeout
    if no_person_start_time and (time.time() - no_person_start_time > PERSON_DETECTION_TIMEOUT):
        print_action("STOP", "Timeout: No person found.")
        return

    print_action("SEARCH_RIGHT", "Scanning area...")
    time.sleep(0.5)

# ====================== MAIN LOOP ======================
def main():
    global no_person_start_time, cap
    
    interpreter, labels = load_model(model_dir, model_file, label_file)
    if not interpreter:
        print("Failed to load model. Exiting.")
        return

    print("Model Loaded. Starting Video Capture...")
    
    # cap is now a VideoStream object, not cv2.VideoCapture
    # Verification handled inside class, or we can check first frame
    time.sleep(2.0) # Warm up

    while True:
        start_time = time.time()
        
        # Get latest frame (non-blocking)
        frame = cap.read()
        
        if frame is None:
            print("Failed to read frame from stream. Reconnecting...")
            time.sleep(1)
            try:
                cap.stop()
                cap = VideoStream(STREAM_URL).start()
            except:
                pass
            continue
        
        frame_height, frame_width = frame.shape[:2]
        
        # Prepare Input
        # cv2 reads in BGR, TFLite needs RGB
        cv2_im = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        try:
            pil_im = Image.fromarray(cv2_im)
        except Exception:
            continue
        
        set_input(interpreter, pil_im)
        interpreter.invoke()
        detections = get_output(interpreter, score_threshold=threshold, top_k=top_k)
        
        # Draw and Count
        person_count = draw_boxes(frame, detections, labels)
        
        # Logic
        if person_count > 0:
            no_person_start_time = None # Reset timer
            track_object(detections, labels, frame_height, frame_width)
        else:
            if no_person_start_time is None:
                no_person_start_time = time.time()
            
            elapsed = time.time() - no_person_start_time
            
            if elapsed < 1.0:
                print_action("STOP", f"Lost detection... waiting ({elapsed:.1f}s)")
            else:
                # Continuous search logic: Rotate right until person found
                print_action("RIGHT", "Searching - No person detected")
        
        # FPS display
        fps = round(1.0 / (time.time() - start_time), 1)
        cv2.putText(frame, f"FPS: {fps}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        
        cv2.imshow("Autonomous View", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopping...")
