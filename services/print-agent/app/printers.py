import json
import platform
import subprocess
from pathlib import Path


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


def submit_pdf(printer_name: str, pdf_path: Path, document_name: str) -> str:
    """Submit a PDF to the Windows spooler and return its job id.

    A spooler job id confirms queue acceptance only. It is not proof that paper was emitted.
    """
    if platform.system() != "Windows":
        raise RuntimeError("真实打印仅支持 Windows")
    try:
        import win32print  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("缺少 pywin32，无法访问 Windows Spooler") from exc
    handle = win32print.OpenPrinter(printer_name)
    try:
        job_id = win32print.StartDocPrinter(handle, 1, (document_name, None, "RAW"))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, pdf_path.read_bytes())
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
    finally:
        win32print.ClosePrinter(handle)
    return str(job_id)
