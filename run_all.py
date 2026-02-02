"""
Запуск бота и API вместе.
Для VPS используй systemd (см. deploy/README.md)
"""

import asyncio
import subprocess
import sys


def main():
    # Запускаем API в отдельном процессе
    api_process = subprocess.Popen([
        sys.executable, "-m", "uvicorn", 
        "api.main:app", 
        "--host", "0.0.0.0", 
        "--port", "8000"
    ])
    
    # Запускаем бота
    bot_process = subprocess.Popen([sys.executable, "bot.py"])
    
    try:
        api_process.wait()
        bot_process.wait()
    except KeyboardInterrupt:
        api_process.terminate()
        bot_process.terminate()


if __name__ == "__main__":
    main()
