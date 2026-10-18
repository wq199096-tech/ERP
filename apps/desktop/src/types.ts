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

