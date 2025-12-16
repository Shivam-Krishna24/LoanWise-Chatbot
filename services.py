import random
import math
from decimal import Decimal
from .models import LoanApplication, ChatMessage, Customer


class MasterAgent:
    """Stage 1: Pre-Approved Offer"""
    
    @staticmethod
    def greet(phone):
        """Get pre-approved offer for customer"""
        try:
            customer = Customer.objects.get(phone=phone)
            return {
                'success': True,
                'customer': {
                    'id': customer.id,
                    'name': customer.name,
                    'email': customer.email,
                    'pre_approved_limit': float(customer.pre_approved_limit),
                    'pre_approved_rate': float(customer.pre_approved_rate)
                },
                'message': f'Great! I found your profile, {customer.name}! 🎉\n\nYou have a pre-approved loan offer:\n• Max Limit: ₹{int(customer.pre_approved_limit):,}\n• Interest Rate: {customer.pre_approved_rate}% p.a.\n\nHow much would you like to borrow?',
                'stage': 'emi'
            }
        except Customer.DoesNotExist:
            return {
                'success': False,
                'message': "I don't have any pre-approved offer for this number. Let me create a new profile for you.",
                'stage': 'pre_offer'
            }


class SalesAgent:
    """Stage 2: EMI Preview & Explanation"""
    
    @staticmethod
    def calculate_emi(principal, annual_rate, tenure_months):
        """Calculate EMI using standard formula"""
        principal = float(principal)
        monthly_rate = float(annual_rate) / 12 / 100
        
        if monthly_rate == 0:
            return int(principal / tenure_months)
        
        emi = principal * (monthly_rate * (1 + monthly_rate) ** tenure_months) / \
              ((1 + monthly_rate) ** tenure_months - 1)
        return int(emi)
    
    @staticmethod
    def generate_emi_options(amount, rate, tenures=[12, 24, 36]):
        """Generate EMI options for different tenures"""
        options = []
        for tenure in tenures:
            emi = SalesAgent.calculate_emi(amount, rate, tenure)
            total = emi * tenure
            options.append({
                'tenure': tenure,
                'emi': emi,
                'total_amount': total
            })
        return options
    
    @staticmethod
    def preview_emi(application, amount):
        """Generate EMI preview message"""
        customer = application.customer
        options = SalesAgent.generate_emi_options(
            Decimal(amount), 
            customer.pre_approved_rate
        )
        
        # Save to application
        application.requested_amount = Decimal(amount)
        application.interest_rate = customer.pre_approved_rate
        application.save()
        
        message = f'Perfect! Here are your EMI options for a loan of ₹{int(amount):,}:\n\n'
        for opt in options:
            message += f"• {opt['tenure']} months: ₹{opt['emi']:,}/month (Total: ₹{opt['total_amount']:,})\n"
        
        return {
            'success': True,
            'options': options,
            'message': message,
            'stage': 'kyc'
        }


class VerificationAgent:
    """Stage 3: Instant KYC Validation"""
    
    @staticmethod
    def verify_kyc(application, aadhar, pan):
        """Validate KYC documents"""
        # Dummy validation: PAN must end with 'P'
        is_valid = pan.upper().endswith('P') and len(aadhar) == 12 and aadhar.isdigit()
        
        application.kyc_aadhar = aadhar
        application.kyc_pan = pan.upper()
        
        if is_valid:
            application.kyc_verified = True
            application.status = 'kyc_done'
            application.save()
            
            return {
                'success': True,
                'message': '✅ KYC Verification Successful!\n\nYour documents have been verified. Now let\'s check your eligibility.',
                'stage': 'eligibility'
            }
        else:
            application.save()
            return {
                'success': False,
                'message': '❌ KYC Verification Failed!\n\nPlease ensure your Aadhaar is 12 digits and PAN ends with "P".',
                'stage': 'kyc'
            }


class UnderwritingAgent:
    """Stage 4: Smart Eligibility Decision"""
    
    @staticmethod
    def simulate_credit_score():
        """Generate random credit score (650-800)"""
        return random.randint(650, 800)
    
    @staticmethod
    def check_eligibility(application, monthly_income):
        """Check loan eligibility based on credit score and FOIR"""
        
        credit_score = UnderwritingAgent.simulate_credit_score()
        application.credit_score = credit_score
        application.monthly_income = Decimal(monthly_income)
        
        # Calculate FOIR (EMI to Income ratio)
        if application.emi and monthly_income:
            foir = (float(application.emi) / float(monthly_income)) * 100
            application.foir = Decimal(foir)
        
        # Approval logic
        if credit_score < 700:
            decision = 'rejected'
            message = '❌ Unfortunately, we cannot approve your loan at this time due to a lower credit score.'
        elif application.foir and application.foir > 50:
            decision = 'conditional'
            message = '⚠️ Your loan is conditionally approved. You may need to provide additional documentation.'
        else:
            decision = 'approved'
            message = '✅ Congratulations! Your loan has been APPROVED!'
        
        application.status = decision
        application.save()
        
        return {
            'success': True,
            'decision': decision,
            'credit_score': credit_score,
            'monthly_income': float(monthly_income),
            'foir': float(application.foir) if application.foir else 0,
            'message': message,
            'stage': 'sanction' if decision == 'approved' else 'pre_offer'
        }


class SanctionAgent:
    """Stage 5: Auto Sanction Letter"""
    
    @staticmethod
    def generate_sanction_letter_html(application):
        """Generate HTML sanction letter"""
        
        html = f"""
        <div style="border: 1px solid #ddd; padding: 16px; border-radius: 8px; font-size: 13px; background: white;">
            <div style="text-align: center; margin-bottom: 16px; border-bottom: 2px solid #134252; padding-bottom: 12px;">
                <strong>LOAN SANCTION LETTER</strong>
                <div style="font-size: 11px; color: #626c7c; margin-top: 4px;">Dated: {application.created_at.strftime('%d-%m-%Y')}</div>
            </div>

            <table style="width: 100%; margin-bottom: 12px; font-size: 12px;">
                <tr>
                    <td style="padding: 6px;"><strong>Sanction ID:</strong></td>
                    <td style="padding: 6px;">{application.application_id}</td>
                </tr>
                <tr style="background: #f9f9f9;">
                    <td style="padding: 6px;"><strong>Applicant Name:</strong></td>
                    <td style="padding: 6px;">{application.customer.name}</td>
                </tr>
                <tr>
                    <td style="padding: 6px;"><strong>Customer ID:</strong></td>
                    <td style="padding: 6px;">{application.customer.id}</td>
                </tr>
                <tr style="background: #f9f9f9;">
                    <td style="padding: 6px;"><strong>Loan Amount:</strong></td>
                    <td style="padding: 6px;"><strong>₹{int(application.requested_amount):,}</strong></td>
                </tr>
                <tr>
                    <td style="padding: 6px;"><strong>Tenure:</strong></td>
                    <td style="padding: 6px;">{application.tenure_months} months</td>
                </tr>
                <tr style="background: #f9f9f9;">
                    <td style="padding: 6px;"><strong>Monthly EMI:</strong></td>
                    <td style="padding: 6px;"><strong>₹{int(application.emi):,}</strong></td>
                </tr>
                <tr>
                    <td style="padding: 6px;"><strong>Interest Rate:</strong></td>
                    <td style="padding: 6px;">{application.interest_rate}% p.a.</td>
                </tr>
                <tr style="background: #f9f9f9;">
                    <td style="padding: 6px;"><strong>Validity:</strong></td>
                    <td style="padding: 6px;">30 days from this date</td>
                </tr>
            </table>

            <div style="background: #e8f4f5; padding: 10px; border-radius: 4px; margin-top: 12px; font-size: 11px;">
                <strong>Terms & Conditions:</strong><br>
                ✓ Funds will be disbursed within 24 hours of final approval<br>
                ✓ Insurance coverage included<br>
                ✓ Prepayment allowed without penalty
            </div>
        </div>
        """
        
        return html
