# Email Sending Diagnostic Plan

## Issue
Users are not receiving registration confirmation emails when registering with the auth_service.

## Investigation Steps

### 1. Verify SendGrid API Key and Configuration

**Actions:**
- Verify the SendGrid API key is valid and not expired
- Check if the SendGrid account is in good standing
- Ensure the sending domain (em8606.laborolabs.com) is properly verified in SendGrid
- Confirm the FROM email address is authorized to send emails

**Implementation:**
```python
# Add a diagnostic endpoint to test email sending
@router.post("/test-email", response_model=Dict[str, Any])
async def test_email(
    email: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Test endpoint to verify email sending functionality."""
    try:
        # Create email service
        email_service = EmailService(background_tasks, db)
        
        # Send a test email
        result = await send_email(
            subject="Test Email from Auth Service",
            recipients=[email],
            body="<p>This is a test email to verify the email sending functionality.</p>"
        )
        
        return {
            "message": "Test email sent",
            "status_code": result,
            "recipient": email
        }
    except Exception as e:
        return {
            "message": "Failed to send test email",
            "error": str(e)
        }
```

### 2. Enhance Error Logging

**Actions:**
- Add more detailed logging in the email sending process
- Capture and log the full response from SendGrid API
- Ensure errors are properly propagated and not silently caught

**Implementation:**
```python
# Modify the send_email function in app/core/email.py to include more detailed logging
async def send_email(subject: str, recipients: List[str], body: str):
    """
    Send an email using SendGrid API with enhanced logging.
    """
    if not settings.SENDGRID_API_KEY:
        logger.error("SendGrid API key not configured", event_type="email_config_error")
        raise RuntimeError("SendGrid API key not configured")
    
    # Log the attempt to send email
    logger.info(
        "Attempting to send email",
        event_type="email_send_attempt",
        recipients=recipients,
        subject=subject
    )
    
    # Prepare SendGrid API request
    url = f"{settings.SENDGRID_HOST}/v3/mail/send"
    
    # Format recipients as SendGrid expects
    formatted_recipients = [{"email": recipient} for recipient in recipients]
    
    # Prepare the email payload
    payload = {
        "personalizations": [
            {
                "to": formatted_recipients,
                "subject": subject
            }
        ],
        "from": {
            "email": settings.EMAIL_FROM_ADDRESS,
            "name": settings.EMAIL_FROM_NAME
        },
        "content": [
            {
                "type": "text/html",
                "value": body
            }
        ]
    }
    
    # Add Azure domain tracking settings if configured
    if settings.AZURE_DOMAIN:
        payload["tracking_settings"] = {
            "click_tracking": {
                "enable": True,
                "enable_text": True
            },
            "open_tracking": {
                "enable": True
            }
        }
        
        # Add custom domain for click and open tracking
        payload["mail_settings"] = {
            "sandbox_mode": {
                "enable": False
            }
        }
    
    headers = {
        "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        logger.debug(
            "SendGrid API request prepared",
            event_type="email_request_prepared",
            url=url,
            payload=payload
        )
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            
            # Log the raw response for debugging
            logger.debug(
                "SendGrid API response received",
                event_type="email_api_response",
                status_code=response.status_code,
                response_text=response.text,
                response_headers=dict(response.headers)
            )
            
            if response.status_code >= 400:
                logger.error(
                    f"Failed to send email: {response.status_code} - {response.text}",
                    event_type="email_send_error",
                    status_code=response.status_code,
                    response=response.text
                )
                raise RuntimeError(f"Failed to send email: {response.status_code} - {response.text}")
            
            logger.info(
                "Email sent successfully",
                event_type="email_sent",
                recipients=recipients,
                subject=subject,
                status_code=response.status_code
            )
            
            return response.status_code
            
    except httpx.RequestError as e:
        # Network-related errors
        logger.error(
            f"Network error when sending email: {str(e)}",
            event_type="email_network_error",
            error=str(e),
            error_type=type(e).__name__
        )
        raise RuntimeError(f"Network error when sending email: {str(e)}")
    except Exception as e:
        logger.error(
            f"Error sending email: {str(e)}",
            event_type="email_send_exception",
            error=str(e),
            error_type=type(e).__name__
        )
        raise RuntimeError(f"Error sending email: {str(e)}")
```

### 3. Implement Email Sending Retry Mechanism

**Actions:**
- Add a retry mechanism for transient failures
- Implement exponential backoff for retries
- Set appropriate timeout values for API calls

**Implementation:**
```python
# Add retry logic to the send_email function
async def send_email_with_retry(subject: str, recipients: List[str], body: str, max_retries: int = 3):
    """
    Send an email with retry logic for transient failures.
    """
    retry_count = 0
    last_exception = None
    
    while retry_count < max_retries:
        try:
            return await send_email(subject, recipients, body)
        except Exception as e:
            last_exception = e
            retry_count += 1
            
            # Only retry for certain types of errors (network errors, 5xx responses)
            if isinstance(e, httpx.RequestError) or "500" in str(e) or "503" in str(e):
                # Exponential backoff: 1s, 2s, 4s, etc.
                wait_time = 2 ** (retry_count - 1)
                
                logger.warning(
                    f"Email sending failed, retrying in {wait_time}s (attempt {retry_count}/{max_retries})",
                    event_type="email_retry",
                    retry_count=retry_count,
                    max_retries=max_retries,
                    wait_time=wait_time,
                    error=str(e)
                )
                
                await asyncio.sleep(wait_time)
            else:
                # Don't retry for client errors or other issues
                logger.error(
                    f"Email sending failed with non-retriable error",
                    event_type="email_error_non_retriable",
                    error=str(e)
                )
                raise e
    
    # If we've exhausted all retries
    logger.error(
        f"Email sending failed after {max_retries} retries",
        event_type="email_all_retries_failed",
        error=str(last_exception)
    )
    raise last_exception
```

### 4. Verify Email Templates

**Actions:**
- Ensure all email templates exist and are properly formatted
- Verify template variables are correctly replaced
- Test template rendering with sample data

**Implementation:**
```python
# Add a function to verify template rendering
def verify_template_rendering(template_name: str, context: Dict[str, Any]) -> str:
    """
    Verify that a template can be rendered with the given context.
    
    Args:
        template_name: Name of the template file (without .html extension)
        context: Dictionary of template variables
        
    Returns:
        str: The rendered template content
        
    Raises:
        ValueError: If template doesn't exist or can't be rendered
    """
    template_path = Path(__file__).parent.parent / "templates" / f"{template_name}.html"
    
    if not template_path.exists():
        raise ValueError(f"Template {template_name} not found at {template_path}")
    
    try:
        with open(template_path, "r") as f:
            template_content = f.read()
        
        # Simple template rendering
        rendered_content = template_content
        for key, value in context.items():
            placeholder = "{{ " + key + " }}"
            if placeholder not in rendered_content:
                raise ValueError(f"Template variable {key} not found in template {template_name}")
            rendered_content = rendered_content.replace(placeholder, str(value))
        
        return rendered_content
    except Exception as e:
        raise ValueError(f"Error rendering template {template_name}: {str(e)}")
```

### 5. Check for Email Deliverability Issues

**Actions:**
- Verify the sending domain's SPF, DKIM, and DMARC records
- Check if the sending domain or IP is on any blacklists
- Test sending to different email providers (Gmail, Outlook, etc.)
- Check spam folder for test emails

**Implementation:**
- Use external tools to verify domain configuration
- Implement a test script to send emails to various providers
- Document findings in a report

## Implementation Plan

1. **Phase 1: Diagnostics (1-2 days)**
   - Implement the test email endpoint
   - Enhance error logging in the email sending process
   - Test sending emails to different providers
   - Check SendGrid dashboard for any issues or rejections

2. **Phase 2: Fixes (1-2 days)**
   - Implement the identified fixes based on diagnostic results
   - Add retry mechanism for transient failures
   - Update email templates if needed
   - Configure proper domain authentication if missing

3. **Phase 3: Verification (1 day)**
   - Test the complete registration flow
   - Verify emails are being delivered to various providers
   - Monitor logs for any remaining issues
   - Document the solution and any configuration changes

## Potential Solutions

Based on common issues with email delivery, here are the most likely solutions:

1. **SendGrid API Key**: Generate a new API key and update the configuration
2. **Domain Authentication**: Properly configure SPF, DKIM, and DMARC records for the sending domain
3. **Error Handling**: Improve error handling and add retry logic for transient failures
4. **Alternative Email Provider**: If SendGrid issues persist, consider an alternative email provider
5. **Email Content**: Modify email content to reduce spam score (avoid spam trigger words, balance text/HTML ratio)

## Monitoring and Long-term Maintenance

1. Implement email sending metrics (success rate, delivery rate)
2. Set up alerts for email sending failures
3. Regularly review email deliverability reports
4. Keep SendGrid configuration and API keys up to date