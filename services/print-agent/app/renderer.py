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


def _header(canvas: Canvas, width: float, height: float, title: str) -> None:
    canvas.setFillColor(HexColor("#155EEF"))
    canvas.rect(0, height - 15 * mm, width, 15 * mm, fill=1, stroke=0)
    canvas.setFillColorRGB(1, 1, 1)
    canvas.setFont(FONT, 13)
    canvas.drawString(6 * mm, height - 10 * mm, title)


def render_pdf(job_type: str, payload: dict, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    size = PAGE_SIZES.get(job_type, A4)
    width, height = size
    canvas = Canvas(str(target), pagesize=size)
    if job_type == "WAYBILL":
        _render_waybill(canvas, width, height, payload)
    elif job_type.startswith("MANIFEST"):
        _render_manifest(canvas, width, height, payload)
    elif job_type == "PRODUCT_LABEL":
        _render_label(canvas, width, height, payload)
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
    lines = [
        f"测试运单号：{payload.get('waybill_no', 'TEST-PENDING')}",
        f"订单号：{payload.get('order_no', 'SO-DEMO-001')}",
        (
            f"收件人：{payload.get('receiver_name', '测试客户')}  "
            f"{payload.get('phone', '138****0000')}"
        ),
        f"地址：{payload.get('address', '浙江省杭州市测试地址***')}",
        f"商品：{payload.get('product_name', '演示商品')} × {payload.get('quantity', 1)}",
        "说明：此数据由 MockPlatformAdapter 生成，无真实物流效力。",
    ]
    y = height - 25 * mm
    for line in lines:
        canvas.drawString(6 * mm, y, line[:42])
        y -= 9 * mm
    barcode = code128.Code128(payload.get("waybill_no", "TEST0000000001"), barHeight=20 * mm)
    barcode.drawOn(canvas, 8 * mm, 18 * mm)


def _render_manifest(canvas: Canvas, width: float, height: float, payload: dict) -> None:
    _header(canvas, width, height, "智单 ERP 发货清单")
    canvas.setFillColorRGB(0, 0, 0)
    canvas.setFont(FONT, 10)
    y = height - 24 * mm
    rows = [
        ("店铺", payload.get("shop_name", "演示店铺")),
        ("订单号", payload.get("order_no", "SO-DEMO-001")),
        ("仓库", payload.get("warehouse", "杭州一号仓")),
        ("商品", payload.get("product_name", "304 不锈钢保温杯")),
        ("SKU", payload.get("sku", "SO-CUP-450")),
        ("规格", payload.get("specification", "曜石黑 / 450ml")),
        ("数量", str(payload.get("quantity", 1))),
        ("货位", payload.get("location", "A-01-03")),
        ("打包备注", payload.get("remark", "核对颜色后装箱")),
    ]
    for label, value in rows:
        canvas.setFillColor(HexColor("#667085"))
        canvas.drawString(8 * mm, y, f"{label}：")
        canvas.setFillColorRGB(0, 0, 0)
        canvas.drawString(30 * mm, y, str(value)[:70])
        canvas.line(8 * mm, y - 3 * mm, width - 8 * mm, y - 3 * mm)
        y -= 10 * mm


def _render_label(canvas: Canvas, width: float, height: float, payload: dict) -> None:
    canvas.setLineWidth(0.5)
    canvas.rect(2 * mm, 2 * mm, width - 4 * mm, height - 4 * mm)
    canvas.setFont(FONT, 9)
    canvas.drawString(4 * mm, height - 8 * mm, payload.get("product_name", "演示商品")[:16])
    canvas.setFont(FONT, 7)
    canvas.drawString(4 * mm, height - 14 * mm, f"SKU: {payload.get('sku', 'SO-DEMO-001')}")
    canvas.drawString(4 * mm, height - 19 * mm, payload.get("specification", "默认规格")[:24])
    barcode = code128.Code128(payload.get("barcode", "6970000010011"), barHeight=10 * mm)
    barcode.drawOn(canvas, 4 * mm, 4 * mm)
    qr_image = qrcode.make(payload.get("sku", "SO-DEMO-001"))
    qr_buffer = BytesIO()
    qr_image.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    canvas.drawImage(ImageReader(qr_buffer), width - 14 * mm, 4 * mm, 10 * mm, 10 * mm)
