"""Synthetic customer-voice examples used for demos and offline evaluation.
These examples never create users or change permissions.
"""
COMPLAINTS = [
    ('payment', 'Google Play', 'Payment failed but my account was charged and the order was not confirmed. Contact me at demo.customer@example.com or +91 98765 43210.', 1, 3),
    ('payment', 'Support mailbox', 'Payment was deducted, but I never received an order confirmation.', 1, 7),
    ('payment', 'Website', 'The checkout payment went through but the order is still missing.', 1, 12),
    ('payment', 'Google Play', 'I was charged during checkout and no order confirmation appeared.', 1, 18),
    ('payment', 'Support mailbox', 'Payment was taken from my account, but the order was not created.', 1, 35),
    ('payment', 'Website', 'My payment was deducted and the order confirmation did not arrive.', 1, 45),
    ('delivery', 'Google Play', 'Delivery is late and the tracking status has not updated.', 2, 4),
    ('delivery', 'Support mailbox', 'Shipping is delayed and my tracking page is stuck.', 2, 34),
    ('delivery', 'Website', 'My package delivery is delayed and the expected date keeps changing.', 2, 39),
    ('delivery', 'Google Play', 'The order delivery arrived late after several tracking delays.', 2, 48),
    ('delivery', 'Support mailbox', 'Delivery tracking has not moved for days and my parcel is late.', 2, 55),
    ('app_crash', 'Google Play', 'The app crashes whenever I open the product page.', 1, 6),
    ('app_crash', 'Support mailbox', 'The application keeps crashing when I try to open a product.', 1, 15),
    ('app_crash', 'Website', 'App closes unexpectedly when I tap the checkout button.', 1, 37),
    ('app_crash', 'Google Play', 'The app crashes on launch and closes before I can sign in.', 1, 50),
]

APPROVED_FACTS = [
    {'name':'downtime','value':'0.1%','source_title':'ECHO demo: Product Specifications & Guarantees — derived from 99.9% uptime guarantee','source_url':''},
    {'name':'Hardware warranty','value':'1 year','source_title':'ECHO demo: Product Specifications & Guarantees','source_url':''},
    {'name':'refunds','value':'48 business hours','source_title':'ECHO demo: Product Specifications & Guarantees','source_url':''},
    {'name':'Founded','value':'2024','source_title':'ECHO demo: Market Position','source_url':''},
    {'name':'replacement warranty','value':'1 year','source_title':'ECHO demo: Product Specifications & Guarantees — standard hardware warranty','source_url':''},
    {'name':'Product price','value':'₹999','source_title':'ECHO demo catalogue — synthetic approved fact','source_url':''},
    {'name':'Launch date','value':'18 December 2026','source_title':'ECHO demo launch plan — synthetic approved fact','source_url':''},
    {'name':'Battery life','value':'24 hours','source_title':'ECHO demo product specification — synthetic approved fact','source_url':''},
]
