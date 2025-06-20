import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

class EmailSender:
    def __init__(self, sender_email: str, app_password: Optional[str] = None):
        self.sender_email = sender_email
        self.app_password = os.getenv("APP_PASSWORD")
        if not self.app_password:
            raise ValueError("App password not provided and APP_PASSWORD environment variable not set")

    def send_email(self, receiver_email: str, subject: str, body: str) -> bool:
        """
        Send an email using Gmail SMTP.
        
        Args:
            receiver_email: Email address of the recipient
            subject: Email subject
            body: Email body content
            
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        msg = MIMEMultipart()
        msg['From'] = self.sender_email
        msg['To'] = receiver_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        try:
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(self.sender_email, self.app_password)
            server.send_message(msg)
            server.quit()
            print("✅ Email sent successfully!")
            return True
        except smtplib.SMTPAuthenticationError:
            print("❌ Authentication failed. Please check your app password.")
            return False
        except smtplib.SMTPException as e:
            print(f"❌ SMTP error occurred: {e}")
            return False
        except Exception as e:
            print(f"❌ An unexpected error occurred: {e}")
            return False

def main():
    # Example usage
    sender = EmailSender("prashnotrika@gmail.com")
    success = sender.send_email(
        receiver_email="akdbgbr@gmail.com",
        subject="Your Question Paper is Ready",
        body="Hello, this is a test email sent from Python."
    )
    
    if not success:
        print("Failed to send email. Please check the error messages above.")

if __name__ == "__main__":
    main()
