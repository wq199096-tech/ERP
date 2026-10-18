export type Platform = 'DOUYIN' | 'PINDUODUO' | 'TAOBAO' | 'JD' | 'CSV';

export interface OrderItem {
  id: string;
  platform_sku: string;
  internal_sku: string | null;
  product_name: string;
  specification: string;
  quantity: number;
  unit_price: string;
  barcode: string;
}

export interface Order {
  id: string;
  platform: Platform;
  shop_id: string;
  shop_name: string;
  platform_order_no: string;
  erp_order_no: string;
  version: number;
  package_id: string;
  warehouse_id: string | null;
  status: string;
  after_sale_status: string;
  audit_status: string;
  print_status: string;
  print_blockers: string[];
  receiver_name: string;
  receiver_phone_masked: string;
  receiver_address_masked: string;
  warehouse_name: string;
  paid_amount: string;
  discount_amount: string;
  remark: string;
  created_at: string;
  paid_at: string;
  items: OrderItem[];
}

export interface ProductSku {
  id: string;
  product_id: string;
  product_name: string;
  sku_code: string;
  barcode: string;
  specification: string;
  purchase_price: string;
  sale_price: string;
  status: string;
}

export interface Product {
  id: string;
  name: string;
  category_id: string | null;
  description: string;
  status: string;
  skus: ProductSku[];
}

export interface Warehouse {
  id: string;
  code: string;
  name: string;
  address: string;
  is_default: boolean;
  status: string;
}

export interface InventoryBalance {
  id: string;
  warehouse_id: string;
  warehouse_code: string;
  warehouse_name: string;
  sku_id: string;
  sku_code: string;
  product_name: string;
  barcode: string;
  specification: string;
  on_hand: number;
  reserved: number;
  available: number;
  low_stock_threshold: number;
  low_stock: boolean;
}

export interface StockMovement {
  id: string;
  warehouse_id: string;
  sku_id: string;
  movement_type: string;
  quantity: number;
  balance_after: number;
  order_id: string | null;
  note: string;
  created_at: string;
}

export interface ShipmentItem {
  id: string;
  sku_code: string;
  barcode: string;
  product_name: string;
  specification: string;
  expected_quantity: number;
  verified_quantity: number;
}

export interface Shipment {
  id: string;
  shipment_no: string;
  order_id: string;
  erp_order_no: string;
  warehouse_id: string;
  warehouse_name: string;
  status: 'PICKING' | 'VERIFIED' | 'SHIPPED' | 'CANCELLED';
  order_scanned_at: string | null;
  verified_at: string | null;
  shipped_at: string | null;
  items: ShipmentItem[];
}

export interface OrderPage {
  records: Order[];
  total: number;
  page: number;
  page_size: number;
}

export interface PrintJob {
  id: string;
  job_type: string;
  printer_name: string;
  status: string;
  waybill_no?: string;
  system_job_id?: string;
  output_file?: string;
  error_message?: string;
  payload?: Record<string, unknown>;
  created_at: string;
}

