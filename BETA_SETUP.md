# 🛡️ Trepan Beta Setup Guide

Welcome to the Trepan Beta! Follow these steps to get your structural code auditor running.

## 1. Prerequisites

- **Python 3.10+**: Download and install from [python.org](https://www.python.org/downloads/).
- **Ollama**: Download and install from [ollama.com](https://ollama.com/).

## 2. Installation

1. Open your terminal (or CMD/PowerShell on Windows).
2. Navigate to the `Trepan` server directory.
3. Install the required Python libraries:
   ```bash
   pip install -r requirements.txt
   ```

## 3. Launching the Server

Run the universal wrapper script. This script will automatically check your Ollama installation, pull the required AI model (`llama3.1:8b`), and start the backend:

```bash
python start_server.py
```

The server will be running on `http://localhost:8001`.

## 4. Connecting the Extension

- Open VS Code.
- In the Trepan extension settings, ensure the **Server URL** is set to `http://localhost:8001`.
- Your code will now be audited on every save.

---
*If you encounter any issues, please check that Ollama is running and accessible at http://localhost:11434.*
