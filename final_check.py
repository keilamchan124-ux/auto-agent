# -*- coding: utf-8 -*-
import subprocess, json, os
from dotenv import load_dotenv

load_dotenv(".env")
KEY = os.getenv("MIMO_API_KEY", "").strip()
# 確保使用 SGP 節點
URL = "https://token-plan-sgp.xiaomimimo.com/v1/chat/completions"

def test():
    # 這裡是最關鍵的 ID 變體：Xiaomi 官方文件中 Token Plan 專用的 ID 是這個：
    # 根據文檔，請務必嘗試 mimo-v2.5-pro (全小寫)
    model_id = "mimo-v2.5-pro"
    
    print(f"Testing Model: {model_id} on SGP Node...")
    
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "Success?"}],
        "max_tokens": 10
    }
    
    # 官方要求的標準 Header 組合
    cmd = [
        "curl", "-s", "-i", URL,
        "-H", f"Authorization: Bearer {KEY}",
        "-H", "Content-Type: application/json",
        "-H", "User-Agent: OpenClaw/1.3.5", # 必須偽裝成 Coding Tool
        "-H", "Accept: application/json",
        "-d", json.dumps(payload)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    print(result.stdout)

if __name__ == "__main__":
    test()