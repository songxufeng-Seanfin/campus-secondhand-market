from django.contrib import admin

from .models import Category, Product


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
