"""
Twilio Webhook Routes

Handles incoming SMS replies for queue confirmations.
"""
from flask import Blueprint, request, Response, abort
from .queue_confirmation import process_sms_reply
import logging
import os

logger = logging.getLogger(__name__)

twilio_bp = Blueprint('twilio', __name__, url_prefix='/webhook')


def validate_twilio_signature():
    """
    SECURITY: Validate that the request is actually from Twilio.
    Returns True if valid or if validation is disabled (no auth token set).
    """
    auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
    if not auth_token:
        # No auth token configured - skip validation (dev mode)
        logger.warning("TWILIO_AUTH_TOKEN not set - skipping signature validation")
        return True
    
    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(auth_token)
        
        # Get the full URL and signature
        url = request.url
        signature = request.headers.get('X-Twilio-Signature', '')
        
        # Validate
        if validator.validate(url, request.form, signature):
            return True
        else:
            logger.warning(f"Invalid Twilio signature from {request.remote_addr}")
            return False
    except ImportError:
        logger.warning("twilio package not installed - skipping signature validation")
        return True


@twilio_bp.route('/sms', methods=['POST'])
def incoming_sms():
    """
    Twilio webhook for incoming SMS messages.
    
    Configure this URL in Twilio console:
    https://yourdomain.com/webhook/sms
    
    For local testing with ngrok:
    https://xxxx.ngrok.io/webhook/sms
    """
    # SECURITY: Validate request is from Twilio
    if not validate_twilio_signature():
        abort(403)  # Forbidden
    
    from_number = request.form.get('From', '')
    body = request.form.get('Body', '')
    
    logger.info(f"Incoming SMS from {from_number}: {body}")
    
    # Process the reply
    result = process_sms_reply(from_number, body)
    
    # Build TwiML response
    response_message = result.get('message', '')
    
    twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{response_message}</Message>
</Response>'''
    
    return Response(twiml, mimetype='application/xml')


@twilio_bp.route('/sms/status', methods=['POST'])
def sms_status_callback():
    """
    Twilio status callback for sent messages.
    
    Optional - tracks delivery status of outgoing SMS.
    """
    message_sid = request.form.get('MessageSid', '')
    message_status = request.form.get('MessageStatus', '')
    
    logger.info(f"SMS {message_sid} status: {message_status}")
    
    # Could update database with delivery status if needed
    
    return Response('OK', status=200)
