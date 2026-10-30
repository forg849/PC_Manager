PC Manager

A functional Windows utility built with Python 3.12+ and PySide6 for monitoring system status.


Installation and Execution

py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py


The application stores `history.db` and `logs/app.log` in the same directory as the source code. NVIDIA metrics are available provided that an NVIDIA driver and `pynvml` are installed; Windows WMI fields will appear as `Unavailable` if the provider is inaccessible or if the necessary permissions are lacking. Accessing certain processes and sensors requires running the application as an administrator.

