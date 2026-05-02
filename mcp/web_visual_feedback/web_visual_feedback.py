# mcp/web_visual_feedback/web_visual_feedback.py

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

@dataclass
class ScreenshotRecord:
    path: str
    timestamp: str
    task_id: str
    phase: str

@dataclass
class VisualFeedbackMCP:
    current_screenshot: Optional[ScreenshotRecord] = None
    recent_screenshots: List[ScreenshotRecord] = field(default_factory=list)
    visual_issues: List[dict] = field(default_factory=list)
    iteration_count: int = 0
    last_feedback: str = ""

    def update_screenshot(self, path: str, task_id: str, phase: str):
        record = ScreenshotRecord(
            path=path,
            timestamp=datetime.now().isoformat(),
            task_id=task_id,
            phase=phase
        )
        self.current_screenshot = record
        self.recent_screenshots.append(record)
        if len(self.recent_screenshots) > 5:
            self.recent_screenshots.pop(0)
        self.iteration_count += 1

    def add_visual_issue(self, issue: str, severity: str = "medium", location: str = ""):
        self.visual_issues.append({
            "issue": issue,
            "severity": severity,
            "location": location,
            "timestamp": datetime.now().isoformat()
        })

    def get_feedback_summary(self) -> dict:
        return {
            "current_screenshot": self.current_screenshot.path if self.current_screenshot else None,
            "iteration_count": self.iteration_count,
            "visual_issues_count": len(self.visual_issues),
            "last_feedback": self.last_feedback,
            "recent_issues": self.visual_issues[-3:] if self.visual_issues else []
        }

    def clear(self):
        self.current_screenshot = None
        self.visual_issues.clear()
        self.iteration_count = 0