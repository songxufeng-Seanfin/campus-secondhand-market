from django.contrib import admin

from .models import (
    Category,
    ChatMessage,
    Conversation,
    Favorite,
    Order,
    Product,
    ProductMessage,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "icon", "order"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """后台商品管理：支持关键词搜索、分类/状态筛选、列表内直接切换上下架。"""

    list_display = ["title", "price", "shipping_policy", "condition", "category", "seller", "is_sold", "is_active", "created_at"]
    list_filter = ["is_sold", "is_active", "shipping_policy", "category", "condition"]
    search_fields = ["title", "description"]
    list_editable = ["is_sold", "is_active"]
    list_select_related = ["seller", "category"]
    readonly_fields = ["views", "created_at", "updated_at"]
    date_hierarchy = "created_at"


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """后台订单管理：运营可以查单、改状态，状态用 list_editable 直接改。"""

    list_display = ["id", "product", "buyer", "seller", "price", "trade_mode", "is_paid", "status", "created_at"]
    list_filter = ["status", "trade_mode", "is_paid", "created_at"]
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


class ChatMessageInline(admin.TabularInline):
    """会话详情页里直接看消息流水，方便排查纠纷。"""

    model = ChatMessage
    extra = 0
    readonly_fields = ["sender", "body", "is_read", "created_at"]


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ["id", "product", "buyer", "seller", "updated_at"]
    search_fields = ["product__title", "buyer__username", "seller__username"]
    list_select_related = ["product", "buyer", "seller"]
    date_hierarchy = "created_at"
    inlines = [ChatMessageInline]


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ["id", "conversation", "sender", "body", "is_read", "created_at"]
    list_filter = ["is_read", "created_at"]
    search_fields = ["body", "sender__username", "conversation__product__title"]
    list_select_related = ["conversation", "sender"]
