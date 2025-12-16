from django.contrib import admin
from .models import Customer, LoanApplication, ChatMessage

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'email', 'pre_approved_limit', 'pre_approved_rate')
    search_fields = ('phone', 'name', 'email')

@admin.register(LoanApplication)
class LoanApplicationAdmin(admin.ModelAdmin):
    list_display = ('application_id', 'customer', 'requested_amount', 'status', 'created_at')
    search_fields = ('application_id', 'customer__phone')
    list_filter = ('status', 'created_at')

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('application', 'message_type', 'created_at')
    list_filter = ('message_type', 'created_at')
