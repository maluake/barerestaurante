import {
  AlertTriangle, BarChart3, BookOpen, Bot, Boxes, CalendarClock, ChefHat, ClipboardCheck, ClipboardList, FileBarChart,
  LayoutDashboard, Lightbulb, type LucideIcon, Receipt, Repeat, Scale, Settings, ShoppingCart, Trash2, Truck, Wallet, ArrowLeftRight, Tags,
} from "lucide-react";

export type NavItem = { to: string; label: string; icon: LucideIcon; perms: string[] };
export type NavGroup = { label: string; items: NavItem[] };

export const NAV: NavGroup[] = [
  { label: "Visão geral", items: [
    { to: "/", label: "Dashboard", icon: LayoutDashboard, perms: ["dashboard.view"] },
    { to: "/alertas", label: "Atenção", icon: AlertTriangle, perms: ["alerts.view"] },
    { to: "/assistente", label: "Assistente do Negócio", icon: Bot, perms: ["assistant.use"] },
  ] },
  { label: "Operação", items: [
    { to: "/pedidos", label: "Pedidos", icon: ClipboardList, perms: ["orders.view"] },
    { to: "/cozinha", label: "Painel da cozinha", icon: ChefHat, perms: ["kitchen.update", "orders.view"] },
    { to: "/vendas", label: "Vendas", icon: Receipt, perms: ["sales.view"] },
  ] },
  { label: "Estoque", items: [
    { to: "/estoque/produtos", label: "Produtos", icon: Boxes, perms: ["products.view"] },
    { to: "/estoque/validades", label: "Validades", icon: CalendarClock, perms: ["stock.view"] },
    { to: "/estoque/movimentacoes", label: "Movimentações", icon: Repeat, perms: ["stock.view"] },
    { to: "/estoque/inventarios", label: "Inventário", icon: ClipboardCheck, perms: ["stock.view"] },
    { to: "/estoque/perdas", label: "Perdas e desperdício", icon: Trash2, perms: ["waste.manage", "stock.view"] },
    { to: "/estoque/transferencias", label: "Transferências", icon: ArrowLeftRight, perms: ["stock.transfer"] },
  ] },
  { label: "Cardápio", items: [
    { to: "/cardapio", label: "Fichas técnicas", icon: BookOpen, perms: ["recipes.view"] },
  ] },
  { label: "Compras", items: [
    { to: "/compras/lista", label: "Lista de compras", icon: ShoppingCart, perms: ["purchases.view"] },
    { to: "/compras/pedidos", label: "Pedidos de compra", icon: Truck, perms: ["purchases.view"] },
    { to: "/compras/fornecedores", label: "Fornecedores", icon: Tags, perms: ["suppliers.view"] },
    { to: "/compras/cotacoes", label: "Cotações", icon: FileBarChart, perms: ["suppliers.view"] },
    { to: "/compras/comparador", label: "Comparador", icon: Scale, perms: ["suppliers.view"] },
    { to: "/compras/oportunidades", label: "Oportunidades", icon: Lightbulb, perms: ["suppliers.view"] },
  ] },
  { label: "Gestão", items: [
    { to: "/financeiro", label: "Financeiro", icon: Wallet, perms: ["finance.view"] },
    { to: "/relatorios", label: "Relatórios", icon: BarChart3, perms: ["reports.view", "reports.finance"] },
    { to: "/configuracoes", label: "Configurações", icon: Settings, perms: [] },
  ] },
];

export const allowed = (item: NavItem, can: (p: string) => boolean) => item.perms.length === 0 || item.perms.some(can);
