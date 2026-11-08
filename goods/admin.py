from django.contrib import admin

from .models import Category, Favorite, Order, Product, ProductMessage


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "icon", "order"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """后台商品管理：支持关键词搜索、分类/状态筛选、列表内直接切换上下架。"""

    list_display = ["title", "price", "condition", "category", "seller", "is_sold", "is_active", "created_at"]
    list_filter = ["is_sold", "is_active", "category", "condition"]
    search_fields = ["title", "description"]
    list_editable = ["is_sold", "is_active"]
    list_select_related = ["seller", "category"]
    readonly_fields = ["views", "created_at", "updated_at"]
    date_hierarchy = "created_at"


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """后台订单管理：运营可以查单、改状态，状态用 list_editable 直接改。"""

    list_display = ["id", "product", "buyer", "seller", "price", "status", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["product__title", "buyer__username", "seller__username"]
    list_select_related = ["product", "buyer", "seller"]
    list_editable = ["status"]
    readonly_fields = ["price", "created_at", "updated_at"]
    date_hierarchy = "created_at"


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ["user", "product", "created_at"]
    search_fields = ["user__username", "product__title"]
    list_select_related = ["user", "product"]


@admin.register(ProductMessage)
class ProductMessageAdmin(admin.ModelAdmin):
    list_display = ["product", "author", "body", "created_at"]
    search_fields = ["body", "product__title", "author__username"]
    list_select_related = ["product", "author"]
