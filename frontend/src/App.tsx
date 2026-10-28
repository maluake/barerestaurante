import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as Tooltip from "@radix-ui/react-tooltip";
import { AuthProvider, useAuth } from "@/lib/auth";
import { ToastProvider, Spinner } from "@/components/ui";
import { AppShell } from "@/layout/AppShell";
import { Guard } from "@/layout/Guard";
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
                    <Route path="alertas" element={<Guard perms={["alerts.view"]}><Alerts /></Guard>} />
                    <Route path="assistente" element={<Guard perms={["assistant.use"]}><Assistant /></Guard>} />
                    <Route path="pedidos" element={<Guard perms={["orders.view"]}><Orders /></Guard>} />
                    <Route path="pedidos/novo" element={<Guard perms={["orders.manage"]}><NewOrder /></Guard>} />
                    <Route path="cozinha" element={<Guard perms={["kitchen.update", "orders.view"]}><Kitchen /></Guard>} />
                    <Route path="vendas" element={<Guard perms={["sales.view"]}><Sales /></Guard>} />
                    <Route path="estoque/produtos" element={<Guard perms={["products.view"]}><Products /></Guard>} />
                    <Route path="estoque/produtos/:id" element={<Guard perms={["products.view"]}><ProductDetail /></Guard>} />
                    <Route path="estoque/validades" element={<Guard perms={["stock.view"]}><Expiry /></Guard>} />
                    <Route path="estoque/movimentacoes" element={<Guard perms={["stock.view"]}><Movements /></Guard>} />
                    <Route path="estoque/inventarios" element={<Guard perms={["stock.view"]}><Inventory /></Guard>} />
                    <Route path="estoque/inventarios/:id" element={<Guard perms={["stock.view"]}><InventoryDetail /></Guard>} />
                    <Route path="estoque/perdas" element={<Guard perms={["waste.manage", "stock.view"]}><Waste /></Guard>} />
                    <Route path="estoque/transferencias" element={<Guard perms={["stock.transfer"]}><Transfers /></Guard>} />
                    <Route path="cardapio" element={<Guard perms={["recipes.view", "orders.view"]}><MenuList /></Guard>} />
                    <Route path="cardapio/:id" element={<Guard perms={["recipes.view"]}><MenuItemPage /></Guard>} />
                    <Route path="compras/lista" element={<Guard perms={["purchases.view"]}><ShoppingList /></Guard>} />
                    <Route path="compras/pedidos" element={<Guard perms={["purchases.view"]}><PurchaseOrders /></Guard>} />
                    <Route path="compras/pedidos/:id" element={<Guard perms={["purchases.view"]}><PurchaseOrderDetail /></Guard>} />
                    <Route path="compras/fornecedores" element={<Guard perms={["suppliers.view"]}><Suppliers /></Guard>} />
                    <Route path="compras/fornecedores/:id" element={<Guard perms={["suppliers.view"]}><SupplierDetail /></Guard>} />
                    <Route path="compras/cotacoes" element={<Guard perms={["suppliers.view"]}><Quotations /></Guard>} />
                    <Route path="compras/comparador" element={<Guard perms={["suppliers.view"]}><Compare /></Guard>} />
                    <Route path="compras/oportunidades" element={<Guard perms={["suppliers.view"]}><Opportunities /></Guard>} />
                    <Route path="financeiro" element={<Guard perms={["finance.view"]}><Finance /></Guard>} />
                    <Route path="relatorios" element={<Guard perms={["reports.view", "reports.finance"]}><Reports /></Guard>} />
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
