# -*- coding: utf-8 -*-
import os
import sys
import atexit
import tempfile

LOCK_FILE = os.path.join(tempfile.gettempdir(), "agent_v72.lock")

def single_instance():
    if os.path.exists(LOCK_FILE):
        print("⚠️ Agent 已經在執行中！請先停止舊的進程。")
        sys.exit(1)
    
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    
    def remove_lock():
        try:
            os.remove(LOCK_FILE)
        except:
            pass
    atexit.register(remove_lock)

if __name__ == "__main__":
    single_instance()
    from core.agent import Agent
    Agent().start()
