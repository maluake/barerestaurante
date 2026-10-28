import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as Tooltip from "@radix-ui/react-tooltip";
import { AuthProvider, useAuth } from "@/lib/auth";
import { ToastProvider, Spinner } from "@/components/ui";
import { AppShell } from "@/layout/AppShell";
import { ApiError } from "@/lib/api";

const Login = lazy(() => import("@/pages/auth/Login"));
const Signup = lazy(() => import("@/pages/auth/Signup"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Alerts = lazy(() => import("@/pages/Alerts"));
const Assistant = lazy(() => import("@/pages/Assistant"));
const Orders = lazy(() => import("@/pages/orders/Orders"));
const NewOrder = lazy(() => import("@/pages/orders/NewOrder"));
const Kitchen = lazy(() => import("@/pages/orders/Kitchen"));
const Sales = lazy(() => import("@/pages/sales/Sales"));
const Products = lazy(() => import("@/pages/stock/Products"));
const ProductDetail = lazy(() => import("@/pages/stock/ProductDetail"));
const Expiry = lazy(() => import("@/pages/stock/Expiry"));
const Movements = lazy(() => import("@/pages/stock/Movements"));
const Inventory = lazy(() => import("@/pages/stock/Inventory"));
const InventoryDetail = lazy(() => import("@/pages/stock/InventoryDetail"));
const Waste = lazy(() => import("@/pages/stock/Waste"));
const Transfers = lazy(() => import("@/pages/stock/Transfers"));
const MenuList = lazy(() => import("@/pages/menu/MenuList"));
const MenuItemPage = lazy(() => import("@/pages/menu/MenuItemPage"));
const ShoppingList = lazy(() => import("@/pages/purchasing/ShoppingList"));
const PurchaseOrders = lazy(() => import("@/pages/purchasing/PurchaseOrders"));
const PurchaseOrderDetail = lazy(() => import("@/pages/purchasing/PurchaseOrderDetail"));
const Suppliers = lazy(() => import("@/pages/purchasing/Suppliers"));
const SupplierDetail = lazy(() => import("@/pages/purchasing/SupplierDetail"));
const Quotations = lazy(() => import("@/pages/purchasing/Quotations"));
const Compare = lazy(() => import("@/pages/purchasing/Compare"));
const Opportunities = lazy(() => import("@/pages/purchasing/Opportunities"));
const Finance = lazy(() => import("@/pages/finance/Finance"));
const Reports = lazy(() => import("@/pages/Reports"));
const Settings = lazy(() => import("@/pages/settings/Settings"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: true,
      retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
    },
  },
});

function RequireAuth({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <Spinner className="min-h-screen" />;
  if (!me) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  return <>{children}</>;
}

function Home() {
  const { can } = useAuth();
  if (can("dashboard.view")) return <Dashboard />;
  if (can("kitchen.update") && !can("orders.manage")) return <Navigate to="/cozinha" replace />;
  if (can("orders.view")) return <Navigate to="/pedidos" replace />;
  if (can("stock.view")) return <Navigate to="/estoque/produtos" replace />;
  return <Navigate to="/configuracoes" replace />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Tooltip.Provider>
        <ToastProvider>
          <AuthProvider>
            <BrowserRouter>
              <Suspense fallback={<Spinner className="min-h-[50vh]" />}>
                <Routes>
                  <Route path="/login" element={<Login />} />
                  <Route path="/cadastro" element={<Signup />} />
                  <Route element={<RequireAuth><AppShell /></RequireAuth>}>
                    <Route index element={<Home />} />
                    <Route path="alertas" element={<Alerts />} />
                    <Route path="assistente" element={<Assistant />} />
                    <Route path="pedidos" element={<Orders />} />
                    <Route path="pedidos/novo" element={<NewOrder />} />
                    <Route path="cozinha" element={<Kitchen />} />
                    <Route path="vendas" element={<Sales />} />
                    <Route path="estoque/produtos" element={<Products />} />
                    <Route path="estoque/produtos/:id" element={<ProductDetail />} />
                    <Route path="estoque/validades" element={<Expiry />} />
                    <Route path="estoque/movimentacoes" element={<Movements />} />
                    <Route path="estoque/inventarios" element={<Inventory />} />
                    <Route path="estoque/inventarios/:id" element={<InventoryDetail />} />
                    <Route path="estoque/perdas" element={<Waste />} />
                    <Route path="estoque/transferencias" element={<Transfers />} />
                    <Route path="cardapio" element={<MenuList />} />
                    <Route path="cardapio/:id" element={<MenuItemPage />} />
                    <Route path="compras/lista" element={<ShoppingList />} />
                    <Route path="compras/pedidos" element={<PurchaseOrders />} />
                    <Route path="compras/pedidos/:id" element={<PurchaseOrderDetail />} />
                    <Route path="compras/fornecedores" element={<Suppliers />} />
                    <Route path="compras/fornecedores/:id" element={<SupplierDetail />} />
                    <Route path="compras/cotacoes" element={<Quotations />} />
                    <Route path="compras/comparador" element={<Compare />} />
                    <Route path="compras/oportunidades" element={<Opportunities />} />
                    <Route path="financeiro" element={<Finance />} />
                    <Route path="relatorios" element={<Reports />} />
                    <Route path="configuracoes" element={<Settings />} />
                    <Route path="configuracoes/:tab" element={<Settings />} />
                    <Route path="*" element={<Navigate to="/" replace />} />
                  </Route>
                </Routes>
              </Suspense>
            </BrowserRouter>
          </AuthProvider>
        </ToastProvider>
      </Tooltip.Provider>
    </QueryClientProvider>
  );
}
