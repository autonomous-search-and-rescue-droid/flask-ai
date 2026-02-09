import requests
from pynput import keyboard
import threading

# ==========================================
# CONFIGURATION
# ==========================================
PI_IP = input("Enter the ip : ")  # <--- REPLACE THIS with your Pi's IP
PORT = "5000"
BASE_URL = f"http://{PI_IP}:{PORT}"

# ==========================================
# CONTROL LOGIC
# ==========================================
# We use a set to keep track of keys so we don't spam the network
pressed_keys = set()

def send_request(endpoint):
    """Sends the command to the Pi in a separate thread to prevent lag."""
    def _req():
        try:
            requests.get(f"{BASE_URL}/{endpoint}", timeout=0.5)
            print(f"Sent: {endpoint}")
        except requests.exceptions.RequestException as e:
            print(f"Error connecting to Pi: {e}")
    
    # Run in thread so keyboard doesn't freeze waiting for Pi response
    threading.Thread(target=_req, daemon=True).start()

def on_press(key):
    try:
        char = key.char
        # Only send command if key wasn't already pressed
        if char in pressed_keys:
            return
        
        if char == 'w':
            send_request("up_side")
            pressed_keys.add('w')
        elif char == 's':
            send_request("down_side")
            pressed_keys.add('s')
        elif char == 'a':
            send_request("left_side")
            pressed_keys.add('a')
        elif char == 'd':
            send_request("right_side")
            pressed_keys.add('d')
            
    except AttributeError:
        pass # Special keys (ctrl, alt, etc)

def on_release(key):
    try:
        char = key.char
        if char in ['w', 's', 'a', 'd']:
            # Remove from set
            if char in pressed_keys:
                pressed_keys.remove(char)
            
            # If no other movement keys are held down, send STOP
            if not any(k in pressed_keys for k in ['w', 's', 'a', 'd']):
                send_request("stop")
                print("Sent: stop")
                
    except AttributeError:
        pass
    
    # Press ESC to quit the script
    if key == keyboard.Key.esc:
        print("Exiting controller...")
        return False

# ==========================================
# MAIN LOOP
# ==========================================
print(f"Connecting to Robot at {BASE_URL}")
print("Controls: W (Fwd), S (Back), A (Left), D (Right)")
print("Press ESC to quit.")

# Collect events until released
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()