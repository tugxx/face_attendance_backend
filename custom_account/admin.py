from django.contrib import admin

from custom_account.services.user_service import soft_delete_user
from custom_account.models import UserModel



@admin.register(UserModel)
class UserAdmin(admin.ModelAdmin):
    def delete_model(self, request, obj):
        """Ghi đè nút Xóa 1 object trong giao diện Admin"""
        soft_delete_user(obj.id)

    def delete_queryset(self, request, queryset):
        """Ghi đè tính năng chọn nhiều (Action) rồi bấm Xóa"""
        for user in queryset:
            soft_delete_user(user.id)