PC Manager

Рабочая Windows-утилита на Python 3.12+ и PySide6 для мониторинга состояния системы.


Установка и запуск

py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
`


Приложение сохраняет `history.db` и `logs/app.log` рядом с исходниками. NVIDIA-метрики доступны при установленном драйвере NVIDIA и `pynvml`; WMI-поля Windows показываются как `Unavailable`, если провайдер или права недоступны. Доступ к некоторым процессам и датчикам требует запуска от имени администратора.

