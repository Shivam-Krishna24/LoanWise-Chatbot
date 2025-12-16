from rest_framework import serializers
from .models import Customer, LoanApplication, ChatMessage


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ['id', 'phone', 'name', 'email', 'pre_approved_limit', 'pre_approved_rate']
        read_only_fields = ['id']


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['id', 'message_type', 'content', 'metadata', 'created_at']
        read_only_fields = ['id', 'created_at']


class LoanApplicationSerializer(serializers.ModelSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    customer_email = serializers.CharField(source='customer.email', read_only=True)

    class Meta:
        model = LoanApplication
        fields = [
            'id', 'application_id', 'customer', 'customer_name', 'customer_email',
            'requested_amount', 'tenure_months', 'interest_rate', 'emi',
            'credit_score', 'monthly_income', 'foir', 'status',
            'kyc_verified', 'messages', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'application_id', 'created_at', 'updated_at']


class ChatRequestSerializer(serializers.Serializer):
    """Serializer for chat API requests"""
    application_id = serializers.CharField()
    message = serializers.CharField()
    stage = serializers.CharField()


class KYCRequestSerializer(serializers.Serializer):
    """Serializer for KYC verification"""
    application_id = serializers.CharField()
    aadhar = serializers.CharField(max_length=12)
    pan = serializers.CharField(max_length=10)


class EligibilityRequestSerializer(serializers.Serializer):
    """Serializer for eligibility check"""
    application_id = serializers.CharField()
    monthly_income = serializers.DecimalField(max_digits=12, decimal_places=2)
