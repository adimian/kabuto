import smtplib
import email.utils
from email.mime.text import MIMEText
from flask import current_app, render_template

MAIL_SUBJECT = "An account has been made on kabuto. Please activate it."


def send_token(recipient, user, token, url_root):
    template = "register.html"
    send_mail(recipient, MAIL_SUBJECT, render_template(template,
                                                       root=url_root,
                                                       user=user,
                                                       token=token))


def send_mail(recipient, subject, content):
    author = current_app.config['MAIL_AUTHOR']
    sender = current_app.config['MAIL_SENDER_ADDRESS']
    sender_pw = current_app.config['MAIL_SENDER_PW']


    msg = MIMEText(content, 'html')
    msg.set_unixfrom(author)
    msg['To'] = email.utils.formataddr(('Recipient', recipient))
    msg['From'] = email.utils.formataddr((author, sender))
    msg['Subject'] = subject
    msg.add_header('reply-to', "info@adimian.com")

    server = smtplib.SMTP(current_app.config['SMTP_SERVER'],
                          current_app.config['SMTP_PORT'])
    try:
        server.set_debuglevel(True)
        server.ehlo()

        # If we can encrypt this session, do it
        if server.has_extn('STARTTLS'):
            server.starttls()
            server.ehlo()  # re-identify ourselves over TLS connection
        if sender and sender_pw:
            server.login(sender, sender_pw)
        server.sendmail(sender, [recipient], msg.as_string())
    finally:
        server.quit()
