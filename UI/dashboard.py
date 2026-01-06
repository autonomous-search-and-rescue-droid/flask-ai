import streamlit as st
import requests

def show_dashboard(api_url):
    st.title("Device Dashboard")
    
    if st.button("Logout"):
        st.session_state.page = "login"
        st.session_state.ssh_creds = {}
        st.session_state.pop('editing_file', None)
        st.session_state.pop('viewing_file', None)
        st.session_state.pop('creating_file', None)
        st.rerun()
    
    creds = st.session_state.ssh_creds
    
    # --- Camera Section ---
    st.header("Camera Feed")
    show_camera = st.toggle("Show Camera Output", value=False)
    
    if show_camera:
        enable_detection = st.checkbox("Enable Person Detection (Beta)")
        
        ip = creds.get('ip')
        if ip:
            # Base stream URL (port 5000 as requested)
            base_url = f"http://{ip}:5000"
            
            if enable_detection:
                # Point to our backend for processing
                # We need to pass the FULL url to the backend
                # Assuming backend is reachable at api_url (localhost:5000 from dashboard view)
                stream_url = f"{api_url}/process-video?url={base_url}"
            else:
                stream_url = base_url
            
            # Use HTML for better centering/styling of the stream
            # Using iframe is more robust if the endpoint returns a full HTML page or a stream
            st.markdown(
                f"""
                <div style="text-align: center; margin-bottom: 20px;">
                    <iframe src="{stream_url}" style="width: 100%; max-width: 800px; height: 600px; border-radius: 8px; border: 1px solid #444;" frameborder="0" allowfullscreen></iframe>
                    <p style="color: #888; font-size: 0.8em; margin-top: 5px;">Source: <a href="{stream_url}" target="_blank">{stream_url}</a></p>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.warning("No connected device found.")
            
    st.divider()
    
    # --- File Browser ---
    st.header("File Browser")
    
    if "current_path" not in st.session_state:
        st.session_state.current_path = "."
        
    # creds already defined above
    
    # Navigation Bar
    col_nav1, col_nav2 = st.columns([4, 1])
    with col_nav1:
        new_path = st.text_input("Current Path", value=st.session_state.current_path)
    with col_nav2:
        if st.button("Go"):
            st.session_state.current_path = new_path
            st.rerun()

    # --- Create New File Section ---
    if st.session_state.get('creating_file'):
        show_create_file_dialog(api_url, creds)
        return
    
    # --- View/Edit File Section ---
    if st.session_state.get('viewing_file'):
        show_view_file(api_url, creds)
        return
    
    if st.session_state.get('editing_file'):
        show_edit_file(api_url, creds)
        return

    # --- Add New File Button ---
    col_add, col_spacer = st.columns([1, 4])
    with col_add:
        if st.button("➕ New File", type="secondary", help="Create a new file in current directory"):
            st.session_state.creating_file = True
            st.session_state.create_directory = st.session_state.current_path
            st.rerun()

    st.divider()

    # List Files
    try:
        payload = creds.copy()
        payload["path"] = st.session_state.current_path
        
        response = requests.post(f"{api_url}/list-files", json=payload)
        
        if response.status_code == 200:
            files = response.json().get("files", [])
            
            # Display files
            for file in files:
                if file['is_dir']:
                    # Directory row
                    col_icon, col_name, col_action = st.columns([0.5, 3, 1.5])
                    
                    with col_icon:
                        st.write("📁")
                    
                    with col_name:
                        if st.button(f"{file['name']}/", key=f"dir_{file['name']}"):
                            st.session_state.current_path = file['path']
                            st.rerun()
                    
                    with col_action:
                        if st.button("➕ Add File", key=f"add_{file['name']}", help="Create new file in this folder"):
                            st.session_state.creating_file = True
                            st.session_state.create_directory = file['path']
                            st.rerun()
                else:
                    # File row
                    col_icon, col_name, col_actions = st.columns([0.5, 2, 2.5])
                    
                    with col_icon:
                        st.write("📄")
                    
                    with col_name:
                        st.write(file['name'])
                    
                    with col_actions:
                        btn_cols = st.columns(4)
                        
                        # View button
                        with btn_cols[0]:
                            if st.button("👁", key=f"view_{file['name']}", help="View file"):
                                st.session_state.viewing_file = file['path']
                                st.session_state.viewing_filename = file['name']
                                st.rerun()
                        
                        # Edit button
                        with btn_cols[1]:
                            if st.button("✏️", key=f"edit_{file['name']}", help="Edit file"):
                                st.session_state.editing_file = file['path']
                                st.session_state.editing_filename = file['name']
                                st.rerun()
                        
                        # Run button (only for Python files)
                        with btn_cols[2]:
                            if file['name'].endswith('.py'):
                                if st.button("▶", key=f"run_{file['name']}", type="primary", help="Run Python Script"):
                                    run_python_script(api_url, creds, file['path'])
                        
                        # Delete button placeholder (optional)
                        with btn_cols[3]:
                            pass
                            
        else:
            st.error("Failed to list files. Check path or connection.")
            
    except Exception as e:
         st.error(f"Error fetching files: {e}")


def show_view_file(api_url, creds):
    """Display file content in read-only mode"""
    file_path = st.session_state.viewing_file
    filename = st.session_state.get('viewing_filename', file_path)
    
    st.subheader(f"📄 Viewing: {filename}")
    
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        if st.button("← Back"):
            st.session_state.pop('viewing_file', None)
            st.session_state.pop('viewing_filename', None)
            st.rerun()
    with col2:
        if st.button("✏️ Edit"):
            st.session_state.editing_file = file_path
            st.session_state.editing_filename = filename
            st.session_state.pop('viewing_file', None)
            st.session_state.pop('viewing_filename', None)
            st.rerun()
    
    try:
        payload = creds.copy()
        payload["path"] = file_path
        
        response = requests.post(f"{api_url}/view-file", json=payload)
        result = response.json()
        
        if response.status_code == 200:
            content = result.get("content", "")
            # Determine language for syntax highlighting
            lang = get_language_from_filename(filename)
            st.code(content, language=lang, line_numbers=True)
        else:
            st.error(f"Failed to load file: {result.get('error')}")
            
    except Exception as e:
        st.error(f"Error loading file: {e}")


def show_edit_file(api_url, creds):
    """Display file content in edit mode with save functionality"""
    file_path = st.session_state.editing_file
    filename = st.session_state.get('editing_filename', file_path)
    
    st.subheader(f"✏️ Editing: {filename}")
    
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("← Back"):
            st.session_state.pop('editing_file', None)
            st.session_state.pop('editing_filename', None)
            st.session_state.pop('file_content', None)
            st.rerun()
    
    # Load content if not already loaded
    if 'file_content' not in st.session_state:
        try:
            payload = creds.copy()
            payload["path"] = file_path
            
            response = requests.post(f"{api_url}/view-file", json=payload)
            result = response.json()
            
            if response.status_code == 200:
                st.session_state.file_content = result.get("content", "")
            else:
                st.error(f"Failed to load file: {result.get('error')}")
                return
                
        except Exception as e:
            st.error(f"Error loading file: {e}")
            return
    
    # Text editor
    lang = get_language_from_filename(filename)
    height = max(300, min(600, len(st.session_state.file_content.split('\n')) * 20))
    
    edited_content = st.text_area(
        "File Content",
        value=st.session_state.file_content,
        height=height,
        key="editor",
        help=f"Editing {filename}"
    )
    
    # Save button
    col_save, col_cancel = st.columns([1, 4])
    with col_save:
        if st.button("💾 Save", type="primary"):
            save_file(api_url, creds, file_path, edited_content)


def show_create_file_dialog(api_url, creds):
    """Show dialog for creating a new file"""
    directory = st.session_state.get('create_directory', st.session_state.current_path)
    
    st.subheader(f"➕ Create New File in: {directory}")
    
    if st.button("← Cancel"):
        st.session_state.pop('creating_file', None)
        st.session_state.pop('create_directory', None)
        st.rerun()
    
    filename = st.text_input("Filename", placeholder="e.g., script.py")
    content = st.text_area("Initial Content (optional)", height=200)
    
    if st.button("Create File", type="primary"):
        if not filename:
            st.error("Please enter a filename")
            return
        
        try:
            payload = creds.copy()
            payload["directory"] = directory
            payload["filename"] = filename
            payload["content"] = content
            
            response = requests.post(f"{api_url}/create-file", json=payload)
            result = response.json()
            
            if response.status_code == 200:
                st.success(result.get("message", "File created successfully!"))
                st.session_state.pop('creating_file', None)
                st.session_state.pop('create_directory', None)
                st.rerun()
            else:
                st.error(f"Failed to create file: {result.get('error')}")
                
        except Exception as e:
            st.error(f"Error creating file: {e}")


def save_file(api_url, creds, path, content):
    """Save file content"""
    try:
        payload = creds.copy()
        payload["path"] = path
        payload["content"] = content
        
        response = requests.post(f"{api_url}/save-file", json=payload)
        result = response.json()
        
        if response.status_code == 200:
            st.success(result.get("message", "File saved successfully!"))
            st.session_state.file_content = content
        else:
            st.error(f"Failed to save file: {result.get('error')}")
            
    except Exception as e:
        st.error(f"Error saving file: {e}")


def run_python_script(api_url, creds, path):
    st.toast(f"Running {path}...", icon="🚀")
    try:
        payload = creds.copy()
        payload["path"] = path
        
        response = requests.post(f"{api_url}/run-file", json=payload)
        result = response.json()
        
        if response.status_code == 200:
            st.markdown("### Execution Result")
            if result.get("output"):
                st.code(result.get("output"), language="bash")
            if result.get("error"):
                st.error("Standard Error Output:")
                st.code(result.get("error"), language="bash")
        else:
            st.error(f"Execution failed: {result.get('error')}")
            
    except Exception as e:
        st.error(f"Error running script: {e}")


def get_language_from_filename(filename):
    """Get syntax highlighting language from filename extension"""
    ext_map = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.html': 'html',
        '.css': 'css',
        '.json': 'json',
        '.yaml': 'yaml',
        '.yml': 'yaml',
        '.md': 'markdown',
        '.sh': 'bash',
        '.bash': 'bash',
        '.sql': 'sql',
        '.xml': 'xml',
        '.c': 'c',
        '.cpp': 'cpp',
        '.h': 'c',
        '.java': 'java',
        '.go': 'go',
        '.rs': 'rust',
        '.rb': 'ruby',
        '.php': 'php',
    }
    
    for ext, lang in ext_map.items():
        if filename.lower().endswith(ext):
            return lang
    return None
