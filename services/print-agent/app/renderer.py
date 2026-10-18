from io import BytesIO
from pathlib import Path

import qrcode
from reportlab.graphics.barcode import code128
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, A5
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen.canvas import Canvas

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
FONT = "STSong-Light"

PAGE_SIZES = {
    "WAYBILL": (100 * mm, 150 * mm),
    "MANIFEST_A4": A4,
    "MANIFEST_A5": A5,
    "MANIFEST_80": (80 * mm, 180 * mm),
    "PRODUCT_LABEL": (60 * mm, 40 * mm),
}


def _print_items(payload: dict) -> list[dict]:
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("打印载荷缺少商品列表")
    return items


def _wrapped_text(text: str, font: str, font_size: int, max_width: float) -> list[str]:
    text = str(text)
    if not text:
        return [""]
    result: list[str] = []
    current = ""
    for character in text:
        trial = current + character
        if pdfmetrics.stringWidth(trial, font, font_size) <= max_width:
            current = trial
        elif not current:
            result.append(character)
        else:
            result.append(current)
            current = character
    if current:
        result.append(current)
    return result


def _header(canvas: Canvas, width: float, height: float, title: str) -> None:
    canvas.setFillColor(HexColor("#155EEF"))
    canvas.rect(0, height - 15 * mm, width, 15 * mm, fill=1, stroke=0)
    canvas.setFillColorRGB(1, 1, 1)
    canvas.setFont(FONT, 13)
    canvas.drawString(6 * mm, height - 10 * mm, title)


def _test_watermark(canvas: Canvas, width: float, height: float) -> None:
    canvas.saveState()
    canvas.setFillColor(HexColor("#D92D20"))
    canvas.setFont(FONT, 22)
    canvas.translate(width / 2, height / 2)
    canvas.rotate(35)
    canvas.setFillAlpha(0.14)
    canvas.drawCentredString(0, 0, "测试样张 · 不可用于寄件")
    canvas.restoreState()


def render_pdf(job_type: str, payload: dict, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    size = PAGE_SIZES.get(job_type, A4)
    if job_type == "PRODUCT_LABEL" and payload.get("label_template"):
        template = payload["label_template"]
        size = (float(template["width_mm"]) * mm, float(template["height_mm"]) * mm)
    width, height = size
    canvas = Canvas(str(target), pagesize=size)
    if job_type == "WAYBILL":
        _render_waybill(canvas, width, height, payload)
    elif job_type.startswith("MANIFEST"):
        _render_manifest(canvas, width, height, payload)
    elif job_type == "PRODUCT_LABEL":
        if payload.get("label_template"):
            for item in _print_items(payload):
                for _ in range(int(item.get("copies", 1))):
                    _render_schema_label(canvas, width, height, payload | {"items": [item]})
                    canvas.showPage()
        else:
            for item in _print_items(payload):
                for _ in range(int(item.get("copies", 1))):
                    _render_label(canvas, width, height, payload | {"items": [item]})
                    canvas.showPage()
        canvas.save()
        return target
    else:
        raise ValueError(f"不支持的任务类型: {job_type}")
    canvas.showPage()
    canvas.save()
    return target


def _render_waybill(canvas: Canvas, width: float, height: float, payload: dict) -> None:
    _header(canvas, width, height, "智单电子面单 · 测试样张")
    canvas.setFillColor(HexColor("#D92D20"))
    canvas.setFont(FONT, 25)
    canvas.saveState()
    canvas.translate(width / 2, height / 2)
    canvas.rotate(32)
    canvas.setFillAlpha(0.16)
    canvas.drawCentredString(0, 0, "测试样张 · 不可用于寄件")
    canvas.restoreState()
    canvas.setFillColorRGB(0, 0, 0)
    canvas.setFont(FONT, 10)
    items = _print_items(payload)
    item_lines = [
        f"{item['product_name']} / {item['internal_sku']} / "
        f"{item['specification'] or '无规格'} × {item['quantity']}"
        for item in items
    ]
    item_lines[0] = f"商品（共 {len(items)} 项）：{item_lines[0]}"
    lines = [
        f"测试运单号：{payload.get('waybill_no', 'TEST-PENDING')}",
        f"ERP 订单号：{payload.get('erp_order_no', payload.get('order_no', 'SO-DEMO-001'))}",
        f"收件人：{payload.get('receiver_name', '测试客户')} "
        f"{payload.get('receiver_phone', '138****0000')}",
        "地址："
        f"{payload.get('receiver_address', payload.get('address', '浙江省杭州市测试地址***'))}",
        f"仓库：{payload.get('warehouse_name', '演示仓库')}",
        *item_lines,
    ]
    if payload.get("remark"):
        lines.append(f"备注：{payload['remark']}")
    lines.append("说明：测试样张，无真实物流效力。")
    layout: list[tuple[str, float]] = []
    for font_size, line_height in ((10, 7), (9, 6.3), (8, 5.6), (7, 5.0), (6, 4.4)):
        layout = []
        y = height - 25 * mm
        for line in lines:
            for text in _wrapped_text(line, FONT, font_size, width - 12 * mm):
                layout.append((text, y))
                y -= line_height
            y -= 1.5
        if y >= 38 * mm:
            canvas.setFont(FONT, font_size)
            for text, text_y in layout:
                canvas.drawString(6 * mm, text_y, text)
            break
    if not layout:
        raise ValueError("电子面单内容超出纸张边界")
    barcode = code128.Code128(payload.get("waybill_no", "TEST0000000001"), barHeight=20 * mm)
    barcode.drawOn(canvas, 8 * mm, 18 * mm)


def _render_manifest(canvas: Canvas, width: float, height: float, payload: dict) -> None:
    items = _print_items(payload)
    page_number = 0

    def start_page(is_first: bool) -> float:
        nonlocal page_number
        page_number += 1
        _header(canvas, width, height, "智单 ERP 发货清单")
        _test_watermark(canvas, width, height)
        y = height - 24 * mm
        rows = [("ERP 订单号", payload.get("erp_order_no", payload.get("order_no", "SO-DEMO-001")))]
        if is_first:
            rows.insert(0, ("店铺", payload.get("shop_name", "演示店铺")))
        rows.append(("仓库", payload.get("warehouse_name", "杭州一号仓")))
        if page_number > 1:
            rows.insert(0, ("页码", f"第 {page_number} 页 · 续页"))
        canvas.setFillColorRGB(0, 0, 0)
        canvas.setFont(FONT, 10)
        for label, value in rows:
            canvas.setFillColor(HexColor("#667085"))
            canvas.drawString(8 * mm, y, f"{label}：")
            canvas.setFillColorRGB(0, 0, 0)
            for text in _wrapped_text(str(value), FONT, 10, width - 40 * mm):
                canvas.drawString(30 * mm, y, text)
                y -= 7 * mm
            canvas.line(8 * mm, y - 3 * mm, width - 8 * mm, y - 3 * mm)
            y -= 10 * mm
        if is_first:
            canvas.setFillColor(HexColor("#155EEF"))
            canvas.drawString(8 * mm, y, f"商品明细（共 {len(items)} 项）")
            y -= 7 * mm
        return y

    y = start_page(True)
    for item in items:
        value = (
            f"{item['product_name']} | SKU {item['internal_sku']} | "
            f"{item['specification'] or '无规格'} | 数量 {item['quantity']}"
        )
        for text in _wrapped_text(value, FONT, 9, width - 40 * mm):
            if y - 6 * mm < 14 * mm:
                canvas.showPage()
                y = start_page(False)
            canvas.setFillColor(HexColor("#667085"))
            canvas.drawString(8 * mm, y, "商品：")
            canvas.setFillColorRGB(0, 0, 0)
            canvas.drawString(30 * mm, y, text)
            y -= 6 * mm
        canvas.line(8 * mm, y - 2 * mm, width - 8 * mm, y - 2 * mm)
        y -= 8 * mm
    if payload.get("remark"):
        canvas.setFillColor(HexColor("#667085"))
        canvas.drawString(8 * mm, y, "打包备注：")
        canvas.setFillColorRGB(0, 0, 0)
        for text in _wrapped_text(payload["remark"], FONT, 9, width - 40 * mm):
            if y - 6 * mm < 14 * mm:
                canvas.showPage()
                y = start_page(False)
                canvas.setFillColor(HexColor("#667085"))
                canvas.drawString(8 * mm, y, "打包备注（续）：")
                canvas.setFillColorRGB(0, 0, 0)
            canvas.drawString(30 * mm, y, text)
            y -= 6 * mm
        y -= 4 * mm
    canvas.setFillColor(HexColor("#667085"))
    canvas.setFont(FONT, 8)
    canvas.drawString(8 * mm, 8 * mm, f"第 {page_number} 页 · 测试样张")


def _render_label(canvas: Canvas, width: float, height: float, payload: dict) -> None:
    if payload.get("label_template"):
        _render_schema_label(canvas, width, height, payload)
        return
    items = _print_items(payload)
    canvas.setLineWidth(0.5)
    canvas.rect(2 * mm, 2 * mm, width - 4 * mm, height - 4 * mm)
    _test_watermark(canvas, width, height)
    y = height - 8 * mm
    for item in items:
        canvas.setFont(FONT, 9)
        for text in _wrapped_text(item["product_name"], FONT, 9, width - 22 * mm):
            canvas.drawString(4 * mm, y, text)
            y -= 5 * mm
        canvas.setFont(FONT, 7)
        canvas.drawString(4 * mm, y, f"SKU: {item['internal_sku']}")
        y -= 4.5 * mm
        for text in _wrapped_text(item["specification"] or "无规格", FONT, 7, width - 8 * mm):
            canvas.drawString(4 * mm, y, text)
            y -= 4.5 * mm
        y -= mm
    if y < 15 * mm:
        raise ValueError("商品标签内容超出纸张边界")
    canvas.setFont(FONT, 9)
    first_barcode = next((item["barcode"] for item in items if item["barcode"]), "6970000010011")
    barcode = code128.Code128(first_barcode, barHeight=10 * mm)
    barcode.drawOn(canvas, 4 * mm, 4 * mm)
    qr_image = qrcode.make(items[0]["internal_sku"])
    qr_buffer = BytesIO()
    qr_image.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    canvas.drawImage(ImageReader(qr_buffer), width - 14 * mm, 4 * mm, 10 * mm, 10 * mm)


def _render_schema_label(canvas: Canvas, width: float, height: float, payload: dict) -> None:
    template = payload["label_template"]
    items = _print_items(payload)
    if len(items) > 1:
        raise ValueError("模板商品标签一次仅支持一个商品，请为每个商品创建独立任务")
    item = items[0]
    values = {
        "text": item["product_name"],
        "sku": item["internal_sku"],
        "barcode": item["barcode"] or item["internal_sku"],
        "qrcode": item["internal_sku"],
        "price": str(payload.get("price", "¥0.00")),
    }
    canvas.setLineWidth(0.4)
    canvas.rect(0.5 * mm, 0.5 * mm, width - mm, height - mm)
    _test_watermark(canvas, width, height)
    for element in template["elements"]:
        kind = element["kind"]
        x = float(element["x_mm"]) * mm
        box_height = float(element["height_mm"]) * mm
        box_width = float(element["width_mm"]) * mm
        y = height - (float(element["y_mm"]) * mm) - box_height
        value = element.get("value") or values[kind]
        canvas.saveState()
        path = canvas.beginPath()
        path.rect(x, y, box_width, box_height)
        canvas.clipPath(path, stroke=0)
        if kind in {"text", "sku", "price"}:
            canvas.setFont(FONT, max(6, min(12, box_height / mm * 0.65)))
            canvas.drawString(x, y + max(1, box_height * 0.2), str(value))
        elif kind == "barcode":
            code = code128.Code128(str(value), barHeight=max(mm, box_height - 2 * mm))
            code.drawOn(canvas, x, y + mm)
        else:
            qr_image = qrcode.make(str(value))
            qr_buffer = BytesIO()
            qr_image.save(qr_buffer, format="PNG")
            qr_buffer.seek(0)
            side = min(box_width, box_height)
            canvas.drawImage(ImageReader(qr_buffer), x, y, side, side)
        canvas.restoreState()
