#!/bin/bash
# 🤖 Agent V7.2 Keep-Alive Server (Linux/macOS)

echo -e "\033[1;32m==========================================\033[0m"
echo -e "\033[1;32m[System] Starting Agent V7.2 Server...\033[0m"
echo -e "\033[1;32m==========================================\033[0m"

# 如果使用虛擬環境，請取消註解下面這行
# source venv/bin/activate

while true; do
    python3 main.py
    EXIT_CODE=$?

    if [ $EXIT_CODE -eq 0 ]; then
        echo -e "\n\033[1;32m[System] Agent closed normally. Ending script.\033[0m"
        break
    fi

    echo -e "\n\033[1;31m[Warning] Agent crashed abnormally, Error Code: $EXIT_CODE !\033[0m"
    echo "$(date) - Crash ErrorCode: $EXIT_CODE" >> agent_crash.log
    echo -e "\033[1;33m[System] Auto-restarting in 3 seconds... Press Ctrl+C to stop.\033[0m"
    sleep 3
done
