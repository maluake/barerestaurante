from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.core.serializers import TenantSerializer
from apps.inventory.units import IncompatibleUnits, convert

from .models import MenuCategory, MenuItem, MenuItemCostSnapshot, MenuItemRevision, RecipeIngredient
from .services import recalculate


class MenuCategorySerializer(TenantSerializer):
    class Meta:
        model = MenuCategory
        fields = ["id", "name", "sort_order"]


class RecipeIngredientSerializer(TenantSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_code = serializers.CharField(source="unit.code", read_only=True)

    class Meta:
        model = RecipeIngredient
        fields = ["id", "product", "product_name", "quantity", "unit", "unit_code", "loss_percent", "notes"]

    def validate(self, attrs):
        if attrs["quantity"] <= 0:
            raise serializers.ValidationError({"quantity": "A quantidade deve ser maior que zero."})
        if not 0 <= attrs.get("loss_percent", 0) < 100:
            raise serializers.ValidationError({"loss_percent": "A perda deve estar entre 0 e 99,99%."})
        try:
            convert(1, attrs["unit"], attrs["product"].unit, attrs["product"])
        except IncompatibleUnits as exc:
            raise serializers.ValidationError({"unit": exc.message})
        return attrs


class MenuItemSerializer(TenantSerializer):
    ingredients = RecipeIngredientSerializer(many=True, required=False)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    direct_product_name = serializers.CharField(source="direct_product.name", read_only=True, default=None)
    has_reliable_recipe = serializers.BooleanField(read_only=True)
    contribution_margin = serializers.SerializerMethodField()
    margin_percent = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = [
            "id", "name", "category", "category_name", "description", "price", "stock_mode", "direct_product",
            "direct_product_name", "direct_quantity", "direct_unit", "yield_portions", "requires_preparation",
            "prep_time_minutes", "is_available", "status", "pos_code", "theoretical_cost", "cost_complete",
            "cost_updated_at", "contribution_margin", "margin_percent", "has_reliable_recipe", "ingredients",
            "created_at", "updated_at",
        ]
        read_only_fields = ["status", "theoretical_cost", "cost_complete", "cost_updated_at", "created_at", "updated_at"]

    def get_contribution_margin(self, obj):
        return str((obj.price - obj.theoretical_cost).quantize(Decimal("0.01")))

    def get_margin_percent(self, obj):
        if not obj.price:
            return None
        return str(((obj.price - obj.theoretical_cost) / obj.price * 100).quantize(Decimal("0.1")))

    def validate(self, attrs):
        mode = attrs.get("stock_mode", getattr(self.instance, "stock_mode", "recipe"))
        if attrs.get("price") is not None and attrs["price"] < 0:
            raise serializers.ValidationError({"price": "O preço não pode ser negativo."})
        if attrs.get("yield_portions") is not None and attrs["yield_portions"] <= 0:
            raise serializers.ValidationError({"yield_portions": "O rendimento deve ser maior que zero."})
        if mode == "direct":
            product = attrs.get("direct_product", getattr(self.instance, "direct_product", None))
            qty = attrs.get("direct_quantity", getattr(self.instance, "direct_quantity", None))
            if not product or not qty:
                raise serializers.ValidationError({"direct_product": "Informe o produto e a quantidade baixada por venda."})
            unit = attrs.get("direct_unit", getattr(self.instance, "direct_unit", None)) or product.unit
            try:
                convert(1, unit, product.unit, product)
            except IncompatibleUnits as exc:
                raise serializers.ValidationError({"direct_unit": exc.message})
        return attrs

    def _snapshot(self, item):
        return {
            "name": item.name, "price": str(item.price), "stock_mode": item.stock_mode,
            "yield_portions": str(item.yield_portions),
            "ingredients": [{"product": i.product.name, "quantity": str(i.quantity), "unit": i.unit.code,
                             "loss_percent": str(i.loss_percent)} for i in item.ingredients.select_related("product", "unit")],
        }

    @transaction.atomic
    def create(self, validated):
        ingredients = validated.pop("ingredients", [])
        item = MenuItem.objects.create(**validated)
        for ing in ingredients:
            RecipeIngredient.objects.create(menu_item=item, **ing)
        recalculate(item, reason="Cadastro")
        MenuItemRevision.objects.create(menu_item=item, user=self.context["request"].user, summary="Item criado",
                                        snapshot=self._snapshot(item))
        return item

    @transaction.atomic
    def update(self, instance, validated):
        ingredients = validated.pop("ingredients", None)
        old = self._snapshot(instance)
        instance = super().update(instance, validated)
        if ingredients is not None:
            instance.ingredients.all().delete()
            for ing in ingredients:
                RecipeIngredient.objects.create(menu_item=instance, **ing)
        new = self._snapshot(instance)
        if new != old:
            changes = [k for k in new if new[k] != old.get(k)]
            labels = {"name": "nome", "price": "preço", "stock_mode": "tipo de baixa", "yield_portions": "rendimento",
                      "ingredients": "ingredientes"}
            MenuItemRevision.objects.create(menu_item=instance, user=self.context["request"].user,
                                            summary="Alterado: " + ", ".join(labels.get(c, c) for c in changes),
                                            snapshot={"before": old, "after": new})
        recalculate(instance, reason="Ficha técnica ou preço alterado")
        return instance


class CostSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItemCostSnapshot
        fields = ["cost_per_portion", "price", "reason", "created_at"]


class RevisionSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True, default=None)

    class Meta:
        model = MenuItemRevision
        fields = ["id", "summary", "snapshot", "user_name", "created_at"]
