# -*- coding: utf-8 -*-
import os
import sys
import atexit
import tempfile

LOCK_FILE = os.path.join(tempfile.gettempdir(), "agent_v72.lock")

def _is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True

def single_instance():
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r", encoding="utf-8") as f:
                existing_pid = int(f.read().strip() or "0")
        except Exception:
            existing_pid = 0

        if _is_pid_running(existing_pid):
            print(f"⚠️ Agent is already running (PID: {existing_pid}). Stop the existing process first.")
            sys.exit(1)
        else:
            # stale lock: process no longer exists
            try:
                os.remove(LOCK_FILE)
            except OSError:
                pass
    
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    
    def remove_lock():
        try:
            os.remove(LOCK_FILE)
        except OSError:
            pass
    atexit.register(remove_lock)

if __name__ == "__main__":
    single_instance()
    from core.agent import Agent
    Agent().start()
