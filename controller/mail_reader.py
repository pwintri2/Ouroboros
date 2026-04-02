import imaplib
import email
import requests

class WintripMail:
    def __init__(self):
        # Initialize an empty list to store unread emails
        self.unread_emails = []

    def fetch_unread_summaries(self, username, password):
        imap = imaplib.IMAP4_SSL('imap.gmail.com')
        imap.login(username, password)
        imap.select('inbox')
        status, messages = imap.search(None, 'UNSEEN')
        for num in messages[0].split():
            status, msg = imap.fetch(num, '(RFC822)')
            raw_email = msg[0][1]
            email_message = email.message_from_bytes(raw_email)
            sender = email_message['From']
            subject = email_message['Subject']
            self.unread_emails.append((sender, subject))
        imap.logout()

    def categorize_email(self, subject, sender):
        url = 'http://127.0.0.1:11434/api/generate'
        payload = {
            'model': 'llama3.1',
            'prompt': f'Categorize this email from {sender} with subject: {subject} as Invoice, Newsletter, or Personal. Return ONLY the category name.',
            'stream': False
        }
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, json=payload, headers=headers)
        category = response.json().get('response', '')
        return category
