import { AlignCenterOutlined, BorderOutlined, DragOutlined } from '@ant-design/icons';
import { Button, Card, InputNumber, message, Select, Space, Typography } from 'antd';
import { useState } from 'react';

type ElementKey = 'name' | 'sku' | 'barcode' | 'qrcode' | 'price';
type Position = { x: number; y: number };

const labels: Record<ElementKey, string> = {
  name: '商品名称：304 不锈钢保温杯',
  sku: 'SKU：SO-CUP-450',
  barcode: '|||| || ||||| 6970000010011',
  qrcode: '▦ 二维码',
  price: '零售价：¥69.00',
};

export function LabelDesigner() {
  const [preset, setPreset] = useState('60x40');
  const [width, setWidth] = useState(60);
  const [height, setHeight] = useState(40);
  const [positions, setPositions] = useState<Record<ElementKey, Position>>({
    name: { x: 5, y: 5 }, sku: { x: 5, y: 14 }, barcode: { x: 5, y: 23 },
    qrcode: { x: 44, y: 20 }, price: { x: 39, y: 31 },
  });
  const setSize = (value: string) => {
    setPreset(value);
    if (value !== 'custom') {
      const [nextWidth, nextHeight] = value.split('x').map(Number);
      setWidth(nextWidth); setHeight(nextHeight);
    }
  };
  const move = (key: ElementKey, event: React.DragEvent<HTMLDivElement>) => {
    const parent = event.currentTarget.parentElement!.getBoundingClientRect();
    const x = Math.max(1, Math.min(width - 12, ((event.clientX - parent.left) / parent.width) * width));
    const y = Math.max(1, Math.min(height - 6, ((event.clientY - parent.top) / parent.height) * height));
    setPositions((current) => ({ ...current, [key]: { x, y } }));
  };
  const center = () => setPositions((current) => ({ ...current, name: { ...current.name, x: width / 4 } }));
  const save = () => {
    localStorage.setItem('smartorder-label-template', JSON.stringify({ width, height, positions }));
    message.success('商品标签模板已保存到本机');
  };

  return <Card title="可视化商品标签模板" extra={<Typography.Text type="secondary">拖动字段调整毫米坐标</Typography.Text>}>
    <div className="label-designer">
      <div className="label-toolbar">
        <Typography.Text strong>纸张尺寸</Typography.Text>
        <Select value={preset} onChange={setSize} options={[
          { value: '40x30', label: '40 × 30 mm' }, { value: '50x30', label: '50 × 30 mm' },
          { value: '60x40', label: '60 × 40 mm' }, { value: 'custom', label: '自定义尺寸' },
        ]} />
        <Space><InputNumber min={20} max={120} suffix="mm" value={width} disabled={preset !== 'custom'} onChange={(value) => setWidth(value ?? 60)} /><span>×</span><InputNumber min={20} max={180} suffix="mm" value={height} disabled={preset !== 'custom'} onChange={(value) => setHeight(value ?? 40)} /></Space>
        <Button icon={<AlignCenterOutlined />} onClick={center}>名称居中</Button>
        <Button type="primary" onClick={save}>保存模板</Button>
        <Typography.Text type="secondary"><BorderOutlined /> 画布按实际毫米比例缩放</Typography.Text>
      </div>
      <div className="label-stage">
        <div className="label-paper" style={{ aspectRatio: `${width}/${height}`, width: `${Math.min(width * 7, 540)}px` }}>
          {(Object.keys(labels) as ElementKey[]).map((key) => <div key={key} draggable className={`label-element ${key}`} style={{ left: `${positions[key].x / width * 100}%`, top: `${positions[key].y / height * 100}%` }} onDragEnd={(event) => move(key, event)}><DragOutlined /> {labels[key]}</div>)}
        </div>
        <Typography.Text type="secondary">当前：{width} × {height} mm · 条码、二维码、商品名、SKU、价格字段均可拖动</Typography.Text>
      </div>
    </div>
  </Card>;
}

