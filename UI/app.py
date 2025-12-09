import streamlit as st
import requests
import pandas as pd

API_URL = "http://127.0.0.1:5000"

st.set_page_config(page_title="ASAR Admin Panel", layout="wide")
st.title("ASAR Admin Panel")

# --- Session State Initialization ---
if 'page' not in st.session_state:
    st.session_state.page = "login"
if 'wifi_data' not in st.session_state:
    st.session_state.wifi_data = None
if 'network_data' not in st.session_state:
    st.session_state.network_data = None
if 'ssh_creds' not in st.session_state:
    st.session_state.ssh_creds = {}

def show_login_page():
    # --- WiFi Status Section ---
    st.header("WiFi Status")

    col_wifi_btn, col_wifi_status = st.columns([1, 4])
    with col_wifi_btn:
        if st.button("Refresh WiFi Status"):
            try:
                response = requests.get(f"{API_URL}/wifi-status")
                if response.status_code == 200:
                    st.session_state.wifi_data = response.json()
                else:
                    st.error("Failed to fetch WiFi status.")
            except Exception as e:
                st.error(f"Error: {e}")

    # Display WiFi Data from Session State
    if st.session_state.wifi_data:
        data = st.session_state.wifi_data
        if data:
            col1, col2, col3 = st.columns(3)
            col1.metric("SSID", data.get("SSID", "N/A"))
            col2.metric("Signal", data.get("Signal", "N/A"))
            col3.metric("State", data.get("State", "N/A"))
            st.write(f"**Receive Rate:** {data.get('Receive_Rate', 'N/A')} | **Transmit Rate:** {data.get('Transmit_Rate', 'N/A')}")
        else:
            st.warning("No WiFi details found.")

    st.divider()

    # --- Network Devices Section ---
    st.header("Connected Network Devices")
    if st.button("Scan Network"):
        with st.spinner("Scanning network..."):
            try:
                response = requests.get(f"{API_URL}/scan-network")
                if response.status_code == 200:
                    st.session_state.network_data = response.json()
                else:
                    st.error("Failed to scan network.")
            except Exception as e:
                st.error(f"Error: {e}")

    # Display Network Data from Session State
    if st.session_state.network_data:
        devices = st.session_state.network_data
        if devices:
            df = pd.DataFrame(devices)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No devices found from ARP scan.")

    st.divider()

    # --- SSH Connection Section ---
    st.header("Connect to Device")

    col_conn1, col_conn2 = st.columns(2)

    with col_conn1:
        target_ip = st.text_input("IP Address", value="172.19.189.243")
        username = st.text_input("Username", value="an_alan_musical")

    with col_conn2:
        password = st.text_input("Password", type="password")
        connect_btn = st.button("Connect via SSH", type="primary")

    if connect_btn:
        if not target_ip or not username or not password:
            st.warning("Please fill in all credentials.")
        else:
            with st.spinner(f"Connecting to {target_ip}..."):
                try:
                    payload = {
                        "ip": target_ip,
                        "username": username,
                        "password": password
                    }
                    response = requests.post(f"{API_URL}/connect", json=payload)
                    result = response.json()
                    
                    if response.status_code == 200 and result.get("status") == "success":
                        st.session_state.ssh_creds = payload
                        st.session_state.page = "dashboard"
                        st.success(result.get("message"))
                        st.snow()
                        st.rerun()
                    else:
                        st.error(f"Connection Failed: {result.get('message')}")
                        
                except Exception as e:
                    st.error(f"Error connecting: {e}")

if st.session_state.page == "login":
    show_login_page()
elif st.session_state.page == "dashboard":
    # Import dashboard here to avoid circular imports if split files
    from dashboard import show_dashboard
    show_dashboard(API_URL)
