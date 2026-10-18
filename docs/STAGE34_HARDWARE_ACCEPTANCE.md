# Stage 3.4 硬件验收清单

## 样张生成

在仓库根目录执行：

```powershell
$env:PYTHONPATH = 'services/print-agent'
.venv\Scripts\python.exe services\print-agent\scripts\generate_hardware_samples.py .hardware-samples
```

生成文件：

| 文件 | 纸张 | 用途 |
| --- | --- | --- |
| `waybill-100x150.pdf` | 100 × 150 mm，纵向 | 电子面单 |
| `manifest-a4.pdf` | A4，纵向 | 发货清单 |
| `label-40x30.pdf` | 40 × 30 mm，纵向 | 商品标签 |

所有样张均带“测试样张 · 不可用于寄件”水印。

## 自动化已覆盖

- PDF 尺寸断言。
- ReportLab 文字内容提取、全部 SKU 数量与特殊字符。
- Code128 条码使用 `zxing-cpp` 渲染后真实扫码读取。
- Mock GDI 的 DEVMODE 纸宽、纸长、方向、`WINSPOOL` 驱动参数断言。
- 缺纸、离线、卡纸状态在提交前拦截。

## 每台真实打印机必须人工核验

1. 在 Windows 控制面板或厂商工具中选择指定打印机，不允许默认使用系统默认打印机。
2. 使用 DEVMODE 设置纸张尺寸；确认打印输出尺寸没有被驱动二次缩放。
3. 检查面单方向和 300 DPI 缩放，不得裁切四周内容。
4. 用扫码枪或手机扫码确认 100 × 150 mm 面单 Code128 可读。
5. 记录 Spooler 返回的作业 ID、开始时间、完成时间。
6. 数实际出纸页数：面单 1 页、A4 清单 1 页、标签每 SKU 1 页。
7. 在热敏打印机上验证缺纸放纸后可继续，离线恢复后不会重复出已打印页。
8. 在 A4 打印机上验证缺纸、取消队列和离线恢复，异常后人工核对实际页数。
9. 记录测试打印机品牌、型号、驱动版本和日期；结果由硬件验收人签字确认。

> 当前仓库交付完成的是软件与 Mock Spooler 自动验收。**硬件验收待完成**，不能声明热敏打印机或 A4 真实硬件已通过。
