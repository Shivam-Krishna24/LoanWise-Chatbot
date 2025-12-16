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
        
        # Get the application and customer
        application = LoanApplication.objects.get(application_id=app_id)
        customer = application.customer
        
        # Update customer with real details
        customer.name = name
        customer.email = email
        customer.save()
        
        # Update application status and income
        application.monthly_income = int(income)
        application.status = 'emi'
        application.save()
        
        # Save user details as chat message for history
        ChatMessage.objects.create(
            application=application,
            message_type='user_details',
            content=f"Name: {name}, DOB: {dob}, Email: {email}, Address: {address}, Income: ₹{income}",
            metadata={
                'name': name,
                'dob': dob,
                'email': email,
                'address': address,
                'income': income
            }
        )
        
        # Return success response
        return Response({
            'success': True,
            'customer': {
                'phone': customer.phone,
                'name': customer.name,
                'email': customer.email,
                'pre_approved_limit': customer.pre_approved_limit,
                'pre_approved_rate': customer.pre_approved_rate
            },
            'message': f'✅ Perfect, {name}! Your profile has been created.\n\n🎉 You have a pre-approved loan offer:\n\n💰 Max Limit: ₹{customer.pre_approved_limit:,}\n📊 Interest Rate: {customer.pre_approved_rate}% p.a.\n\nHow much would you like to borrow?',
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
        
        application = LoanApplication.objects.get(application_id=app_id)
        
        # Calculate EMI
        emi = SalesAgent.calculate_emi(amount, application.customer.pre_approved_rate, tenure)
        
        application.requested_amount = amount
        application.tenure_months = tenure
        application.emi = emi
        application.status = 'emi_preview'
        application.save()
        
        # Save messages
        ChatMessage.objects.create(
            application=application,
            message_type='user',
            content=f"I want to borrow ₹{int(amount):,} for {tenure} months"
        )
        
        ChatMessage.objects.create(
            application=application,
            message_type='sales_agent',
            content=f"Perfect! Your monthly EMI will be ₹{int(emi):,}. Now let's verify your KYC."
        )
        
        return Response({
            'success': True,
            'emi': int(emi),
            'total_amount': int(emi) * tenure,
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
        
        application = LoanApplication.objects.get(application_id=app_id)
        
        result = VerificationAgent.verify_kyc(application, aadhar, pan)
        
        # Save messages
        ChatMessage.objects.create(
            application=application,
            message_type='user',
            content=f"Aadhar: {aadhar} | PAN: {pan}"
        )
        
        ChatMessage.objects.create(
            application=application,
            message_type='verification_agent',
            content=result['message']
        )
        
        return Response({
            'success': result['success'],
            'message': result['message'],
            'stage': result['stage']
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
        
        application = LoanApplication.objects.get(application_id=app_id)
        
        result = UnderwritingAgent.check_eligibility(application, monthly_income)
        
        # Save messages
        ChatMessage.objects.create(
            application=application,
            message_type='user',
            content=f"My monthly income is ₹{int(float(monthly_income)):,}"
        )
        
        ChatMessage.objects.create(
            application=application,
            message_type='underwriting_agent',
            content=result['message'],
            metadata={
                'credit_score': result['credit_score'],
                'monthly_income': result['monthly_income'],
                'foir': result['foir']
            }
        )
        
        # Update application status if approved
        if result['decision'] == 'approved':
            application.status = 'approved'
            application.monthly_income = monthly_income
            application.credit_score = result['credit_score']
            application.save()
        
        return Response({
            'success': True,
            'decision': result['decision'],
            'credit_score': result['credit_score'],
            'monthly_income': result['monthly_income'],
            'foir': result['foir'],
            'message': result['message'],
            'stage': result['stage']
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
        
        application = LoanApplication.objects.get(application_id=app_id)
        
        if application.status != 'approved':
            return Response(
                {'error': 'Application must be approved first'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate letter
        letter_html = SanctionAgent.generate_sanction_letter_html(application)
        
        application.status = 'sanctioned'
        application.save()
        
        # Save message
        ChatMessage.objects.create(
            application=application,
            message_type='sanction_agent',
            content=f"✅ Your Sanction Letter is ready!\n\nWe've generated a professional sanction letter. It has been sent to {application.customer.email}"
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
    """Retrieve application details and chat history"""
    try:
        application = LoanApplication.objects.get(application_id=app_id)
        serializer = LoanApplicationSerializer(application)
        return Response(serializer.data)
    except LoanApplication.DoesNotExist:
        return Response({'error': 'Application not found'}, status=status.HTTP_404_NOT_FOUND)
