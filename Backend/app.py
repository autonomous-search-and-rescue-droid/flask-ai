import subprocess
import paramiko
from flask import Flask, jsonify, request
from flask_cors import CORS
import cv2
import numpy as np
import tensorflow as tf
import os
import requests
from threading import Lock
import socket
from urllib.parse import urlparse

# --- Load Model ---
MODEL_PATH = "models/mobilenet_ssd_v2_coco_quant_postprocess.tflite"
LABELS_PATH = "models/coco_labels.txt"

interpreter = None
labels = []
lock = Lock()

def load_model():
    global interpreter, labels
    try:
        if not os.path.exists(MODEL_PATH):
            print(f"Model not found at {MODEL_PATH}")
            return False
            
        interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
        interpreter.allocate_tensors()
        
        with open(LABELS_PATH, 'r') as f:
            labels = [line.strip() for line in f.readlines()]
            
        print("Model loaded successfully")
        return True
    except Exception as e:
        print(f"Error loading model: {e}")
        return False

# Load model on startup
load_model()

def detect_objects(frame, sock=None, target_address=None):
    global interpreter
    if not interpreter:
        return frame
        
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    height = input_details[0]['shape'][1]
    width = input_details[0]['shape'][2]

    # Preprocess
    # Match user's logic: Resize and Normalize
    frame_resized = cv2.resize(frame, (width, height))
    
    # Expand dims (1, H, W, C)
    input_data = np.expand_dims(frame_resized, axis=0)
    
    # Check if model expects float or int
    # User's logic: if float, divide by 255.0 (range 0-1)
    # Note: cv2 reads in BGR, TFLite models often expect RGB.
    # The user's code does: cv2_im = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    # We should add that.
    
    # Logic adaptation:
    input_data = cv2.cvtColor(input_data[0], cv2.COLOR_BGR2RGB)
    input_data = np.expand_dims(input_data, axis=0)

    if input_details[0]['dtype'] == np.uint8:
        input_data = input_data.astype(np.uint8)
    else:
        # User supplied logic: (input_data / 255.0)
        input_data = (input_data / 255.0).astype(np.float32)
    
    with lock:
        interpreter.set_tensor(input_details[0]['index'], input_data)
        interpreter.invoke()
        
        boxes = interpreter.get_tensor(output_details[0]['index'])[0]
        classes = interpreter.get_tensor(output_details[1]['index'])[0]
        scores = interpreter.get_tensor(output_details[2]['index'])[0]
        # num_detections = int(interpreter.get_tensor(output_details[3]['index'])[0]) 
        # (Standard TFLite obj detection has 4 outputs: boxes, classes, scores, num)

    # Draw boxes
    person_count = 0
    im_height, im_width, _ = frame.shape
    
    for i in range(len(scores)):
        score = scores[i]
        # User defined threshold in snippet was 0.3
        if score > 0.3:
            class_id = int(classes[i])
            # User checks if class_id == 0 for person. 
            # We can also check labels if available, but let's prioritize index 0 as 'person'
            
            is_person = (class_id == 0)
            # Or fallback to label check if 0 is not person in this specific model (unlikely for COCO)
            if not is_person and len(labels) > class_id:
                if 'person' in labels[class_id].lower():
                    is_person = True
            
            if is_person:
                person_count += 1
                ymin, xmin, ymax, xmax = boxes[i]
                
                (left, right, top, bottom) = (int(xmin * im_width), int(xmax * im_width),
                                              int(ymin * im_height), int(ymax * im_height))
                                              
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                text = f"person: {score:.2f}"
                cv2.putText(frame, text, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                
                # --- Direction Logic ---
                box_center_x = (left + right) / 2
                image_center_x = im_width / 2
                
                # Define deadzone threshold (e.g., 15% of width from center)
                threshold = im_width * 0.15
                
                if box_center_x > image_center_x + threshold:
                    direction = "right"
                    print(f"Action: {direction}")
                elif box_center_x < image_center_x - threshold:
                    direction = "left"
                    print(f"Action: {direction}")
                else:
                    direction = "forward"
                    print(f"Action: {direction}")
                
                if sock and target_address:
                    try:
                        sock.sendto(direction.encode(), target_address)
                    except Exception as e:
                        print(f"Socket send error: {e}")
                # -----------------------
    
    # Add count text
    detection_text = f"Persons: {person_count}"
    # Calculate text size for positioning
    (text_w, text_h), _ = cv2.getTextSize(detection_text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)
    cv2.putText(frame, detection_text, (im_width - text_w - 10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                            
    return frame

app = Flask(__name__)
CORS(app)

@app.route('/')
def hello():
    return jsonify({"message": "Hello from Flask Backend!"})

@app.route('/wifi-status')
def wifi_status():
    try:
        # Run netsh command to get wifi details
        result = subprocess.check_output(['netsh', 'wlan', 'show', 'interfaces']).decode('utf-8')
        
        info = {}
        for line in result.split('\n'):
            line = line.strip()
            if 'SSID' in line and 'BSSID' not in line:
                info['SSID'] = line.split(':')[1].strip()
            elif 'Signal' in line:
                info['Signal'] = line.split(':')[1].strip()
            elif 'Receive rate' in line:
                info['Receive_Rate'] = line.split(':')[1].strip()
            elif 'Transmit rate' in line:
                info['Transmit_Rate'] = line.split(':')[1].strip()
            elif 'State' in line:
                info['State'] = line.split(':')[1].strip()
                
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/scan-network')
def scan_network():
    try:
        # Run arp -a to see connected devices
        result = subprocess.check_output(['arp', '-a']).decode('utf-8')
        devices = []
        for line in result.split('\n'):
            parts = line.split()
            if len(parts) >= 3:
                # Basic check to see if it looks like an IP and MAC
                if parts[0].replace('.', '').isdigit() and '-' in parts[1]: 
                    devices.append({
                        "IP": parts[0],
                        "MAC": parts[1],
                        "Type": parts[2]
                    })
        return jsonify(devices)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/connect', methods=['POST'])
def connect_ssh():
    data = request.json
    ip = data.get('ip')
    username = data.get('username')
    password = data.get('password')
    
    if not ip or not username or not password:
        return jsonify({"message": "Missing credentials"}), 400
        
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=username, password=password, timeout=5)
        
        # Test command
        stdin, stdout, stderr = ssh.exec_command('whoami')
        user = stdout.read().decode().strip()
        ssh.close()
        
        return jsonify({"message": f"Successfully connected as {user}", "status": "success"})
    except Exception as e:
        return jsonify({"message": str(e), "status": "error"}), 401

@app.route('/list-files', methods=['POST'])
def list_files():
    data = request.json
    ip = data.get('ip')
    username = data.get('username')
    password = data.get('password')
    path = data.get('path', '.') # Default to current directory
    
    if not ip or not username or not password:
        return jsonify({"message": "Missing credentials"}), 400
        
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=username, password=password, timeout=5)
        
        # List files with type indicator (-F)
        # -F appends / to dir, * to executable, etc.
        cmd = f"ls -F {path}"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        
        files_raw = stdout.read().decode().splitlines()
        ssh.close()
        
        files = []
        for f in files_raw:
            f = f.strip()
            if not f: continue
            
            is_dir = f.endswith('/')
            name = f.rstrip('/*@|') # Clean up indicators
            
            files.append({
                "name": name,
                "is_dir": is_dir,
                "path": f"{path}/{name}".replace('//', '/') if path != '.' else name
            })
            
        return jsonify({"files": files})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/run-file', methods=['POST'])
def run_file():
    data = request.json
    ip = data.get('ip')
    username = data.get('username')
    password = data.get('password')
    path = data.get('path')
    
    if not ip or not username or not password or not path:
        return jsonify({"message": "Missing credentials or path"}), 400
        
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=username, password=password, timeout=5)
        
        # Execute python file
        # We start with basic python execution.
        cmd = f"python {path}"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        
        # Read output
        output = stdout.read().decode()
        error = stderr.read().decode()
        
        ssh.close()
        
        return jsonify({
            "output": output,
            "error": error,
            "status": "success" if not error else "warning"
        })
    except Exception as e:
        return jsonify({"error": str(e), "status": "failed"}), 500

@app.route('/view-file', methods=['POST'])
def view_file():
    """Read and return the content of a file"""
    data = request.json
    ip = data.get('ip')
    username = data.get('username')
    password = data.get('password')
    path = data.get('path')
    
    if not ip or not username or not password or not path:
        return jsonify({"message": "Missing credentials or path"}), 400
        
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=username, password=password, timeout=5)
        
        # Read file content using cat
        cmd = f"cat '{path}'"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        
        content = stdout.read().decode()
        error = stderr.read().decode()
        
        ssh.close()
        
        if error:
            return jsonify({"error": error}), 400
        
        return jsonify({
            "content": content,
            "status": "success"
        })
    except Exception as e:
        return jsonify({"error": str(e), "status": "failed"}), 500

@app.route('/save-file', methods=['POST'])
def save_file():
    """Save content to a file"""
    data = request.json
    ip = data.get('ip')
    username = data.get('username')
    password = data.get('password')
    path = data.get('path')
    content = data.get('content', '')
    
    if not ip or not username or not password or not path:
        return jsonify({"message": "Missing credentials or path"}), 400
        
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=username, password=password, timeout=5)
        
        # Use SFTP to write file
        sftp = ssh.open_sftp()
        with sftp.file(path, 'w') as f:
            f.write(content)
        sftp.close()
        
        ssh.close()
        
        return jsonify({
            "message": f"File saved successfully: {path}",
            "status": "success"
        })
    except Exception as e:
        return jsonify({"error": str(e), "status": "failed"}), 500

@app.route('/create-file', methods=['POST'])
def create_file():
    """Create a new file in the specified directory"""
    data = request.json
    ip = data.get('ip')
    username = data.get('username')
    password = data.get('password')
    directory = data.get('directory', '.')
    filename = data.get('filename')
    content = data.get('content', '')
    
    if not ip or not username or not password or not filename:
        return jsonify({"message": "Missing credentials or filename"}), 400
        
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=username, password=password, timeout=5)
        
        # Construct full path
        full_path = f"{directory}/{filename}".replace('//', '/')
        
        # Check if file already exists
        cmd = f"test -f '{full_path}' && echo 'exists'"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        if stdout.read().decode().strip() == 'exists':
            ssh.close()
            return jsonify({"error": "File already exists", "status": "failed"}), 400
        
        # Use SFTP to create file
        sftp = ssh.open_sftp()
        with sftp.file(full_path, 'w') as f:
            f.write(content)
        sftp.close()
        
        ssh.close()
        
        return jsonify({
            "message": f"File created successfully: {full_path}",
            "path": full_path,
            "status": "success"
        })
    except Exception as e:
        return jsonify({"error": str(e), "status": "failed"}), 500

@app.route('/process-video')
def process_video():
    url = request.args.get('url')
    if not url:
        return "Missing URL", 400

    # Socket setup logic
    target_ip = request.args.get('ip')
    target_port = request.args.get('port')
    sock = None
    target_address = None

    if not target_ip:
        # Try to extract IP from URL
        try:
            parsed_url = urlparse(url)
            if parsed_url.hostname:
                target_ip = parsed_url.hostname
                print(f"Extracted IP from URL: {target_ip}")
        except Exception as e:
            print(f"Could not extract IP from URL: {e}")

    if target_ip and target_port:
        try:
            port = int(target_port)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            target_address = (target_ip, port)
            print(f"UDP Socket initialized for {target_address}")
        except ValueError:
            print("Invalid port number")
        
    def generate_frames():
        # captured_url needs to be a local variable that can be updated
        target_url = url
        
        print(f"Inspect/Open video stream from: {target_url}")
        
        # Diagnostic and Auto-discovery
        try:
            r = requests.get(target_url, stream=True, timeout=5)
            content_type = r.headers.get('Content-Type', '')
            print(f"Target URL Content-Type: {content_type}")
            
            if 'text/html' in content_type:
                print("URL seems to be a webpage. Attempting to find video stream URL in HTML...")
                html_content = r.text
                # Simple regex to find img src
                import re
                # Look for img tag with src
                matches = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html_content)
                if matches:
                    print(f"Found image sources: {matches}")
                    # Usually the stream is the main image in simple flask apps
                    src = matches[0]
                    
                    if not src.startswith('http'):
                        # Handle relative URL
                        from urllib.parse import urljoin
                        target_url = urljoin(target_url, src)
                    else:
                        target_url = src
                    
                    print(f"Resolved new video URL: {target_url}")
                else:
                    print("No img tags found in HTML. Trying original URL...")
            r.close()
        except Exception as e:
            print(f"Error inspecting/parsing URL: {e}")

        # Open video stream
        # Force FFMPEG backend which is often more robust for network streams
        cap = cv2.VideoCapture(target_url, cv2.CAP_FFMPEG)
        
        if not cap.isOpened():
            print(f"Failed to open video capture for URL: {url}")
            return

        print("Video capture opened successfully. Starting frame loop...")
        frame_count = 0
        while True:
            success, frame = cap.read()
            if not success:
                print("Failed to read frame or stream ended.")
                break
            
            # optional: limit log rate
            if frame_count % 30 == 0:
                print(f"Processing frame {frame_count}")
            frame_count += 1
                
            # Run detection
            try:
                frame = detect_objects(frame, sock, target_address)
            except Exception as e:
                print(f"Error during detection: {e}")
            
            # Encode
            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                print("Failed to encode frame.")
                continue
                
            frame_bytes = buffer.tobytes()
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                   
        cap.release()
        if sock:
            sock.close()
        print("Video capture released.")

    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

from flask import Response

if __name__ == '__main__':
    app.run(debug=True, port=5000)
