"""
VoxPop 运行观测 — 状态记录 + macOS 通知
每次标注运行结束后写 status.json + 发持久弹窗
"""
import json, os, subprocess, time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

STATUS_FILE = Path(__file__).parent / "run_status.json"
HISTORY_FILE = Path(__file__).parent / "run_history.json"
MAX_HISTORY = 20


def send_notification(title: str, message: str, alert: bool = True):
    """发送 macOS 通知
    alert=True → 弹窗 Alert（不点不消失）
    alert=False → Banner（自动消失）
    """
    if alert:
        # 使用 display alert — 阻塞式弹窗，不点不消失
        # stderr 是因为 osascript 会把 button returned 输出到 stderr
        script = f'''
        display alert "{title}" message "{message}" buttons {{"知道了"}} default button "知道了"
        '''
    else:
        script = f'''
        display notification "{message}" with title "{title}"
        '''
    try:
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, timeout=10,
        )
    except Exception as e:
        print(f"[observer] 发送通知失败: {e}")


def notify_normal(stats: dict):
    """正常运行完毕 — Banner 通知（不挡屏幕）"""
    total = stats.get("total_labeled", 0)
    llm = stats.get("llm_count", 0)
    cost = stats.get("estimated_cost", 0)
    plat_summary = ", ".join(
        f"{p}:{d['total']}" for p, d in stats.get("platforms", {}).items()
    )
    send_notification(
        "✅ VoxPop 标注完成",
        f"共 {total} 条 (LLM {llm}) | 费用 ${cost:.4f} | {plat_summary}",
        alert=False,
    )


def notify_warning(stats: dict):
    """有异常但继续完成了 — Alert 弹窗"""
    warns = stats.get("warnings", [])
    errors = stats.get("errors", 0)
    total = stats.get("total_labeled", 0)
    send_notification(
        "⚠️ VoxPop 标注异常",
        f"错误 {errors}/{total} | {' | '.join(warns[:3])}",
        alert=True,
    )


def notify_error(reason: str):
    """严重错误 — 停止并 Alert"""
    send_notification(
        "🔴 VoxPop 标注已停止",
        reason,
        alert=True,
    )


def write_status(result: dict):
    """写入运行状态（覆盖最新一条 + 追加历史）"""
    result["_timestamp"] = datetime.now().isoformat()
    result["_time_str"] = datetime.now().strftime("%m-%d %H:%M")

    # 写最新状态
    STATUS_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    # 追加历史（保留最近 MAX_HISTORY 条）
    history = []
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text())
        except (json.JSONDecodeError, Exception):
            history = []
    history.append(result)
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2))


def read_status() -> dict:
    """读取最新运行状态"""
    if STATUS_FILE.exists():
        try:
            return json.loads(STATUS_FILE.read_text())
        except (json.JSONDecodeError, Exception):
            return {"status": "unknown", "error": "无法解析状态文件"}
    return {"status": "never_run", "message": "尚未运行过标注"}


def read_history() -> list:
    """读取运行历史"""
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except (json.JSONDecodeError, Exception):
            return []
    return []
