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

## 3. Installing the VS Code Extension

Before you can use Trepan in your IDE, you need to install the extension:

1. Go to the [Trepan GitHub Releases](https://github.com/dsadsadsadsadas/Trepan/releases) page.
2. Download the latest `trepan-gatekeeper-x.x.x.vsix` file.
3. Open **VS Code**.
4. Open the **Extensions** view (`Ctrl+Shift+X`).
5. Click the `...` menu (Views and More Actions) in the top-right corner of the Extensions sidebar.
6. Select **Install from VSIX...**.
7. Locate and select the downloaded project `.vsix` file.

## 4. Launching the Server

Run the universal wrapper script. This script will automatically check your Ollama installation, pull the required AI model (`llama3.1:8b`), and start the backend:

```bash
python start_server.py
```

The server will be running on `http://localhost:8001`.

## 5. Connecting the Extension

- In VS Code, open your project.
- In the Trepan extension settings, ensure the **Server URL** is set to `http://localhost:8001`.
- Your code will now be audited on every save.

---
*If you encounter any issues, please check that Ollama is running and accessible at http://localhost:11434.*
