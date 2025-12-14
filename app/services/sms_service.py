"""
SMS Service for sending verification codes and notifications.
Uses Twilio as the provider but designed to be pluggable.

Required environment variables (optional - will skip sending in dev mode if not set):
- TWILIO_ACCOUNT_SID
- TWILIO_AUTH_TOKEN  
- TWILIO_FROM_NUMBER
"""
import os
import logging

logger = logging.getLogger(__name__)

# Try to import Twilio - it's optional
try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    logger.warning("Twilio not installed - SMS sending will be simulated in dev mode")


def get_twilio_client():
    """Get Twilio client if credentials are configured."""
    if not TWILIO_AVAILABLE:
        return None
    
    account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
    auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
    
    if not account_sid or not auth_token:
        return None
    
    return TwilioClient(account_sid, auth_token)


def format_phone_for_twilio(phone_number):
    """
    Format phone number for Twilio (E.164 format).
    Assumes US numbers if no country code provided.
    """
    if not phone_number:
        return None
    
    # Remove all non-digits
    digits = ''.join(c for c in phone_number if c.isdigit())
    
    # If starts with 1 and is 11 digits, it's already +1 format
    if len(digits) == 11 and digits[0] == '1':
        return f'+{digits}'
    
    # If 10 digits, assume US number
    if len(digits) == 10:
        return f'+1{digits}'
    
    # If already has +, return as is
    if phone_number.startswith('+'):
        return phone_number
    
    # Default: add + prefix
    return f'+{digits}'


def send_verification_sms(phone_number, code):
    """
    Send SMS verification code.
    
    Args:
        phone_number: The phone number to send to
        code: The verification code
    
    Returns:
        dict with 'success' (bool) and 'message' (str) or 'error' (str)
    """
    formatted_phone = format_phone_for_twilio(phone_number)
    if not formatted_phone:
        return {'success': False, 'error': 'Invalid phone number'}
    
    from_number = os.environ.get('TWILIO_FROM_NUMBER')
    message_body = f"Your Pool Cue verification code is: {code}\n\nThis code expires in 10 minutes."
    
    # Try to send via Twilio
    client = get_twilio_client()
    
    if client and from_number:
        try:
            message = client.messages.create(
                body=message_body,
                from_=from_number,
                to=formatted_phone
            )
            logger.info(f"SMS sent successfully to {formatted_phone[-4:]}, SID: {message.sid}")
            return {'success': True, 'message': 'SMS sent successfully', 'sid': message.sid}
        except Exception as e:
            logger.error(f"Twilio SMS error: {e}")
            return {'success': False, 'error': str(e)}
    
    # Dev/demo mode - just log the code
    logger.info(f"[DEV MODE] Would send SMS to {formatted_phone}: {message_body}")
    print(f"\n📱 [DEV SMS] To: {formatted_phone}")
    print(f"   Code: {code}")
    print(f"   (Twilio not configured - code logged for testing)\n")
    
    return {'success': True, 'message': 'SMS simulated (dev mode)', 'dev_mode': True}


def send_queue_notification_sms(phone_number, message):
    """
    Send a queue notification SMS (e.g., "You're up next!").
    
    Args:
        phone_number: The phone number to send to
        message: The notification message
    
    Returns:
        dict with 'success' (bool) and 'message' or 'error'
    """
    formatted_phone = format_phone_for_twilio(phone_number)
    if not formatted_phone:
        return {'success': False, 'error': 'Invalid phone number'}
    
    from_number = os.environ.get('TWILIO_FROM_NUMBER')
    
    client = get_twilio_client()
    
    if client and from_number:
        try:
            sms = client.messages.create(
                body=message,
                from_=from_number,
                to=formatted_phone
            )
            logger.info(f"Queue SMS sent to {formatted_phone[-4:]}, SID: {sms.sid}")
            return {'success': True, 'message': 'SMS sent', 'sid': sms.sid}
        except Exception as e:
            logger.error(f"Queue SMS error: {e}")
            return {'success': False, 'error': str(e)}
    
    # Dev mode
    logger.info(f"[DEV MODE] Queue notification to {formatted_phone}: {message}")
    print(f"\n📱 [DEV SMS] Queue notification to {formatted_phone}: {message}\n")
    return {'success': True, 'message': 'SMS simulated (dev mode)', 'dev_mode': True}


def is_sms_configured():
    """Check if SMS sending is properly configured."""
    return (
        TWILIO_AVAILABLE and
        os.environ.get('TWILIO_ACCOUNT_SID') and
        os.environ.get('TWILIO_AUTH_TOKEN') and
        os.environ.get('TWILIO_FROM_NUMBER')
    )


# Alias for generic SMS sending
send_sms = send_queue_notification_sms
