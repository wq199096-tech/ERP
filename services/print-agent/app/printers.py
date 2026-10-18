import json
import math
import platform
import subprocess
from pathlib import Path
from typing import Any

PRINTER_STATUS_MAP = {
    0x00000002: "ERROR",
    0x00000004: "PAPER_JAM",
    0x00000010: "PAPER_OUT",
    0x00000020: "MANUAL_FEED",
    0x00000040: "PAPER_PROBLEM",
    0x00000080: "OFFLINE",
    0x00000200: "OUTPUT_BIN_FULL",
    0x00000400: "USER_INTERVENTION",
    0x00000800: "DOOR_OPEN",
    0x00001000: "NOT_AVAILABLE",
}

JOB_STATUS_MAP = {
    0x00000001: "PAUSED",
    0x00000002: "ERROR",
    0x00000004: "DELETED",
    0x00000020: "OFFLINE",
    0x00000040: "PAPER_OUT",
    0x00000080: "PRINTED",
    0x00000200: "BLOCKED_DEVICE_QUEUE",
    0x00000400: "PRINTING",
    0x00000800: "RETAINED",
}


def _windows_records() -> list[dict[str, Any]]:
    if platform.system() != "Windows":
        return []
    script = (
        "Get-CimInstance Win32_Printer | "
        "Select-Object Name,Default,WorkOffline,DriverName,PrinterStatus,DetectedErrorState | "
        "ConvertTo-Json -Compress"
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
        return records if isinstance(records, list) else [records]
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return []


def list_printers() -> list[dict[str, Any]]:
    printers: list[dict[str, Any]] = []
    for item in _windows_records():
        status_codes = {item.get("PrinterStatus"), item.get("DetectedErrorState")}
        is_online = (
            not bool(item.get("WorkOffline"))
            and 7 not in status_codes
            and 9 not in status_codes
        )
        printers.append(
            {
                "name": item["Name"],
                "is_default": bool(item.get("Default")),
                "is_online": is_online,
                "driver": item.get("DriverName", "Windows"),
                "capability": "PDF_RENDERED_GDI",
                "status": "OFFLINE" if not is_online else "READY",
            }
        )
    printers.append(
        {
            "name": "MockPrinter 智单测试打印机",
            "is_default": not printers or not any(item["is_default"] for item in printers),
            "is_online": True,
            "driver": "MOCK",
            "capability": "PDF_AND_SIMULATION",
            "status": "READY",
        }
    )
    return printers


def _check_printer_status(printer_name: str) -> None:
    record = next((item for item in _windows_records() if item.get("Name") == printer_name), None)
    if not record:
        raise RuntimeError(f"找不到 Windows 打印机：{printer_name}")
    if bool(record.get("WorkOffline")) or record.get("PrinterStatus") == 7:
        raise RuntimeError("打印机离线，任务未提交到 Spooler")
    if record.get("PrinterStatus") == 5:
        raise RuntimeError("打印机预热中，请稍后重试")
    if record.get("DetectedErrorState") == 3:
        raise RuntimeError("打印机缺纸，任务未提交到 Spooler")
    if record.get("DetectedErrorState") == 4:
        raise RuntimeError("打印机缺纸，任务未提交到 Spooler")
    if record.get("DetectedErrorState") == 8:
        raise RuntimeError("打印机卡纸，任务未提交到 Spooler")
    if record.get("DetectedErrorState") == 9:
        raise RuntimeError("打印机离线，任务未提交到 Spooler")


def _render_pdf_pages(pdf_path: Path, dpi: int = 300) -> tuple[list[Any], tuple[float, float]]:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise RuntimeError("缺少 pypdfium2，无法渲染 PDF") from exc
    try:
        document = pdfium.PdfDocument(str(pdf_path))
    except Exception as exc:
        raise RuntimeError("PDF 渲染失败：文件无效") from exc
    images: list[Any] = []
    page_size = (0.0, 0.0)
    try:
        for page in document:
            width_pt, height_pt = page.get_size()
            current_size = (width_pt * 25.4 / 72, height_pt * 25.4 / 72)
            if not images:
                page_size = current_size
            elif math.dist(current_size, page_size) > 0.5:
                raise RuntimeError("同一打印文档内出现多种纸张尺寸，请拆分打印任务")
            bitmap = page.render(scale=dpi / 72)
            images.append(bitmap.to_pil().convert("RGB"))
    except RuntimeError:
        for image in images:
            image.close()
        raise
    finally:
        document.close()
    if not images:
        raise RuntimeError("PDF 渲染失败：没有页面")
    return images, page_size


def get_spooler_job_status(printer_name: str, system_job_id: str) -> dict[str, str]:
    """Read a spooler status without treating queue disappearance as successful printing."""
    if platform.system() != "Windows":
        return {"status": "UNKNOWN", "message": "Spooler 状态查询仅支持 Windows"}
    try:
        import win32print  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("缺少 pywin32，无法查询 Windows Spooler") from exc
    handle = win32print.OpenPrinter(printer_name)
    try:
        jobs = win32print.EnumJobs(handle, 0, 1000, 1)
        numeric_id = int(system_job_id)
        job = next((item for item in jobs if item.get("JobId") == numeric_id), None)
        if job is None:
            return {"status": "UNKNOWN", "message": "作业已离开队列；不能自动视为实际出纸"}
        status_code = int(job.get("Status") or 0)
        names = [name for bit, name in JOB_STATUS_MAP.items() if status_code & bit]
        if status_code & 0x00000080:
            status = "PRINTED"
        elif status_code & 0x00000002 or status_code & 0x00000040 or status_code & 0x00000200:
            status = "FAILED"
        elif status_code & 0x00000400:
            status = "PRINTING"
        else:
            status = "SUBMITTED"
        return {"status": status, "message": "、".join(names) or "已由 Windows Spooler 接收"}
    finally:
        win32print.ClosePrinter(handle)


def submit_pdf(printer_name: str, pdf_path: Path, document_name: str) -> str:
    """Render a PDF and submit it through Windows GDI, preserving the Spooler job id."""
    if platform.system() != "Windows":
        raise RuntimeError("真实打印仅支持 Windows")
    _check_printer_status(printer_name)
    try:
        import pywintypes  # type: ignore[import-not-found]
        import win32con  # type: ignore[import-not-found]
        import win32gui  # type: ignore[import-not-found]
        import win32print  # type: ignore[import-not-found]
        import win32ui  # type: ignore[import-not-found]
        from PIL.ImageWin import Dib
    except ImportError as exc:
        raise RuntimeError("缺少 pywin32/Pillow，无法访问 Windows GDI 打印") from exc

    try:
        images, page_size = _render_pdf_pages(pdf_path)
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError("PDF 渲染失败") from exc

    handle = win32print.OpenPrinter(printer_name)
    device_context = None
    document_started = False
    try:
        info = win32print.GetPrinter(handle, 2)
        processor = info.get("pPrintProcessor") or "winspool"
        mode_size = win32print.DocumentProperties(0, handle, printer_name, None, None, 0)
        driver_extra = max(mode_size - pywintypes.DEVMODEType().Size, 0)
        devmode = pywintypes.DEVMODEType(driver_extra)
        devmode.Fields |= win32con.DM_PAPERSIZE
        devmode.Fields |= win32con.DM_PAPERWIDTH
        devmode.Fields |= win32con.DM_PAPERLENGTH
        devmode.Fields |= win32con.DM_ORIENTATION
        devmode.PaperSize = win32con.DMPAPER_USER
        devmode.PaperWidth = int(page_size[0] * 10)
        devmode.PaperLength = int(page_size[1] * 10)
        devmode.Orientation = win32con.DMORIENT_PORTRAIT
        win32print.DocumentProperties(
            0,
            handle,
            printer_name,
            devmode,
            devmode,
            win32con.DM_IN_BUFFER | win32con.DM_OUT_BUFFER,
        )
        hdc = win32gui.CreateDC(processor, printer_name, devmode)
        device_context = win32ui.CreateDCFromHandle(hdc)
        job_id = win32print.StartDoc(
            device_context.GetHandleOutput(), (document_name, None, None, 0)
        )
        document_started = True
        page_width = device_context.GetDeviceCaps(win32con.HORZRES)
        page_height = device_context.GetDeviceCaps(win32con.VERTRES)
        device_context.StartPage()
        for image in images:
            dib = Dib(image)
            dib.draw(
                device_context.GetHandleOutput(),
                (0, 0, page_width, page_height),
            )
            device_context.EndPage()
            if image is not images[-1]:
                device_context.StartPage()
        device_context.EndDoc()
        return str(job_id)
    except Exception as exc:
        if device_context is not None and document_started:
            try:
                device_context.EndDoc()
            except Exception:
                pass
        raise RuntimeError(f"Windows 打印失败：{exc}") from exc
    finally:
        if device_context is not None:
            device_context.DeleteDC()
        win32print.ClosePrinter(handle)
        for image in images:
            image.close()
