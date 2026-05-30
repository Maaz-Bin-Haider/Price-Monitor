import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Environment, FileSystemLoader
import os

from config import settings


def _render_email_template(job, below_target: list[dict]) -> str:
    """Render the email_alert.html Jinja2 template."""
    templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
    env = Environment(loader=FileSystemLoader(templates_dir))
    template = env.get_template("email_alert.html")
    lowest = below_target[0] if below_target else {}
    return template.render(
        product_name=job.product_name,
        target_price=job.target_price,
        below_target=below_target,
        lowest_price=lowest.get("price"),
        lowest_site=lowest.get("site_name"),
        lowest_link=lowest.get("link"),
    )


async def _send_smtp(to_email: str, subject: str, html_body: str) -> bool:
    """Send via aiosmtplib STARTTLS."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.EMAIL_FROM,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
        )
        return True
    except Exception as e:
        print(f"[EMAIL] SMTP error: {e}")
        return False


async def _send_sendgrid(to_email: str, subject: str, html_body: str) -> bool:
    """Send via SendGrid SDK."""
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        message = Mail(
            from_email=settings.EMAIL_FROM,
            to_emails=to_email,
            subject=subject,
            html_content=html_body,
        )
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)
        return response.status_code == 202
    except Exception as e:
        print(f"[EMAIL] SendGrid error: {e}")
        return False


async def send_alert_email(job, below_target: list[dict]) -> bool:
    """
    Send price alert email using configured provider (SMTP or SendGrid).
    Returns True on success, False on failure. Never raises.
    """
    if not below_target:
        return False

    lowest = below_target[0]
    subject = f"Price Alert: {job.product_name} is available at {lowest.get('price')}"

    try:
        html_body = _render_email_template(job, below_target)
    except Exception as e:
        print(f"[EMAIL] Template render error: {e}")
        return False

    if settings.USE_SENDGRID:
        return await _send_sendgrid(job.user_email, subject, html_body)
    else:
        return await _send_smtp(job.user_email, subject, html_body)
