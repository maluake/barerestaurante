from django.contrib import admin

from .models import AuditLog, Membership, Organization, Unit


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "plan", "is_demo", "created_at"]


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "city", "is_active"]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "organization", "role", "is_active"]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "organization", "user", "action", "entity", "summary"]
    list_filter = ["action", "entity"]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
