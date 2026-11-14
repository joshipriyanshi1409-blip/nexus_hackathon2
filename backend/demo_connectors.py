"""Synthetic Gmail and Google Play records for an explicitly labelled demo.

These fixtures never contact Google services and are not real customer data.
They deliberately pass through the same feedback-cleaning and persistence path
as live connector imports.
"""
from datetime import datetime, timedelta, timezone


def demo_feedback_rows():
    now = datetime.now(timezone.utc)

    def stamp(days_ago):
        return (now - timedelta(days=days_ago)).isoformat()

    return [
        # Simulated Gmail support mailbox messages.
        {
            'source': 'Demo Gmail',
            'text': (
                'Subject: Payment deducted but order missing\n\n'
                'Hello support, my payment was deducted but I never received an '
                'order confirmation. Please help. You can reach me at '
                'demo.customer@example.com or +91 98765 43210.'
            ),
            'rating': 2, 'date': stamp(3),
            'external_id': 'demo_connector:gmail:message-001',
        },
        {
            'source': 'Demo Gmail',
            'text': 'Subject: App keeps closing\n\nThe app closes every time I open a product page. I cannot place my order.',
            'rating': 2, 'date': stamp(5),
            'external_id': 'demo_connector:gmail:message-002',
        },
        {
            'source': 'Demo Gmail',
            'text': 'Subject: Delivery tracking is stuck\n\nMy parcel is late and the tracking page has not updated for four days.',
            'rating': 2, 'date': stamp(8),
            'external_id': 'demo_connector:gmail:message-003',
        },
        {
            'source': 'Demo Gmail',
            'text': 'Subject: Refund not received\n\nMy return was approved, but the refund has not arrived in my account yet.',
            'rating': 2, 'date': stamp(11),
            'external_id': 'demo_connector:gmail:message-004',
        },
        {
            # Deliberate duplicate content with a different provider ID.
            'source': 'Demo Gmail',
            'text': 'Subject: Payment deducted but order missing\n\nHello support, my payment was deducted but I never received an order confirmation. Please help. You can reach me at demo.customer@example.com or +91 98765 43210.',
            'rating': 2, 'date': stamp(3),
            'external_id': 'demo_connector:gmail:message-005-duplicate',
        },

        # Simulated Google Play review records.
        {
            'source': 'Demo Google Play',
            'text': 'The app crashes on launch. I have to open it three or four times before it works.',
            'rating': 1, 'date': stamp(2),
            'external_id': 'demo_connector:play:review-001',
        },
        {
            'source': 'Demo Google Play',
            'text': 'Payment was deducted but I did not get an order confirmation. Very frustrating.',
            'rating': 1, 'date': stamp(4),
            'external_id': 'demo_connector:play:review-002',
        },
        {
            'source': 'Demo Google Play',
            'text': 'OTP takes too long to arrive. I cannot log in when I need to check my order.',
            'rating': 2, 'date': stamp(7),
            'external_id': 'demo_connector:play:review-003',
        },
        {
            'source': 'Demo Google Play',
            'text': 'Search freezes whenever I type more than a few letters. Please fix this bug.',
            'rating': 2, 'date': stamp(12),
            'external_id': 'demo_connector:play:review-004',
        },
        {
            # Deliberate duplicate content with a different review ID.
            'source': 'Demo Google Play',
            'text': 'The app crashes on launch. I have to open it three or four times before it works.',
            'rating': 1, 'date': stamp(2),
            'external_id': 'demo_connector:play:review-005-duplicate',
        },
    ]
