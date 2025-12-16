from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
import json
import uuid
from datetime import datetime

from .models import Customer, LoanApplication, ChatMessage
from .serializers import LoanApplicationSerializer, ChatMessageSerializer
from .services import (
    MasterAgent, SalesAgent, VerificationAgent,
    UnderwritingAgent, SanctionAgent
)


def index(request):
    """Render chatbot UI"""
    return render(request, 'chatbot/index.html')


@csrf_exempt
@api_view(['POST'])
def start_application(request):
    """Initialize a new loan application or retrieve existing customer"""
    try:
        data = request.data
        phone = data.get('phone', '').strip()
        
        if not phone or not phone.isdigit() or len(phone) != 10:
            return Response(
                {'error': 'Please enter a valid 10-digit phone number'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if customer exists
        is_new_user = False
        try:
            customer = Customer.objects.get(phone=phone)
        except Customer.DoesNotExist:
            # Create new customer with minimal data
            is_new_user = True
            customer = Customer.objects.create(
                phone=phone,
                name=f"User {phone[-4:]}",  # Temporary name - will be updated
                email=f"user_{phone}@loanwise.com",  # Temporary email - will be updated
                pre_approved_limit=300000,
                pre_approved_rate=13.0
            )
        
        # Create new loan application
        app_id = f"APP{uuid.uuid4().hex[:10].upper()}"
        application = LoanApplication.objects.create(
            customer=customer,
            application_id=app_id,
            status='pre_offer' if not is_new_user else 'new_user_details'
        )
        
        # Return appropriate response based on user type
        if is_new_user:
            # New user - ask for details
            return Response({
                'success': True,
                'application_id': app_id,
                'customer': {
                    'phone': customer.phone,
                    'name': customer.name,
                    'pre_approved_limit': customer.pre_approved_limit,
                    'pre_approved_rate': customer.pre_approved_rate
                },
                'message': 'Welcome to LoanWise! Let me collect your details.',
                'stage': 'new_user_details',
                'is_new_user': True
            }, status=status.HTTP_201_CREATED)
        else:
            # Existing user - show offer
            result = MasterAgent.greet(phone)
            ChatMessage.objects.create(
                application=application,
                message_type='master_agent',
                content=result['message']
            )
            
            return Response({
                'success': True,
                'application_id': app_id,
                'customer': {
                    'phone': customer.phone,
                    'name': customer.name,
                    'pre_approved_limit': customer.pre_approved_limit,
                    'pre_approved_rate': customer.pre_approved_rate
                },
                'message': result['message'],
                'stage': 'emi',
                'is_new_user': False
            }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        print(f"Error in start_application: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@csrf_exempt
@api_view(['POST'])
def save_new_user_details(request):
    """Save new user details to database"""
    try:
        data = request.data
        app_id = data.get('application_id')
        phone = data.get('phone')
        name = data.get('name')
        dob = data.get('dob')
        email = data.get('email')
        address = data.get('address')
        income = data.get('income')
        
        # Validate inputs
        if not all([app_id, phone, name, dob, email, address, income]):
            return Response(
                {'error': 'All fields are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get the application and customer
        try:
            application = LoanApplication.objects.get(application_id=app_id)
        except LoanApplication.DoesNotExist:
            return Response(
                {'error': 'Application not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        customer = application.customer
        
        # Update customer with real details
        customer.name = name
        customer.email = email
        customer.save()
        
        # Update application status and income
        try:
            income_num = int(str(income).replace(',', ''))
        except ValueError:
            income_num = int(income)
        
        application.monthly_income = income_num
        application.status = 'emi'
        application.save()
        
        # Save user details as chat message for history
        ChatMessage.objects.create(
            application=application,
            message_type='user_details',
            content=f"Name: {name}, DOB: {dob}, Email: {email}, Address: {address}, Income: ₹{income_num}",
            metadata={
                'name': name,
                'dob': dob,
                'email': email,
                'address': address,
                'income': income_num
            }
        )
        
        # Format currency
        formatted_income = f"₹{income_num:,}"
        formatted_limit = f"₹{customer.pre_approved_limit:,}"
        
        # Return success response with pre-approved offer
        return Response({
            'success': True,
            'customer': {
                'phone': customer.phone,
                'name': customer.name,
                'email': customer.email,
                'pre_approved_limit': customer.pre_approved_limit,
                'pre_approved_rate': customer.pre_approved_rate
            },
            'message': f'✅ Perfect, {name}!\n\n🎉 Your profile has been created.\n\n💰 Max Limit: {formatted_limit}\n📊 Interest Rate: {customer.pre_approved_rate}% p.a.\n\nHow much would you like to borrow?',
            'stage': 'emi'
        })
    
    except LoanApplication.DoesNotExist:
        return Response(
            {'error': 'Application not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        print(f"Error in save_new_user_details: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@csrf_exempt
@api_view(['POST'])
def process_emi(request):
    """Process EMI selection"""
    try:
        data = request.data
        app_id = data.get('application_id')
        amount = data.get('amount')
        tenure = data.get('tenure')
        
        try:
            application = LoanApplication.objects.get(application_id=app_id)
        except LoanApplication.DoesNotExist:
            return Response({'error': 'Application not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Calculate EMI
        try:
            amount_num = int(str(amount).replace(',', ''))
            tenure_num = int(tenure)
        except ValueError:
            amount_num = int(amount)
            tenure_num = int(tenure)
        
        # EMI Calculation Formula: EMI = P * r * (1 + r)^n / ((1 + r)^n - 1)
        monthly_rate = (application.customer.pre_approved_rate / 12) / 100
        emi = int(amount_num * (monthly_rate * ((1 + monthly_rate) ** tenure_num)) / (((1 + monthly_rate) ** tenure_num) - 1))
        
        application.requested_amount = amount_num
        application.tenure_months = tenure_num
        application.emi = emi
        application.status = 'emi_preview'
        application.save()
        
        # Save messages
        ChatMessage.objects.create(
            application=application,
            message_type='user',
            content=f"I want to borrow ₹{amount_num:,} for {tenure_num} months"
        )
        
        ChatMessage.objects.create(
            application=application,
            message_type='sales_agent',
            content=f"Perfect! Your monthly EMI will be ₹{emi:,}. Now let's verify your KYC."
        )
        
        return Response({
            'success': True,
            'emi': emi,
            'total_amount': emi * tenure_num,
            'stage': 'kyc'
        })
    
    except LoanApplication.DoesNotExist:
        return Response({'error': 'Application not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f"Error in process_emi: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@api_view(['POST'])
def verify_kyc(request):
    """Verify KYC documents"""
    try:
        data = request.data
        app_id = data.get('application_id')
        aadhar = data.get('aadhar', '').strip()
        pan = data.get('pan', '').strip().upper()
        
        try:
            application = LoanApplication.objects.get(application_id=app_id)
        except LoanApplication.DoesNotExist:
            return Response({'error': 'Application not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Basic validation
        if not aadhar or len(aadhar) != 12 or not aadhar.isdigit():
            return Response({
                'success': False,
                'message': '❌ Invalid Aadhaar. Must be 12 digits.',
                'stage': 'kyc'
            })
        
        if not pan or len(pan) != 10:
            return Response({
                'success': False,
                'message': '❌ Invalid PAN. Must be 10 characters.',
                'stage': 'kyc'
            })
        
        # Save KYC details
        application.aadhar = aadhar
        application.pan = pan
        application.status = 'kyc_verified'
        application.save()
        
        # Save messages
        ChatMessage.objects.create(
            application=application,
            message_type='user',
            content=f"Aadhaar: {aadhar} | PAN: {pan}"
        )
        
        ChatMessage.objects.create(
            application=application,
            message_type='verification_agent',
            content='✅ KYC verified successfully! Now checking eligibility...'
        )
        
        return Response({
            'success': True,
            'message': '✅ KYC verified successfully!\n\nNow let\'s check your eligibility.',
            'stage': 'eligibility'
        })
    
    except LoanApplication.DoesNotExist:
        return Response({'error': 'Application not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f"Error in verify_kyc: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@api_view(['POST'])
def check_eligibility(request):
    """Check loan eligibility"""
    try:
        data = request.data
        app_id = data.get('application_id')
        monthly_income = data.get('monthly_income')
        
        try:
            application = LoanApplication.objects.get(application_id=app_id)
        except LoanApplication.DoesNotExist:
            return Response({'error': 'Application not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Parse income
        try:
            income_num = int(str(monthly_income).replace(',', ''))
        except ValueError:
            income_num = int(monthly_income)
        
        # Generate credit score (demo)
        credit_score = 650 + int(income_num / 10000) % 250
        
        # Calculate FOIR (Debt to Income Ratio)
        total_monthly_debt = application.emi
        foir = (total_monthly_debt / income_num) * 100
        
        # Eligibility check
        decision = 'approved' if foir <= 50 else 'rejected'
        
        # Save messages
        ChatMessage.objects.create(
            application=application,
            message_type='user',
            content=f"My monthly income is ₹{income_num:,}"
        )
        
        # Update application
        application.monthly_income = income_num
        application.credit_score = credit_score
        application.status = 'approved' if decision == 'approved' else 'rejected'
        application.save()
        
        ChatMessage.objects.create(
            application=application,
            message_type='underwriting_agent',
            content=f"✅ Eligibility check complete!\n\nCredit Score: {credit_score}/900\nFOIR: {foir:.1f}%\n\nDecision: {decision.upper()}",
            metadata={
                'credit_score': credit_score,
                'monthly_income': income_num,
                'foir': foir
            }
        )
        
        if decision == 'approved':
            message = f'✅ Great news! You are approved.\n\n📊 Credit Score: {credit_score}/900\n💰 Loan Amount: ₹{application.requested_amount:,}\n📅 EMI: ₹{application.emi:,}/month\n⏱️ FOIR: {foir:.1f}%\n\nReady to proceed?'
        else:
            message = f'❌ Sorry, you are not eligible at this time.\n\nFOIR: {foir:.1f}% (Max: 50%)\n\nPlease try with higher income or lower loan amount.'
        
        return Response({
            'success': True,
            'decision': decision,
            'credit_score': credit_score,
            'monthly_income': income_num,
            'foir': foir,
            'message': message,
            'stage': 'sanction' if decision == 'approved' else 'eligibility'
        })
    
    except LoanApplication.DoesNotExist:
        return Response({'error': 'Application not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f"Error in check_eligibility: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@api_view(['POST'])
def generate_sanction_letter(request):
    """Generate sanction letter"""
    try:
        data = request.data
        app_id = data.get('application_id')
        
        try:
            application = LoanApplication.objects.get(application_id=app_id)
        except LoanApplication.DoesNotExist:
            return Response(
                {'error': 'Application not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if application.status != 'approved':
            return Response(
                {'error': 'Application must be approved first'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate letter HTML
        letter_html = f"""
        <div class="letter-box">
            <div class="letter-header">
                <div class="letter-title">💳 SANCTION LETTER</div>
                <div style="font-size: 11px; color: var(--text-light);">
                    Application ID: {application.application_id}
                </div>
            </div>
            
            <div class="letter-content">
                <strong>Dear {application.customer.name},</strong>
                <br><br>
                We are pleased to inform you that your loan application has been <strong>APPROVED</strong>!
                <br><br>
                
                <strong>Loan Details:</strong>
                <table class="letter-table">
                    <tr>
                        <td>Loan Amount:</td>
                        <td><strong>₹{application.requested_amount:,}</strong></td>
                    </tr>
                    <tr>
                        <td>Interest Rate:</td>
                        <td><strong>{application.customer.pre_approved_rate}% p.a.</strong></td>
                    </tr>
                    <tr>
                        <td>Tenure:</td>
                        <td><strong>{application.tenure_months} months</strong></td>
                    </tr>
                    <tr>
                        <td>Monthly EMI:</td>
                        <td><strong>₹{application.emi:,}</strong></td>
                    </tr>
                    <tr>
                        <td>Total Amount:</td>
                        <td><strong>₹{application.emi * application.tenure_months:,}</strong></td>
                    </tr>
                    <tr>
                        <td>Processing Fee:</td>
                        <td><strong>₹0 (Waived)</strong></td>
                    </tr>
                    <tr>
                        <td>Credit Score:</td>
                        <td><strong>{application.credit_score}/900</strong></td>
                    </tr>
                </table>
                
                <div class="letter-terms">
                    <strong>Terms & Conditions:</strong><br>
                    • Loan is valid for 30 days from date of this letter<br>
                    • Full KYC documentation required before disbursement<br>
                    • Prepayment allowed without penalty<br>
                    • Funds will be transferred to registered bank account<br>
                    • Rate lock for entire tenure<br>
                    • No hidden charges or processing fees
                </div>
                
                <br><br>
                This letter is valid for 30 days. To proceed, please accept the terms and complete the final verification.
                <br><br>
                
                <strong>LoanWise Team</strong><br>
                <span style="font-size: 12px; color: var(--text-light);">
                    Generated on: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}
                </span>
            </div>
        </div>
        """
        
        application.status = 'sanctioned'
        application.save()
        
        # Save message
        ChatMessage.objects.create(
            application=application,
            message_type='sanction_agent',
            content=f"✅ Your Sanction Letter is ready!\n\nFunds will be transferred to your registered bank account within 24 hours."
        )
        
        return Response({
            'success': True,
            'letter_html': letter_html,
            'message': '✅ Sanction letter generated successfully!',
            'stage': 'sanction'
        })
    
    except LoanApplication.DoesNotExist:
        return Response({'error': 'Application not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f"Error in generate_sanction_letter: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@api_view(['GET'])
def get_application(request, app_id):
    """Retrieve application details"""
    try:
        application = LoanApplication.objects.get(application_id=app_id)
        return Response({
            'success': True,
            'application_id': application.application_id,
            'customer_name': application.customer.name,
            'loan_amount': application.requested_amount,
            'emi': application.emi,
            'tenure': application.tenure_months,
            'status': application.status
        })
    except LoanApplication.DoesNotExist:
        return Response({'error': 'Application not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
