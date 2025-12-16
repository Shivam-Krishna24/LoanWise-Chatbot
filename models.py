from django.db import models
from django.utils import timezone

class Customer(models.Model):
    """Customer model with pre-approved loan offer"""
    phone = models.CharField(max_length=15, unique=True)
    name = models.CharField(max_length=100)
    email = models.EmailField()
    aadhar = models.CharField(max_length=12, blank=True, null=True)
    pan = models.CharField(max_length=10, blank=True, null=True)
    pre_approved_limit = models.DecimalField(max_digits=12, decimal_places=2)
    pre_approved_rate = models.DecimalField(max_digits=5, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.phone})"

    class Meta:
        db_table = 'customers'
        verbose_name_plural = 'Customers'


class LoanApplication(models.Model):
    """Loan application tracking"""
    STATUS_CHOICES = [
        ('initiated', 'Initiated'),
        ('pre_offer', 'Pre-Approved Offer'),
        ('emi_preview', 'EMI Preview'),
        ('kyc_pending', 'KYC Pending'),
        ('kyc_done', 'KYC Done'),
        ('eligibility_check', 'Eligibility Check'),
        ('approved', 'Approved'),
        ('conditional', 'Conditional Approval'),
        ('rejected', 'Rejected'),
        ('sanctioned', 'Sanctioned'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='applications')
    application_id = models.CharField(max_length=20, unique=True)
    requested_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    tenure_months = models.IntegerField(null=True, blank=True)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    emi = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    credit_score = models.IntegerField(null=True, blank=True)
    monthly_income = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    foir = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='initiated')
    kyc_aadhar = models.CharField(max_length=12, blank=True, null=True)
    kyc_pan = models.CharField(max_length=10, blank=True, null=True)
    kyc_verified = models.BooleanField(default=False)
    sanction_letter_path = models.FileField(upload_to='sanction_letters/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.application_id} - {self.customer.name}"

    class Meta:
        db_table = 'loan_applications'
        ordering = ['-created_at']


class ChatMessage(models.Model):
    """Chat message history"""
    MESSAGE_TYPE_CHOICES = [
        ('user', 'User'),
        ('master_agent', 'Master Agent'),
        ('sales_agent', 'Sales Agent'),
        ('verification_agent', 'Verification Agent'),
        ('underwriting_agent', 'Underwriting Agent'),
        ('sanction_agent', 'Sanction Agent'),
    ]

    application = models.ForeignKey(LoanApplication, on_delete=models.CASCADE, related_name='messages')
    message_type = models.CharField(max_length=25, choices=MESSAGE_TYPE_CHOICES)
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)  # Store quick replies, form data, etc.
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.application.application_id} - {self.message_type}"

    class Meta:
        db_table = 'chat_messages'
        ordering = ['created_at']
