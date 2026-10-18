import json
import platform
import subprocess


def list_printers() -> list[dict]:
    printers = [
        {
            "name": "MockPrinter 智单测试打印机",
            "is_default": True,
            "is_online": True,
            "driver": "MOCK",
            "capability": "PDF_AND_SIMULATION",
        }
    ]
    if platform.system() != "Windows":
        return printers
    script = (
        "Get-CimInstance Win32_Printer | "
        "Select-Object Name,Default,WorkOffline,DriverName | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        records = json.loads(result.stdout or "[]")
        if isinstance(records, dict):
            records = [records]
        printers.extend(
            {
                "name": item["Name"],
                "is_default": bool(item.get("Default")),
                "is_online": not bool(item.get("WorkOffline")),
                "driver": item.get("DriverName", "Windows"),
                "capability": "WINDOWS_SPOOLER",
            }
            for item in records
        )
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        pass
    return printers
