# Admin Panel Project

This project consists of a Flask backend and a Streamlit frontend.

## Prerequisites

- Python 3.x

## Setup & Running

It is recommended to use two separate terminals for running the backend and the frontend.

### 1. Backend Setup

Navigate to the `Backend` directory:

```bash
cd Backend
pip install -r requirements.txt
python app.py
```

The backend will start at `http://127.0.0.1:5000/`.

### 2. Frontend Setup

Navigate to the `UI` directory:

```bash
cd UI
pip install -r requirements.txt
streamlit run app.py
```

The frontend will open in your default browser (usually at `http://localhost:8501`).
