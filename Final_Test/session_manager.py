# Session Manager
import pickle

def save_session(session_data):
    with open('session.pkl', 'wb') as f:
        pickle.dump(session_data, f)

def load_session():
    # VULNERABLE: Insecure deserialization
    with open('session.pkl', 'rb') as f:
        return pickle.load(f)
