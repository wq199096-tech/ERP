from __future__ import annotations

import argparse
from pathlib import Path

from app.renderer import render_pdf


def _payload(erp_order_no: str) -> dict:
    return {
        "data_source": "MANUAL_TEST",
        "server_task_id": f"hardware-{erp_order_no.lower()}",
        "erp_order_no": erp_order_no,
        "order_version": 1,
        "package_id": f"PKG-{erp_order_no}",
        "receiver_name": "硬件验收测试收件人",
        "receiver_phone": "138****0000",
        "receiver_address": "浙江省杭州市滨江区硬件验收测试地址*** 1 栋",
        "warehouse_name": "杭州一号仓",
        "remark": "打印验收样张，禁止真实寄件",
        "items": [
            {
                "internal_sku": "SO-HARDWARE-001",
                "product_name": "硬件验收测试商品",
                "specification": "100×150 / A4 / 40×30",
                "quantity": 2,
                "barcode": "6970000010011",
                "copies": 1,
            }
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="生成硬件验收测试 PDF 样张")
    parser.add_argument("output", type=Path, help="PDF 输出目录")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    render_pdf("WAYBILL", _payload("SO-HW-WAYBILL"), output / "waybill-100x150.pdf")
    render_pdf("MANIFEST_A4", _payload("SO-HW-MANIFEST"), output / "manifest-a4.pdf")
    payload = _payload("SO-HW-LABEL")
    payload["label_template"] = {
        "schema_version": 1,
        "name": "硬件验收 40×30",
        "width_mm": 40,
        "height_mm": 30,
        "elements": [
            {"kind": "text", "x_mm": 2, "y_mm": 2, "width_mm": 36, "height_mm": 6},
            {"kind": "sku", "x_mm": 2, "y_mm": 9, "width_mm": 36, "height_mm": 5},
            {"kind": "barcode", "x_mm": 2, "y_mm": 15, "width_mm": 24, "height_mm": 12},
            {"kind": "qrcode", "x_mm": 27, "y_mm": 15, "width_mm": 11, "height_mm": 11},
        ],
    }
    render_pdf("PRODUCT_LABEL", payload, output / "label-40x30.pdf")


if __name__ == "__main__":
    main()
