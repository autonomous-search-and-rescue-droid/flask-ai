import subprocess
import paramiko
from flask import Flask, jsonify, request
from flask_cors import CORS

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

if __name__ == '__main__':
    app.run(debug=True, port=5000)
