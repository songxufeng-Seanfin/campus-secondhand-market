from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """后台用户管理：把扩展字段加入列表页与编辑页。"""

    list_display = ("username", "phone", "is_staff", "date_joined")
    fieldsets = UserAdmin.fieldsets + (("扩展信息", {"fields": ("phone", "avatar")}),)
