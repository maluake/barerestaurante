export type OrderItem = { id: number; menu_item: number; name: string; quantity: string; unit_price: string; notes: string; stock_warning: string; requires_preparation: boolean };
export type Order = {
  id: number; number: number; origin: string; origin_label: string; table_label: string; customer_name: string; notes: string;
  status: string; status_label: string; discount: string; delivery_fee: string; payment_method: string; subtotal: string; total: string;
  stock_status: string; stock_status_label: string; created_by_name: string | null; created_at: string; elapsed_minutes: number;
  is_late: boolean; next_statuses: string[]; items: OrderItem[]; events: { from_status: string; to_status: string; note: string; user_name: string | null; created_at: string }[];
  cancel_reason: string; sale_id: number | null; ready_at: string | null; preparing_at: string | null;
};
export type MenuItem = {
  id: number; name: string; category: number | null; category_name: string | null; description: string; price: string;
  stock_mode: "recipe" | "direct" | "none"; direct_product: number | null; direct_product_name: string | null; direct_quantity: string | null;
  direct_unit: number | null; yield_portions: string; requires_preparation: boolean; prep_time_minutes: number | null; is_available: boolean;
  status: string; pos_code: string; theoretical_cost?: string; cost_complete?: boolean; contribution_margin?: string; margin_percent?: string;
  has_reliable_recipe: boolean; ingredients: { id?: number; product: number; product_name?: string; quantity: string; unit: number; unit_code?: string; loss_percent: string; notes?: string }[];
};
export type Product = {
  id: number; name: string; description: string; category: number | null; category_name: string | null; brand: string; sku: string; barcode: string;
  unit: number; unit_code: string; min_stock: string; ideal_stock: string; max_stock: string | null; default_location: number | null; location_name: string | null;
  main_supplier: number | null; supplier_name: string | null; cost_price: string; is_perishable: boolean; shelf_life_days: number | null; status: string;
  created_at: string; packagings: { id?: number; unit: number; unit_code?: string; quantity: string; contained_unit: number; contained_unit_code?: string }[];
  quantity: string; expired_quantity: string; available_quantity: string; stock_value: string; stock_status: string; next_expiry: string | null;
};
export type Uom = { id: number; code: string; name: string; dimension: string; factor_to_base: string | null; is_global: boolean };

export const ORIGINS = [
  { value: "counter", label: "Balcão" }, { value: "table", label: "Mesa" }, { value: "takeout", label: "Retirada" },
  { value: "delivery", label: "Entrega própria" }, { value: "app", label: "Aplicativo" },
];
export const PAYMENTS = [
  { value: "pix", label: "Pix" }, { value: "credit", label: "Crédito" }, { value: "debit", label: "Débito" }, { value: "cash", label: "Dinheiro" },
  { value: "voucher", label: "Vale-refeição" }, { value: "app", label: "Pago no app" }, { value: "other", label: "Outro" },
];
export const STATUS_ACTION: Record<string, string> = {
  confirmed: "Confirmar", preparing: "Iniciar preparo", ready: "Marcar pronto", dispatched: "Saiu para entrega", delivered: "Entregar", cancelled: "Cancelar",
};
