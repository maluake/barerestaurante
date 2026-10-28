from django.conf import settings
from django.contrib import admin
from django.http import FileResponse, HttpResponseNotFound, JsonResponse
from django.urls import include, path, re_path
from rest_framework.routers import DefaultRouter

from apps.alerts.views import AlertViewSet, NotificationsView, PreferencesView
from apps.analytics.views import AssistantView, DashboardView, ReportListView, ReportView
from apps.core.views import (
    AuditLogViewSet,
    ChangePasswordView,
    ContextView,
    CsrfView,
    LoginView,
    LogoutView,
    MeView,
    OrganizationView,
    PersonalDataExportView,
    SignupView,
    TeamViewSet,
    UnitViewSet,
)
from apps.finance.views import CashFlowView, CashSessionViewSet, ExpenseCategoryViewSet, FinancialEntryViewSet, SummaryView
from apps.integrations.views import CatalogView, IntegrationConfigViewSet, IntegrationLogViewSet
from apps.inventory.views import (
    CategoryViewSet,
    ConvertView,
    ExpiryOverviewView,
    InventoryCountViewSet,
    LotViewSet,
    MovementViewSet,
    ProductViewSet,
    StockOperationViewSet,
    StorageLocationViewSet,
    TransferViewSet,
    UnitOfMeasureViewSet,
    WasteViewSet,
)
from apps.menu.views import MenuCategoryViewSet, MenuItemViewSet
from apps.purchasing.views import (
    CompareView,
    OpportunitiesView,
    PurchaseIssueViewSet,
    PurchaseOrderViewSet,
    QuotationViewSet,
    ShoppingListViewSet,
    SupplierViewSet,
)
from apps.sales.views import ImportBatchViewSet, OrderViewSet, PosMappingViewSet, SaleViewSet

router = DefaultRouter()
router.register("units", UnitViewSet, basename="unit")
router.register("team", TeamViewSet, basename="team")
router.register("audit", AuditLogViewSet, basename="audit")
router.register("units-of-measure", UnitOfMeasureViewSet, basename="uom")
router.register("categories", CategoryViewSet, basename="category")
router.register("locations", StorageLocationViewSet, basename="location")
router.register("products", ProductViewSet, basename="product")
router.register("lots", LotViewSet, basename="lot")
router.register("movements", MovementViewSet, basename="movement")
router.register("stock-operations", StockOperationViewSet, basename="stock-operation")
router.register("waste", WasteViewSet, basename="waste")
router.register("inventory-counts", InventoryCountViewSet, basename="inventory-count")
router.register("transfers", TransferViewSet, basename="transfer")
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("quotations", QuotationViewSet, basename="quotation")
router.register("shopping-lists", ShoppingListViewSet, basename="shopping-list")
router.register("purchase-orders", PurchaseOrderViewSet, basename="purchase-order")
router.register("purchase-issues", PurchaseIssueViewSet, basename="purchase-issue")
router.register("menu-categories", MenuCategoryViewSet, basename="menu-category")
router.register("menu-items", MenuItemViewSet, basename="menu-item")
router.register("orders", OrderViewSet, basename="order")
router.register("sales", SaleViewSet, basename="sale")
router.register("pos-mappings", PosMappingViewSet, basename="pos-mapping")
router.register("import-batches", ImportBatchViewSet, basename="import-batch")
router.register("expense-categories", ExpenseCategoryViewSet, basename="expense-category")
router.register("financial-entries", FinancialEntryViewSet, basename="financial-entry")
router.register("cash-sessions", CashSessionViewSet, basename="cash-session")
router.register("alerts", AlertViewSet, basename="alert")
router.register("integrations", IntegrationConfigViewSet, basename="integration")
router.register("integration-logs", IntegrationLogViewSet, basename="integration-log")

api = [
    path("auth/csrf/", CsrfView.as_view()),
    path("auth/login/", LoginView.as_view()),
    path("auth/logout/", LogoutView.as_view()),
    path("auth/me/", MeView.as_view()),
    path("auth/signup/", SignupView.as_view()),
    path("auth/change-password/", ChangePasswordView.as_view()),
    path("auth/my-data/", PersonalDataExportView.as_view()),
    path("context/", ContextView.as_view()),
    path("organization/", OrganizationView.as_view()),
    path("expiry/", ExpiryOverviewView.as_view()),
    path("convert/", ConvertView.as_view()),
    path("compare/", CompareView.as_view()),
    path("opportunities/", OpportunitiesView.as_view()),
    path("finance/summary/", SummaryView.as_view()),
    path("finance/cash-flow/", CashFlowView.as_view()),
    path("dashboard/", DashboardView.as_view()),
    path("reports/", ReportListView.as_view()),
    path("reports/<str:key>/", ReportView.as_view()),
    path("assistant/", AssistantView.as_view()),
    path("alert-preferences/", PreferencesView.as_view()),
    path("notifications/", NotificationsView.as_view()),
    path("integration-catalog/", CatalogView.as_view()),
    path("health/", lambda r: JsonResponse({"status": "ok"})),
    path("", include(router.urls)),
]


def spa(request, *args, **kwargs):
    """Serve o frontend compilado (SPA) quando disponível."""
    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        return HttpResponseNotFound("Frontend não compilado. Em desenvolvimento, use `npm run dev` em frontend/.")
    return FileResponse(open(index, "rb"), content_type="text/html")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(api)),
    re_path(r"^(?!api/|admin/|static/).*$", spa),
]
