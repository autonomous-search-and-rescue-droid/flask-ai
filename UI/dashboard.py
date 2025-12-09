import streamlit as st
import requests

def show_dashboard(api_url):
    st.title("Device Dashboard")
    
    if st.button("Logout"):
        st.session_state.page = "login"
        st.session_state.ssh_creds = {}
        st.rerun()
    
    # --- File Browser ---
    st.header("File Browser")
    
    if "current_path" not in st.session_state:
        st.session_state.current_path = "."
        
    creds = st.session_state.ssh_creds
    
    # Navigation Bar
    col_nav1, col_nav2 = st.columns([4, 1])
    with col_nav1:
        new_path = st.text_input("Current Path", value=st.session_state.current_path)
    with col_nav2:
        if st.button("Go"):
            st.session_state.current_path = new_path
            st.rerun()

    # List Files
    try:
        payload = creds.copy()
        payload["path"] = st.session_state.current_path
        
        response = requests.post(f"{api_url}/list-files", json=payload)
        
        if response.status_code == 200:
            files = response.json().get("files", [])
            
            # Display files
            for file in files:
                col_icon, col_name, col_action = st.columns([0.5, 3, 1])
                
                with col_icon:
                    st.write("📁" if file['is_dir'] else "📄")
                
                with col_name:
                    if file['is_dir']:
                         if st.button(f"{file['name']}/", key=f"dir_{file['name']}"):
                             st.session_state.current_path = file['path']
                             st.rerun()
                    else:
                        st.write(file['name'])
                        
                with col_action:
                    if not file['is_dir'] and file['name'].endswith('.py'):
                        if st.button("▶ Run", key=f"run_{file['name']}", type="primary", help="Run Python Script"):
                            run_python_script(api_url, creds, file['path'])
                            
        else:
            st.error("Failed to list files. Check path or connection.")
            
    except Exception as e:
         st.error(f"Error fetching files: {e}")

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
