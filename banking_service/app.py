# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify, render_template, send_from_directory, Response
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime, timedelta
import random
import os
import sys
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__, static_folder='.', template_folder='.')
CORS(app)

# Avoid Windows console encoding crashes from unicode log messages.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Email Config
SMTP_SERVER = "smtp.gmail.com"
FRAUD_API_URL = os.getenv("FRAUD_API_URL", "http://localhost:5001/analyze")
SMTP_PORT = 587
MAIL_USERNAME = "smaulik557@gmail.com"
MAIL_PASSWORD = "fpbx ebwd nqsq ifah"


def send_email(to_email, subject, body):
    try:
        msg = MIMEMultipart()
        msg['From'] = MAIL_USERNAME
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))  # HTML for better formatting

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        text = msg.as_string()
        server.sendmail(MAIL_USERNAME, to_email, text)
        server.quit()
        print(f"Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

# Error Handlers


@app.errorhandler(404)
def not_found(e):
    return send_from_directory('.', '404.html'), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500


@app.errorhandler(504)
def gateway_timeout(e):
    return send_from_directory('.', '504.html'), 504

# NEW MAPPED API URLS FOR CUSTOMER PORTAL
@app.route('/portal/transactions')
@app.route('/portal/profile')
@app.route('/portal/devices')
@app.route('/portal/security')
@app.route('/portal/analytics')
def render_customer_portal():
    return send_from_directory('.', 'customer-portal.html')


# Database Configuration
# Database Configuration (Dedicated Banking DB)
MONGO_URI = "mongodb+srv://mkbharvad8080:Mkb%408080@cluster0.a82h2.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client['banking_core_db']

transactions_coll = db['transactions']
customers_coll = db['customers']

# Optional/Supplemental Collections
alerts_coll = db['alerts']
audit_coll = db['audit_logs']
merchants_coll = db['merchants']
bank_accounts_coll = db['bank_accounts']
credit_cards_coll = db['credit_cards']
audit_coll = db['audit_logs']

# --- Helper Functions ---


def log_audit(user, action, target, details=""):
    audit_coll.insert_one({
        "timestamp": datetime.utcnow(),
        "user": user,
        "action": action,
        "target": target,
        "details": details
    })


def generate_account_number():
    """Generate unique 16-digit account number"""
    return f"{random.randint(1000000000000000, 9999999999999999)}"


def generate_merchant_id():
    """Generate unique merchant ID"""
    return f"MERCH-{random.randint(100000, 999999)}"

# --- PAYPAL WEBHOOK INTEGRATION ---


@app.route('/api/paypal/webhook', methods=['POST'])
def paypal_webhook():
    """
    PayPal sends transaction data here when payment happens
    Configure this URL in PayPal Developer Dashboard
    """
    try:
        data = request.json
        event_type = data.get('event_type')

        # Handle payment completion
        if event_type == 'PAYMENT.SALE.COMPLETED':
            payment_data = data.get('resource', {})

            # Extract transaction details
            txn_id = payment_data.get(
                'id', f"PP-{random.randint(100000, 999999)}")
            amount = float(payment_data.get('amount', {}).get('total', 0))
            currency = payment_data.get('amount', {}).get('currency', 'USD')
            payer_email = payment_data.get(
                'payer', {}).get('email_address', 'Unknown')

            # Calculate risk score via Microservice
            risk_score, reasoning, _ = calculate_risk_score({
                "amount": amount,
                "location": "PayPal",
                "customer": payer_email,
                "merchant": "PayPal"
            })

            # Save to database
            transaction = {
                "id": txn_id,
                "customer": payer_email,
                "amount": amount,
                "currency": currency,
                "location": "PayPal",
                "coords": [0, 0],
                "channel": "PayPal",
                "type": "Credit",
                "timestamp": datetime.utcnow(),
                "risk_score": risk_score,
                "ai_reason": reasoning,
                "status": "Blocked" if risk_score > 85 else ("Review" if risk_score > 60 else "Approved")
            }
            transactions_coll.insert_one(transaction)

            # Update customer profile
            customers_coll.update_one(
                {"email": payer_email},
                {"$inc": {"txn_count": 1, "total_spent": amount}, "$set": {
                    "last_txn": datetime.utcnow(), "risk_score": risk_score}},
                upsert=True
            )

            log_audit(
                "PayPal", f"Transaction: {txn_id}", "PayPal", f"{amount} {currency}")
            return jsonify({"success": True})

        return jsonify({"success": True, "message": "Event received"})
    except Exception as e:
        print(f"PayPal Error: {e}")
        return jsonify({"error": str(e)}), 500

# --- AUTH ENDPOINTS WITH OTP ---


@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    email = data.get('email')
    role = data.get('role', 'Customer')

    # Check if user already exists
    if db['users'].find_one({"email": email}):
        return jsonify({"success": False, "message": "User already exists"})

    user = {
        "name": data.get('name'),
        "email": email,
        "phone": data.get('phone'),
        "password": data.get('password'),
        "role": role,
        "created_at": datetime.utcnow(),
        "status": "Active"
    }
    db['users'].insert_one(user)

    # --- Role Specific Logic ---
    if role == 'Merchant':
        # Generate Merchant Credentials
        merchant_id = generate_merchant_id()
        account_number = generate_account_number()

        merchant_record = {
            "merchant_id": merchant_id,
            "business_name": data.get('name'),
            "email": email,
            "account_number": account_number,
            "status": "Active",
            "created_at": datetime.utcnow(),
            "total_revenue": 0
        }
        merchants_coll.insert_one(merchant_record)

        # Send Merchant Welcome Email
        email_body = f"""
        <h3>Welcome to Swift Bank!</h3>
        <p>Hello {data.get('name')},</p>
        <p>Your merchant account has been successfully created.</p>
        <p><strong>Merchant ID:</strong> {merchant_id}</p>
        <p><strong>Account Number:</strong> {account_number}</p>
        <p>You can now login to your dashboard and start accepting payments.</p>
        """
        send_email(email, "Merchant Registration Successful", email_body)

    elif role == 'Customer':
        # Ensure Customer Profile Exists
        customer_record = {
            "name": data.get('name'),
            "email": email,
            "account_number": generate_account_number(),
            "balance": 1000,  # Initial Balance
            "txn_count": 0,
            "total_spent": 0,
            "risk_score": 0,
            "created_at": datetime.utcnow(),
            "status": "Active"
        }
        customers_coll.insert_one(customer_record)

        # Send Customer Welcome Email
        email_body = f"""
        <h3>Welcome to Swift Bank!</h3>
        <p>Hello {data.get('name')},</p>
        <p>Your account has been successfully created as <strong>{role}</strong>.</p>
        <p>Please login and link your credit card to start making payments.</p>
        """
        send_email(email, "Welcome to Swift Bank Platform", email_body)

    log_audit(
        "System", f"New User Registered: {email} ({role})", "Auth", "Register")
    return jsonify({"success": True, "message": "Registration successful"})


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    # Merchants don't have passwords in this simple flow, or we assume they do?
    password = data.get('password')
    # Actually, for this demo, merchants might not have passwords set up in 'register_merchant'.
    # Let's check: register_merchant creates a merchant object but NO PASSWORD field.
    # To fix this elegantly for the user without complex auth:
    # We will allow merchants to login just by Email for this demo (or assume a default password if needed).
    # OR, better: Check if it's a merchant, if so, generate OTP directly without password check (simulating "Login with OTP").

    # 1. Check User (Customer/Admin) with Password
    user = db['users'].find_one({"email": email})
    if user:
        if user.get('password') == password:
            # Valid User
            pass
        else:
            return jsonify({"success": False, "message": "Invalid credentials"})
    else:
        # 2. Check Merchant (No password required for this demo flow, just email)
        merchant = merchants_coll.find_one({"email": email})
        if merchant:
            user = merchant  # Treat merchant as user for OTP step
        else:
            return jsonify({"success": False, "message": "User not found"})

    # Generate 6-digit OTP
    otp = str(random.randint(100000, 999999))

    # Store OTP with expiry (5 mins)
    db['otps'].update_one(
        {"email": email},
        {"$set": {"otp": otp, "expires_at": datetime.utcnow() + timedelta(minutes=5)}},
        upsert=True
    )

    # Send OTP Code (Email or Console)
    print(f"🔐 LOGIN OTP for {email}: {otp}")
    send_email(email, "Your Login OTP", f"Your OTP is: <b>{otp}</b>")

    return jsonify({"success": True, "message": "OTP sent to email", "require_otp": True})


@app.route('/api/auth/verify-otp', methods=['POST'])
def verify_otp():
    data = request.json
    email = data.get('email')
    otp = data.get('otp')

    record = db['otps'].find_one({"email": email})

    if record and record['otp'] == otp:
        # Check expiry
        if datetime.utcnow() > record['expires_at']:
            return jsonify({"success": False, "message": "OTP expired"})

        # Determine User Role & Name
        user = db['users'].find_one({"email": email})
        merchant = merchants_coll.find_one({"email": email})

        user_data = {}
        if user:
            user_data = {
                "name": user['name'],
                "email": user['email'],
                "role": user.get('role', 'Customer')
            }
        elif merchant:
            user_data = {
                "name": merchant['business_name'],
                "email": merchant['email'],
                "role": 'Merchant'
            }

        # Clear OTP
        db['otps'].delete_one({"email": email})

        # Add $5000 demo balance on login
        customers_coll.update_one({"email": email}, {"$inc": {"balance": 5000}})

        log_audit(email, "Login Successful", "Auth", "Login")
        return jsonify({"success": True, "user": user_data})

    return jsonify({"success": False, "message": "Invalid OTP"})


@app.route('/api/auth/forgot-password', methods=['POST'])
def forgot_password():
    data = request.json
    email = data.get('email')

    user = db['users'].find_one({"email": email})
    if not user:
        # Security: Return success even if user not found to prevent enumeration
        return jsonify({"success": True, "message": "If an account exists, a reset link has been sent."})

    # Generate Token
    import uuid
    token = str(uuid.uuid4())

    # Store Token
    db['users'].update_one(
        {"email": email},
        {"$set": {
            "reset_token": token,
            "reset_token_expires": datetime.utcnow() + timedelta(hours=1)
        }}
    )

    # Construct Link
    reset_link = f"http://localhost:5000/reset-password.html?token={token}"

    # LOG TO CONSOLE (Simulation)
    print("\n" + "="*50)
    print(f"📧 PASSWORD RESET EMAIL SIMULATION")
    print(f"To: {email}")
    print(f"Link: {reset_link}")
    print("="*50 + "\n")

    # Attempt to send real email if configured
    email_body = f"""
    <h3>Password Reset Request</h3>
    <p>Click the link below to reset your password:</p>
    <p><a href="{reset_link}">Reset Password</a></p>
    <p>If you did not request this, please ignore this email.</p>
    """
    send_email(email, "Password Reset Request", email_body)

    return jsonify({"success": True, "message": "Reset link sent"})


@app.route('/api/auth/reset-password', methods=['POST'])
def reset_password():
    data = request.json
    token = data.get('token')
    new_password = data.get('password')

    user = db['users'].find_one({
        "reset_token": token,
        "reset_token_expires": {"$gt": datetime.utcnow()}  # Check not expired
    })

    if not user:
        return jsonify({"success": False, "message": "Invalid or expired token"})

    # Update Password and Clear Token
    db['users'].update_one(
        {"_id": user['_id']},
        {
            "$set": {"password": new_password},
            "$unset": {"reset_token": "", "reset_token_expires": ""}
        }
    )

    log_audit(user['email'], "Password Reset Successfully", "Auth", "Reset")
    return jsonify({"success": True, "message": "Password updated successfully"})


@app.route('/api/auth/resend-otp', methods=['POST'])
def resend_otp():
    data = request.json
    email = data.get('email')

    user = db['users'].find_one({"email": email})
    if not user:
        return jsonify({"success": False, "message": "User not found"})

    # Generate new OTP
    otp = str(random.randint(100000, 999999))

    db['otps'].insert_one({
        "email": email,
        "otp": otp,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(minutes=5)
    })

    email_body = f"""
    <h3>Your New Login OTP</h3>
    <p>Your OTP is: <strong style="font-size:24px; color:#dc3545;">{otp}</strong></p>
    <p>Valid for 5 minutes.</p>
    """
    send_email(email, f"Swift Bank OTP Resent: {otp}", email_body)

    return jsonify({"success": True, "message": "OTP resent"})


# --- PROFILE MANAGEMENT ---
@app.route('/api/profile', methods=['GET', 'POST'])
def manage_profile():
    # For simulation, default to Admin or use query param
    email = request.args.get('email', "admin@swiftai.com")

    if request.method == 'POST':
        data = request.json
        # Allow updating email context if needed
        email = data.get('email', email)

        update_fields = {
            "name": data.get('name'),
            "phone": data.get('phone'),
            "location": data.get('location', 'Headquarters, Silicon Valley, CA'),
            "updated_at": datetime.utcnow()
        }

        result = db['users'].update_one(
            {"email": email}, {"$set": update_fields}, upsert=True)
        log_audit(email, "Updated Profile", "Profile",
                  "User updated personal details")
        return jsonify({"success": True, "message": "Profile updated successfully"})

    user = db['users'].find_one({"email": email})
    if not user:
        # Create default admin if missing
        user = {
            "name": "Admin User",
            "email": email,
            "role": "Super Admin",
            "phone": "+1 (555) 000-1234",
            "location": "Headquarters, Silicon Valley, CA",
            "created_at": datetime.utcnow()
        }
        db['users'].insert_one(user)

    user['_id'] = str(user['_id'])
    return jsonify(user)

# --- BANK PORTAL ENDPOINTS ---


@app.route('/api/kyc/verify', methods=['POST'])
def verify_kyc():
    data = request.json
    name = data.get('name')
    # Simple logic for simulation: "Unknown" or "Hidden" triggers fraud
    is_fraud = "Unknown" in name or "Hidden" in data.get('country', '')

    status = "Failed" if is_fraud else "Verified"

    # Store record
    db['kyc_records'].insert_one({
        "name": name,
        "country": data.get('country'),
        "status": status,
        "timestamp": datetime.utcnow()
    })

    if status == "Failed":
        # Alert Admin
        send_email(MAIL_USERNAME, "CRITICAL: KYC Alert",
                   f"High Risk KYC Detected: {name}. System blocked verification.")

    return jsonify({
        "status": status,
        "details": {"document_check": "Forged" if is_fraud else "Valid"}
    })

# --- AI CHATBOT ENDPOINT ---


@app.route('/api/chat', methods=['POST'])
def ai_chat():
    data = request.json
    msg = data.get('message', '').lower()

    response_text = "I didn't understand that. Try asking about 'stats', 'blocked transactions', or a 'customer'."

    try:
        if 'hello' in msg or 'hi' in msg:
            response_text = "Hello! I am Swift Assist. I can help you analyze fraud data. Try asking 'Show me today's stats'."

        elif 'stat' in msg or 'overview' in msg:
            total = db['transactions'].count_documents({})
            blocked = db['transactions'].count_documents({"status": "Blocked"})
            response_text = f"Currently, we have processed {total} transactions. {blocked} have been blocked as fraudulent."

        elif 'blocked' in msg:
            recent_blocked = list(db['transactions'].find(
                {"status": "Blocked"}).sort("timestamp", -1).limit(3))
            if recent_blocked:
                details = ", ".join(
                    [f"{t.get('customer', 'Unknown')} (${t.get('amount')})" for t in recent_blocked])
                response_text = f"The last 3 blocked transactions were: {details}."
            else:
                response_text = "No blocked transactions found recently."

        elif 'customer' in msg or 'check' in msg:
            # Simple simulation: Extract name if possible, or just give general info
            response_text = "To check a specific customer, please visit the Customers page or provide an ID. I can tell you that we have " + \
                str(db['customers'].count_documents({})) + " active profiles."

        elif 'alert' in msg:
            pending = db['alerts'].count_documents({"status": "Pending"})
            response_text = f"There are currently {pending} pending alerts requiring your attention."

        elif 'risk' in msg:
            response_text = "Global Risk Level is currently MODERATE based on recent velocity checks."

    except Exception as e:
        response_text = "I encountered an error accessing the database."

    return jsonify({"response": response_text})


def calculate_risk_score(txn):
    """
    Delegate risk calculation to the external Fraud Detection Service.
    Now constructs a rich 'Vesta-compatible' payload using feature importance fields.
    """
    try:
        # 1. Fetch Historical Data & Context for Feature Engineering
        customer_email = txn.get('customer') or txn.get('from_email')

        # Default Aggregates
        c1_count = 1  # Txn Count
        d1_days = 0  # Days since account created
        d2_days = 0  # Days since last txn

        if customer_email:
            # Fetch Customer Profile for Account Age (D1)
            customer = customers_coll.find_one({"email": customer_email})
            current_balance = 0
            if customer:
                current_balance = customer.get('balance', 0)
                created_at = customer.get('created_at')
                if created_at:
                    # Handle string vs datetime
                    if isinstance(created_at, str):
                        try:
                            created_at = datetime.fromisoformat(created_at)
                        except:
                            created_at = datetime.utcnow()
                    d1_days = (datetime.utcnow() - created_at).days

            # Fetch Transaction History for Counts (C Columns) & Velocities
            # C1: Total transactions for this customer
            c1_count = transactions_coll.count_documents(
                {"from_email": customer_email}) + 1

            # Additional Stats for "Complete View"
            pipeline = [
                {"$match": {"from_email": customer_email}},
                {"$group": {
                    "_id": None,
                    "total_spend": {"$sum": "$amount"},
                    "avg_spend": {"$avg": "$amount"}
                }}
            ]
            agg = list(transactions_coll.aggregate(pipeline))
            total_spend = agg[0]['total_spend'] if agg else 0
            avg_spend = agg[0]['avg_spend'] if agg else 0

            # Linked Cards
            linked_cards_count = db['credit_cards'].count_documents(
                {"user_email": customer_email})

            # C2: Transactions today (Velocity)
            start_of_day = datetime.utcnow().replace(
                hour=0, minute=0, second=0, microsecond=0)
            c2_count = transactions_coll.count_documents({
                "from_email": customer_email,
                "timestamp": {"$gte": start_of_day}
            }) + 1

            # D2: Days since last transaction
            last_txn = transactions_coll.find_one(
                {"from_email": customer_email},
                sort=[("timestamp", -1)]
            )
            if last_txn and last_txn.get('timestamp'):
                last_ts = last_txn['timestamp']
                d2_days = (datetime.utcnow() - last_ts).days
        else:
            c2_count = 1
            total_spend = 0
            avg_spend = 0
            linked_cards_count = 0
            current_balance = 0

        # 2. Map Banking Data to New Model Schema
        # The new model expects: amt, category, city, state, lat, long, timestamp

        # Location Parsing
        location_raw = txn.get('location', {})
        location_data = {}

        if isinstance(location_raw, dict):
            location_data = location_raw
        else:
            # Parse string "City, State" or just "City"
            parts = str(location_raw).split(',')
            location_data['city'] = parts[0].strip()
            if len(parts) > 1:
                # Using country as state proxy
                location_data['country'] = parts[1].strip()

        timestamp_str = datetime.utcnow().isoformat()

        payload = {
            # Core Fields for New ML Model
            "amount": float(txn.get('amount', 0)),
            "category": txn.get('category', 'misc_net'),
            "location": location_data,  # Use the object
            "timestamp": timestamp_str,

            # Identity / Enrichment (Optional but good for fallback)
            "customer": customer_email,
            "ip_address": txn.get('ip_address', 'Unknown'),
            "device_type": txn.get('device_type', 'Unknown'),
            "browser": txn.get('browser', 'Unknown'),
            "os": txn.get('os', 'Unknown'),
            "country": location_data.get('country', txn.get('country', 'Unknown')),
            "latitude": txn.get('latitude', location_data.get('latitude', 0)),
            "longitude": txn.get('longitude', location_data.get('longitude', 0)),

            # Legacy/Derived Context (Still useful for rules)
            "account_age_days": d1_days,
            "txn_velocity_24h": c2_count,

            # DEEP INSIGHTS (Requested by User)
            "total_spend_lifetime": total_spend,
            "avg_transaction_val": avg_spend,
            "linked_cards": linked_cards_count,
            "current_balance": current_balance
        }

        print(f"Sending Payload to Fraud Service: {payload}")

        try:
            response = requests.post(FRAUD_API_URL, json=payload, timeout=5.0)
            if response.status_code == 200:
                result = response.json()
                return result.get('risk_score', 0), result.get('reasons', []), result
            else:
                print(f"Fraud Service Error: {response.status_code}")
                return 0, ["Service Error"], {}
        except Exception as e:
            print(f"Fraud Service Exception: {e}")
            return 0, ["Connection Failed"], {}

    except Exception as e:
        print(f"Risk Calculation Error: {e}")
        return 0, ["Internal Error"], {}


# Location to Coordinates Mapping
LOCATION_MAP = {
    "Mumbai, IN": [19.0760, 72.8777],
    "New York, US": [40.7128, -74.0060],
    "London, UK": [51.5074, -0.1278],
    "Dubai, UAE": [25.2048, 55.2708],
    "Lagos, Nigeria": [6.5244, 3.3792],
    "Tokyo, Japan": [35.6762, 139.6503],
    "High Risk Zone": [34.5553, 69.2075]  # Kabul (example)
}

# --- Routes ---
# --- Frontend Routes (Clean URLs) ---


@app.route('/')
def home():
    return send_from_directory('.', 'bank-portal.html')


@app.route('/<path:path>')
def serve_page(path):
    # Try directory/file as is first (for images, styles etc)
    if os.path.exists(path) and not os.path.isdir(path):
        return send_from_directory('.', path)

    # Try adding .html for clean URLs
    html_path = f"{path}.html"
    if os.path.exists(html_path):
        return send_from_directory('.', html_path)

    # Default to 404
    return send_from_directory('.', '404.html'), 404


@app.route('/api/transactions/<txn_id>', methods=['GET'])
def get_transaction(txn_id):
    txn = transactions_coll.find_one({"id": txn_id})
    if txn:
        txn['_id'] = str(txn['_id'])
        return jsonify(txn)
    return jsonify({"error": "Transaction not found"}), 404

# 1. Transactions & Simulation


@app.route('/api/transactions', methods=['GET'])
def manage_transactions():
    # GET with Filters
    status = request.args.get('status')
    customer = request.args.get('customer')

    query = {}

    # Build customer filter
    if customer:
        customer_filter = {
            '$or': [
                {'customer': customer},
                {'from_email': customer},
                {'user_email': customer}
            ]
        }
        query.update(customer_filter)

    # Add status filter if specified
    if status and status != 'All':
        query['status'] = status

    print(f"[API] Transaction query: {query}")  # Debug log
    txns = list(transactions_coll.find(query).sort(
        "timestamp", -1).limit(100))  # Increased limit
    for t in txns:
        t['_id'] = str(t['_id'])

    print(f"[API] Found {len(txns)} transactions")  # Debug log
    return jsonify(txns)

# Customer Profile Management


@app.route('/api/profile/password', methods=['POST'])
def change_password():
    data = request.json
    email = data.get('email')
    current_password = data.get('current_password')
    new_password = data.get('new_password')

    if not email:
        return jsonify({"success": False, "message": "Email is required"}), 400

    # Retrieve user (from customers collection primarily for banking)
    # Using 'customers' since 'users' is for admin/fraud service mostly
    result = customers_coll.update_one(
        {"email": email},
        {"$set": {
            "password": new_password,  # In prod, hash this!
            "password_updated_at": datetime.utcnow()
        }}
    )

    if result.matched_count == 0:
        return jsonify({"success": False, "message": "User not found"}), 404

    log_audit(email, "Changed Password", "Security", "Password updated")
    return jsonify({"success": True, "message": "Password changed successfully"})


# 19. User Management with Invitations

# 20. File Upload Handler
@app.route('/uploads/<filename>')
def serve_upload(filename):
    return send_from_directory('uploads', filename)

# 21. Transaction Actions (Approve/Block/Review)


@app.route('/api/transactions/<txn_id>/approve', methods=['POST'])
def approve_transaction(txn_id):
    transactions_coll.update_one(
        {"id": txn_id}, {"$set": {"status": "Approved"}})
    log_audit(
        "Admin", f"Approved Transaction: {txn_id}", "Transactions", "Approved")
    return jsonify({"success": True, "message": "Transaction approved"})


@app.route('/api/transactions/<txn_id>/block', methods=['POST'])
def block_transaction(txn_id):
    transactions_coll.update_one(
        {"id": txn_id}, {"$set": {"status": "Blocked"}})
    log_audit(
        "Admin", f"Blocked Transaction: {txn_id}", "Transactions", "Blocked")
    return jsonify({"success": True, "message": "Transaction blocked"})


@app.route('/api/transactions/<txn_id>/review', methods=['POST'])
def review_transaction(txn_id):
    transactions_coll.update_one(
        {"id": txn_id}, {"$set": {"status": "Review"}})
    log_audit(
        "Admin", f"Sent Transaction to Review: {txn_id}", "Transactions", "Review")
    return jsonify({"success": True, "message": "Transaction sent to review"})

# 22. Customer Detail & Management


@app.route('/api/customers/<customer_id>', methods=['GET', 'PUT'])
def manage_customer_detail(customer_id):
    if request.method == 'GET':
        # Search by Email OR Name
        customer = customers_coll.find_one(
            {"$or": [{"email": customer_id}, {"name": customer_id}]})
        if not customer:
            # Create persistent profile for new user so data can be saved/updated
            is_email = '@' in customer_id
            new_profile = {
                "account_number": generate_account_number(),
                "name": customer_id.split('@')[0] if is_email else customer_id,
                "email": customer_id if is_email else "",
                "phone": "",
                "txn_count": 0,
                "total_spent": 0,
                "risk_score": 0,
                "balance": 1000,  # Initial balance for testing
                "created_at": datetime.utcnow(),
                "status": "Active"
            }
            customers_coll.insert_one(new_profile)
            new_profile['_id'] = str(new_profile['_id'])
            return jsonify(new_profile)

        # Auto-generate account number for existing customers who don't have one
        if not customer.get('account_number'):
            account_num = generate_account_number()
            customers_coll.update_one(
                {"_id": customer['_id']},
                {"$set": {"account_number": account_num}}
            )
            customer['account_number'] = account_num

        customer['_id'] = str(customer['_id'])
        return jsonify(customer)

    # UPDATE
    data = request.json
    customers_coll.update_one(
        {"$or": [{"email": customer_id}, {"name": customer_id}]},
        {"$set": {
            # Ensure name is set if updating
            "name": data.get('name', customer_id),
            "phone": data.get('phone'),
            "updated_at": datetime.utcnow()
        }},
        upsert=True  # Create if doesn't exist to ensure profile availability
    )
    log_audit(
        "Admin", f"Updated Customer: {customer_id}", "Customers", "Modified")
    return jsonify({"success": True, "message": "Customer updated"})


@app.route('/api/customers/<customer_id>/transactions', methods=['GET'])
def get_customer_transactions(customer_id):
    query = {"$or": [{"customer": customer_id}, {
        "from_email": customer_id}, {"user_email": customer_id}]}
    txns = list(transactions_coll.find(query).sort("timestamp", -1).limit(50))
    for t in txns:
        t['_id'] = str(t['_id'])
    return jsonify(txns)


@app.route('/api/customers/<customer_id>/alerts', methods=['GET'])
def get_customer_alerts(customer_id):
    alerts = list(alerts_coll.find(
        {"customer": customer_id}).sort("timestamp", -1).limit(20))
    for a in alerts:
        a['_id'] = str(a['_id'])
    return jsonify(alerts)


@app.route('/api/customers/<customer_id>/block', methods=['POST'])
def block_customer(customer_id):
    customers_coll.update_one({"name": customer_id}, {
                              "$set": {"status": "Blocked"}})
    log_audit(
        "Admin", f"Blocked Customer: {customer_id}", "Customers", "Blocked")
    return jsonify({"success": True, "message": "Customer blocked"})

# 23. Alert Detail & Actions


@app.route('/api/alerts/<alert_id>', methods=['GET', 'PUT'])
def manage_alert_detail(alert_id):
    from bson import ObjectId

    if request.method == 'GET':
        alert = alerts_coll.find_one({"_id": ObjectId(alert_id)})
        if not alert:
            return jsonify({"error": "Alert not found"}), 404
        alert['_id'] = str(alert['_id'])
        return jsonify(alert)

    # UPDATE
    data = request.json
    alerts_coll.update_one(
        {"_id": ObjectId(alert_id)},
        {"$set": {
            "status": data.get('status'),
            "notes": data.get('notes'),
            "updated_at": datetime.utcnow()
        }}
    )
    log_audit("Admin", f"Updated Alert: {alert_id}", "Alerts", "Modified")
    return jsonify({"success": True, "message": "Alert updated"})


@app.route('/api/alerts/<alert_id>/escalate', methods=['POST'])
def escalate_alert(alert_id):
    from bson import ObjectId
    alerts_coll.update_one(
        {"_id": ObjectId(alert_id)},
        {"$set": {"severity": "Critical", "escalated": True,
                  "escalated_at": datetime.utcnow()}}
    )
    log_audit("Admin", f"Escalated Alert: {alert_id}", "Alerts", "Escalated")
    return jsonify({"success": True, "message": "Alert escalated"})


@app.route('/api/alerts/<alert_id>/assign', methods=['POST'])
def assign_alert(alert_id):
    from bson import ObjectId
    data = request.json
    alerts_coll.update_one(
        {"_id": ObjectId(alert_id)},
        {"$set": {"assigned_to": data.get(
            'user_id'), "assigned_at": datetime.utcnow()}}
    )
    log_audit(
        "Admin", f"Assigned Alert: {alert_id} to {data.get('user_id')}", "Alerts", "Assigned")
    return jsonify({"success": True, "message": "Alert assigned"})


# --- MERCHANT MANAGEMENT ENDPOINTS ---
@app.route('/api/merchants/register', methods=['POST'])
def register_merchant():
    data = request.json

    # Check if merchant already exists
    if merchants_coll.find_one({"email": data.get('email')}):
        return jsonify({"success": False, "message": "Merchant already registered"})

    # Generate API key
    import secrets
    api_key = f"sk_live_{secrets.token_urlsafe(32)}"
    merchant_id = generate_merchant_id()

    merchant = {
        "merchant_id": merchant_id,
        "business_name": data.get('business_name'),
        "business_type": data.get('business_type'),
        "email": data.get('email'),
        "phone": data.get('phone'),
        "address": data.get('address'),
        "website": data.get('website'),
        "paypal_email": data.get('paypal_email'),
        "expected_volume": data.get('expected_volume'),
        "description": data.get('description'),
        "api_key": api_key,
        "status": "Active",
        "created_at": datetime.utcnow(),
        "total_sales": 0,
        "approved_count": 0,
        "blocked_count": 0,
        "fraud_prevented_amount": 0
    }

    merchants_coll.insert_one(merchant)

    # Send welcome email
    email_body = f"""
    <h3>Welcome to Swift Bank!</h3>
    <p>Hello {merchant['business_name']},</p>
    <p>Your merchant account has been successfully created.</p>
    <p><strong>Merchant ID:</strong> {merchant_id}</p>
    <p><strong>API Key:</strong> {api_key}</p>
    <p>Keep your API key secure. You'll need it for integration.</p>
    """
    send_email(data.get('email'), "Welcome to Swift Bank", email_body)

    log_audit(
        "System", f"Merchant Registered: {merchant_id}", "Merchant", merchant['business_name'])
    return jsonify({"success": True, "merchant_id": merchant_id, "api_key": api_key})


@app.route('/api/merchants/<merchant_id>', methods=['GET'])
def get_merchant(merchant_id):
    merchant = merchants_coll.find_one({"merchant_id": merchant_id})
    if merchant:
        merchant['_id'] = str(merchant['_id'])
        return jsonify(merchant)
    return jsonify({"error": "Merchant not found"}), 404


@app.route('/api/merchants/<merchant_id>/transactions', methods=['GET'])
def get_merchant_transactions(merchant_id):
    txns = list(transactions_coll.find(
        {"merchant_id": merchant_id}).sort("timestamp", -1).limit(50))
    for t in txns:
        t['_id'] = str(t['_id'])
    return jsonify(txns)


@app.route('/api/merchants/email/<email>', methods=['GET'])
def get_merchant_by_email(email):
    merchant = merchants_coll.find_one({"email": email})
    if merchant:
        merchant['_id'] = str(merchant['_id'])
        return jsonify(merchant)
    return jsonify({"error": "Merchant not found"}), 404


@app.route('/api/merchants/search', methods=['GET'])
def search_merchants():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])

    # Case-insensitive search for business name
    merchants = list(merchants_coll.find(
        {"business_name": {"$regex": query, "$options": "i"}},
        {"_id": 0, "business_name": 1, "email": 1,
            "merchant_id": 1, "account_number": 1}
    ).limit(10))

    return jsonify(merchants)


# --- BANK ACCOUNT SYSTEM ---
@app.route('/api/bank/create-account', methods=['POST'])
def create_bank_account():
    data = request.json
    email = data.get('email')
    user_type = data.get('user_type', 'Customer')
    initial_balance = float(data.get('initial_balance', 10000))

    # Check if account already exists
    existing = bank_accounts_coll.find_one({"user_email": email})
    if existing:
        return jsonify({"success": False, "message": "Account already exists"})

    # Generate account number
    account_number = f"{random.randint(1000000000, 9999999999)}"

    account = {
        "account_id": f"ACC-{random.randint(100000, 999999)}",
        "user_email": email,
        "user_type": user_type,
        "account_number": account_number,
        "ifsc_code": "SWIFT0001",
        "balance": initial_balance,
        "currency": "USD",
        "status": "Active",
        "created_at": datetime.utcnow(),
        "last_updated": datetime.utcnow()
    }

    bank_accounts_coll.insert_one(account)
    log_audit(email, "Bank Account Created",
              "Bank", f"Account: {account_number}")

    return jsonify({"success": True, "account_number": account_number, "balance": initial_balance})


@app.route('/api/bank/account/<email>', methods=['GET'])
def get_bank_account(email):
    # 1. Check dedicated bank accounts collection
    account = bank_accounts_coll.find_one({"user_email": email})
    if account:
        account['_id'] = str(account['_id'])
        return jsonify(account)

    # 2. Check Merchant Profile
    merchant = merchants_coll.find_one({"email": email})
    if merchant:
        return jsonify({
            "account_number": merchant.get('account_number'),
            "balance": merchant.get('total_revenue', 0),
            "status": "Active",
            "type": "Merchant"
        })

    # 3. Check Customer Profile
    customer = customers_coll.find_one({"email": email})
    if customer:
        return jsonify({
            "account_number": customer.get('account_number'),
            "balance": customer.get('balance', 0),
            "status": "Active",
            "type": "Customer"
        })

    return jsonify({"error": "Account not found"}), 404


@app.route('/api/bank/transfer', methods=['POST'])
def bank_transfer():
    """
    Process payment from Credit Card → Merchant (or User)
    Enhanced with IP, location, device, and session tracking
    """
    data = request.json

    from_email = data.get('from_email')
    to_email = data.get('to_email')
    amount = float(data.get('amount', 0))
    category = data.get('category', 'Other')
    description = data.get('description', '')

    # Enhanced data
    card_id = data.get('card_id')
    card_type = data.get('card_type', 'Unknown')
    last_4 = data.get('last_4', 'XXXX')
    ip_address = data.get('ip_address', request.remote_addr)
    location = data.get('location', {})
    device = data.get('device', {})
    session = data.get('session', {})

    # 1. Verify Sender (Credit Card OR Debit Card)
    is_debit = card_id == 'DEBIT_CARD'
    card = None

    if is_debit:
        # Check Customer Balance logic
        customer = customers_coll.find_one({"email": from_email})
        if not customer:
            return jsonify({"success": False, "message": "Customer account not found"}), 404

        current_balance = customer.get('balance', 0)
        card_type = "Debit Card"
        last_4 = customer.get('account_number', '0000')[-4:]

        if current_balance < amount:
            # REPORT TO FRAUD SERVICE
            print(
                f"[PAYMENT] ❌ Insufficient funds (Debit). Reporting to Fraud Service...")
            calculate_risk_score({  # Result discarded intentionally (fire-and-forget logging)
                "id": f"FAIL-{random.randint(100000, 999999)}",
                "amount": amount,
                "merchant": to_email,
                "customer": from_email,
                "type": "Insufficient Funds",
                "status": "Blocked",
                "location": location.get('city', 'Unknown'),
                "ip_address": ip_address,
                "device_type": device.get('type', 'Unknown'),
                "reasons": ["Insufficient funds", "Potential high-value fraud attempt"]
            })
            # Return as BLOCKED so frontend shows the Red Blocked UI
            blocked_txn_id = f"BLK-{random.randint(100000, 999999)}"
            transactions_coll.insert_one({
                "transaction_id": blocked_txn_id,
                "from_email": from_email,
                "to_email": to_email,
                "amount": amount,
                "currency": "USD",
                "category": category,
                "description": f"Failed Transfer: {description}",
                "location": location.get('city', 'Online'),
                "ip_address": ip_address,
                "device": {"type": device.get('type', 'Unknown')},
                "fraud_check": {
                    "status": "BLOCKED",
                    "risk_score": 0,
                    "reasons": ["Insufficient funds (Debit)"],
                    "checked_at": datetime.utcnow()
                },
                "status": "BLOCKED",
                "timestamp": datetime.utcnow()
            })

            return jsonify({
                "success": False,
                "status": "BLOCKED",
                "risk_score": 0,
                "decision": "Transaction blocked: Insufficient Funds",
                "reasons": ["Insufficient funds in account/card.", "Debit account balance too low."],
                "transaction_id": blocked_txn_id
            })

    else:
        # Credit Card Logic
        card = credit_cards_coll.find_one(
            {"card_id": card_id}) if card_id else credit_cards_coll.find_one({"user_email": from_email})
        if not card:
            return jsonify({"success": False, "message": "No linked credit card found. Please link a card."}), 400

        # 1.1 Check Credit Limit (Mock Check)
        limit = card.get('limit', 5000.0)
        spent = card.get('current_spent', 0.0)
        if spent + amount > limit:
            # REPORT TO FRAUD SERVICE
            print(f"[PAYMENT] ❌ Insufficient funds. Reporting to Fraud Service...")
            score, reasons, raw_json = calculate_risk_score({
                "id": f"FAIL-{random.randint(100000, 999999)}",
                "amount": amount,
                "merchant": to_email,
                "customer": from_email,
                "type": "Insufficient Funds",
                "status": "Blocked",
                "location": location.get('city', 'Unknown'),
                "ip_address": ip_address,
                "device_type": device.get('type', 'Unknown'),
                "reasons": ["Insufficient funds", "Potential high-value fraud attempt"]
            })
            # Return as BLOCKED so frontend shows the Red Blocked UI
            blocked_txn_id = f"BLK-{random.randint(100000, 999999)}"
            transactions_coll.insert_one({
                "transaction_id": blocked_txn_id,
                "from_email": from_email,
                "to_email": to_email,
                "amount": amount,
                "currency": "USD",
                "category": category,
                "description": f"Failed Transfer: {description}",
                "location": location.get('city', 'Online'),
                "ip_address": ip_address,
                "device": {"type": device.get('type', 'Unknown')},
                "fraud_check": {
                    "status": "BLOCKED",
                    "risk_score": 0,
                    "reasons": ["Insufficient funds (Credit)"],
                    "checked_at": datetime.utcnow()
                },
                "status": "BLOCKED",
                "timestamp": datetime.utcnow()
            })

            return jsonify({
                "success": False,
                "status": "BLOCKED",
                "risk_score": 0,
                "decision": "Transaction blocked: Insufficient Funds",
                "reasons": ["Insufficient funds in account/card.", "Credit limit exceeded."],
                "transaction_id": blocked_txn_id
            })

    # 1.0 Verify Recipient (Must be a valid user or merchant)
    # Support both email and account number
    recipient_identifier = to_email

    # Check if it's an account number (16 digits) or email
    if recipient_identifier.isdigit() and len(recipient_identifier) == 16:
        # It's an account number
        recipient = customers_coll.find_one(
            {"account_number": recipient_identifier})
        if recipient:
            # Use the email for further processing
            to_email = recipient.get('email')
            print(
                f"[PAYMENT] ✓ Recipient found by account number: {recipient_identifier} → {to_email}")
    else:
        # It's an email
        recipient = merchants_coll.find_one(
            {"email": to_email}) or customers_coll.find_one({"email": to_email})

    if not recipient:
        # REPORT TO FRAUD SERVICE BEFORE RETURNING ERROR
        print(
            f"[PAYMENT] ❌ Recipient '{recipient_identifier}' not found. Reporting to Fraud Service...")
        score, reasons, raw_json = calculate_risk_score({
            "id": f"FAIL-{random.randint(100000, 999999)}",
            "amount": amount,
            "merchant": recipient_identifier,  # The invalid identifier
            "customer": from_email,
            "type": "Validation Failure",  # Changed from Invalid Recipient
            "status": "Blocked",
            "location": location.get('city', 'Unknown'),
            "ip_address": ip_address,
            "device_type": device.get('type', 'Unknown'),
            "reasons": ["Attempt transfer to non-existent recipient", "Potential Account Enumeration"]
        })

        # SAVE TO DB AS BLOCKED (So it shows in Dashboard)
        blocked_txn_id = f"BLK-{random.randint(100000, 999999)}"
        city = location.get('city', 'Unknown')
        country = location.get('country', 'Unknown')
        blocked_transaction = {
            "transaction_id": blocked_txn_id,
            "from_email": from_email,
            "to_email": recipient_identifier,  # The invalid input
            "amount": amount,
            "currency": "USD",
            "category": category,
            "description": f"Failed Transfer: {description}",
            "location": f"{city}, {country}",
            "ip_address": ip_address,
            "device": {"type": device.get('type', 'Unknown')},
            "fraud_check": {
                "status": "BLOCKED",
                "risk_score": 0,
                "reasons": ["Recipient account does not exist"],
                "checked_at": datetime.utcnow()
            },
            "status": "BLOCKED",  # Important for History
            "timestamp": datetime.utcnow()
        }
        transactions_coll.insert_one(blocked_transaction)
        log_audit(
            from_email, f"Payment Blocked: {blocked_txn_id}", "Payment", "Invalid Recipient")

        # Return as BLOCKED so frontend shows the Red Blocked UI
        return jsonify({
            "success": False,
            "status": "BLOCKED",
            "risk_score": 0,
            "decision": "Transaction blocked: Invalid Recipient",
            "reasons": [f"Recipient account '{recipient_identifier}' does not exist.", "Security Policy: Transaction Halted"],
            "transaction_id": blocked_txn_id
        })

    # 2. FRAUD CHECK via Fraud Service (Enhanced)
    print(
        f"\n[PAYMENT] Processing transfer {from_email} → {to_email}: ${amount}")
    print(
        f"[PAYMENT] IP: {ip_address}, Location: {location.get('city', 'Unknown')}, {location.get('country', 'Unknown')}")
    print(
        f"[PAYMENT] Device: {device.get('type', 'Unknown')}, Card: {card_type} ****{last_4}")

    # Fetch customer stats for context
    customer_profile = customers_coll.find_one({"email": from_email}) or {}

    # Call fraud service with enhanced data
    risk_score, reasoning, full_analysis = calculate_risk_score({
        "id": f"TXN-{random.randint(100000, 999999)}",
        "amount": amount,
        "merchant": to_email,
        "location": location,  # Pass full object for extraction
        "customer": from_email,
        "type": "Transfer",
        "category": category,

        # Enhanced fields
        "ip_address": ip_address,
        "country": location.get('country', 'Unknown'),
        "latitude": location.get('latitude', 0),
        "longitude": location.get('longitude', 0),
        "device_type": device.get('type', 'Unknown'),
        "browser": device.get('browser', 'Unknown'),
        "os": device.get('os', 'Unknown'),
        "card_type": card_type,
        "timezone": session.get('timezone', 'UTC'),

        # User History Context
        "user_txn_count": customer_profile.get('txn_count', 0),
        "user_total_spent": customer_profile.get('total_spent', 0),
        "user_risk_score": customer_profile.get('risk_score', 0),
        "account_created_at": str(customer_profile.get('created_at', datetime.utcnow().isoformat()))
    })

    # Parse reasons
    # Parse reasons (Handle list vs string from updated fraud service)
    if isinstance(reasoning, list):
        reasons = reasoning
    elif isinstance(reasoning, str):
        reasons = reasoning.split(", ") if reasoning else []
    else:
        reasons = []

    # LOGGING: Confirm Receipt of Decision
    decision_status = 'BLOCKED' if risk_score >= 85 else (
        'REVIEW' if risk_score >= 60 else 'APPROVED')
    print(f"[PROOF] 📩 Fraud Response Received:")
    print(f"   > Risk Score: {risk_score}")
    print(f"   > Decision:   {decision_status}")
    print(f"   > Reasons:    {reasons}")
    print("-" * 50)

    # Determine status based on fraud service response
    if risk_score >= 85:
        status = "BLOCKED"
        decision = "Transaction blocked due to high fraud risk"
    elif risk_score >= 60:
        status = "REVIEW"
        decision = "Transaction requires manual review"
    else:
        status = "APPROVED"
        decision = "Transaction approved"

    # Generate transaction ID
    txn_id = f"TXN-{random.randint(100000, 999999)}"

    # 3. Process Payment
    if status == "APPROVED":
        # Credit Merchant (Update Stats if it is a merchant)
        merchants_coll.update_one(
            {"email": to_email},
            {"$inc": {"total_sales": amount, "approved_count": 1}}
        )

        # Debut Funds
        if is_debit:
            customers_coll.update_one(
                {"email": from_email},
                {"$inc": {"balance": -amount}}  # Deduct from balance
            )
        else:
            # Debited from Card (Update Spent)
            credit_cards_coll.update_one(
                {"card_id": card.get('card_id', card_id)},
                {"$inc": {"current_spent": amount}}
            )

        # Save Transaction (Enhanced)
        city = location.get('city', 'Unknown')
        country = location.get('country', 'Unknown')

        transaction = {
            "transaction_id": txn_id,
            "from_email": from_email,
            "to_email": to_email,
            "amount": amount,
            "currency": "USD",
            "category": category,
            "description": description,

            # Location & IP
            "location": f"{city}, {country}",
            "country": country,
            "ip_address": ip_address,
            "latitude": location.get('latitude', 0),
            "longitude": location.get('longitude', 0),
            "channel": "Web",

            # Card details
            "payment_method": {
                "type": "Debit Card" if is_debit else "Credit Card",
                "card_id": "DEBIT" if is_debit else card.get('card_id', card_id),
                "last_4": last_4,
                "card_type": card_type
            },

            # Device & Session
            "device": {
                "type": device.get('type', 'Unknown'),
                "browser": device.get('browser', 'Unknown'),
                "os": device.get('os', 'Unknown')
            },
            "session": {
                "timezone": session.get('timezone', 'UTC'),
                "language": session.get('language', 'en')
            },

            # Fraud check results
            "fraud_check": {
                "status": status,
                "risk_score": risk_score,
                "reasons": reasons,
                "checked_at": datetime.utcnow()
            },
            "status": "COMPLETED",
            "timestamp": datetime.utcnow()
        }

        # Add Order ID for merchant payments
        if data.get('is_merchant_payment'):
            transaction['order_id'] = f"ORD-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}"
            # Force category for merchant payments if not set
            transaction['category'] = 'Shopping'

        transactions_coll.insert_one(transaction)

        # Update Customer Stats
        customers_coll.update_one(
            {"email": from_email},
            {
                "$inc": {"txn_count": 1, "total_spent": amount},
                "$set": {"last_txn": datetime.utcnow()}
            },
            upsert=True
        )

        log_audit(from_email, f"Payment: {txn_id}",
                  "Payment", f"${amount} to {to_email}")

        return jsonify({
            "success": True,
            "transaction_id": txn_id,
            "status": status,
            "risk_score": risk_score,
            "decision": decision,
            "message": "Payment successful"
        })

    else:
        # BLOCKED or REVIEW (Enhanced)
        city = location.get('city', 'Unknown')
        country = location.get('country', 'Unknown')

        transaction = {
            "transaction_id": txn_id,
            "from_email": from_email,
            "to_email": to_email,
            "amount": amount,
            "currency": "USD",
            "category": category,
            "description": description,

            # Location & IP
            "location": f"{city}, {country}",
            "country": country,
            "ip_address": ip_address,
            "latitude": location.get('latitude', 0),
            "longitude": location.get('longitude', 0),
            "channel": "Web",

            # Card details
            "payment_method": {
                "type": "Debit Card" if is_debit else "Credit Card",
                "card_id": "DEBIT" if is_debit else card.get('card_id', card_id),
                "last_4": last_4,
                "card_type": card_type
            },

            # Device & Session
            "device": {
                "type": device.get('type', 'Unknown'),
                "browser": device.get('browser', 'Unknown'),
                "os": device.get('os', 'Unknown')
            },
            "session": {
                "timezone": session.get('timezone', 'UTC'),
                "language": session.get('language', 'en')
            },

            # Fraud check results
            "fraud_check": {
                "status": status,
                "risk_score": risk_score,
                "reasons": reasons,
                "checked_at": datetime.utcnow()
            },
            "status": status,
            "timestamp": datetime.utcnow()
        }
        transactions_coll.insert_one(transaction)

        # Create alert
        if risk_score >= 60:
            alerts_coll.insert_one({
                "transaction_id": txn_id,
                "customer": from_email,
                "risk_score": risk_score,
                "severity": "Critical" if risk_score >= 85 else "High",
                "status": "New",
                "timestamp": datetime.utcnow()
            })

        log_audit(
            from_email, f"Payment {status}: {txn_id}", "Payment", f"Risk: {risk_score}")

        return jsonify({
            "success": False,
            "transaction_id": txn_id,
            "status": status,
            "risk_score": risk_score,
            "decision": decision,
            "reasons": reasons
        })


@app.route('/api/bank/add-money', methods=['POST'])
def add_money():
    """Simulate adding money to account"""
    data = request.json
    email = data.get('email')
    amount = float(data.get('amount', 0))

    account = bank_accounts_coll.find_one({"user_email": email})
    if not account:
        return jsonify({"success": False, "message": "Account not found"}), 404

    new_balance = account['balance'] + amount
    bank_accounts_coll.update_one(
        {"user_email": email},
        {"$set": {"balance": new_balance, "last_updated": datetime.utcnow()}}
    )

    log_audit(email, "Money Added", "Bank", f"${amount}")
    return jsonify({"success": True, "new_balance": new_balance})

# --- CREDIT CARD SYSTEM ---


@app.route('/api/cards/link', methods=['POST'])
def link_credit_card():
    """Link a credit card to user account"""
    data = request.json
    email = data.get('email')

    # Check if card already exists
    card_number = data.get('card_number')
    last_4 = card_number[-4:] if len(card_number) >= 4 else card_number

    existing = credit_cards_coll.find_one(
        {"user_email": email, "last_4": last_4})
    if existing:
        return jsonify({"success": False, "message": "Card already linked"})

    card = {
        "card_id": f"CARD-{random.randint(100000, 999999)}",
        "user_email": email,
        "card_number": card_number,  # In production, encrypt this!
        "last_4": last_4,
        "card_holder": data.get('card_holder'),
        "expiry_month": data.get('expiry_month'),
        "expiry_year": data.get('expiry_year'),
        "cvv": data.get('cvv'),  # In production, don't store CVV!
        "card_type": data.get('card_type', 'Visa'),
        "billing_address": data.get('billing_address', ''),
        "is_primary": data.get('is_primary', True),
        "status": "Active",
        "linked_at": datetime.utcnow()
    }

    credit_cards_coll.insert_one(card)
    log_audit(email, "Credit Card Linked", "Card", f"****{last_4}")

    return jsonify({"success": True, "message": "Card linked successfully", "card_id": card['card_id']})


@app.route('/api/cards/<email>', methods=['GET'])
def get_user_cards(email):
    """Get all cards for a user"""
    print(f"Fetching cards for: {email}")  # DEBUG
    cards = list(credit_cards_coll.find({"user_email": email}))
    for card in cards:
        card['_id'] = str(card['_id'])
        # Don't send full card number
        card['card_number'] = f"****-****-****-{card['last_4']}"
        del card['cvv']  # Never send CVV
    return jsonify(cards)


@app.route('/api/cards/delete/<card_id>', methods=['DELETE'])
def delete_card(card_id):
    """Delete a credit card"""
    result = credit_cards_coll.delete_one({"card_id": card_id})
    if result.deleted_count > 0:
        log_audit("User", f"Card Deleted: {card_id}", "Card", "Deleted")
        return jsonify({"success": True, "message": "Card deleted"})
    return jsonify({"success": False, "message": "Card not found"}), 404


# --- BALANCE & PAYMENT MANAGEMENT ---

@app.route('/api/balance/add', methods=['POST'])
def add_balance():
    """Add money to customer account"""
    data = request.json
    customer_email = data.get('customer_email')
    amount = float(data.get('amount', 0))

    if amount <= 0:
        return jsonify({"error": "Invalid amount"}), 400

    # Update customer balance
    customers_coll.update_one(
        {"email": customer_email},
        {
            "$inc": {"balance": amount},
            "$set": {"last_updated": datetime.utcnow()}
        },
        upsert=True
    )

    # Get updated balance
    customer = customers_coll.find_one({"email": customer_email})
    new_balance = customer.get('balance', 0) if customer else amount

    # Log transaction
    balance_txn = {
        "id": f"BAL-{random.randint(100000, 999999)}",
        "customer": customer_email,
        "type": "Balance Add",
        "amount": amount,
        "new_balance": new_balance,
        "timestamp": datetime.utcnow(),
        "status": "Completed"
    }
    transactions_coll.insert_one(balance_txn)

    log_audit(customer_email, "Added Balance", "Account", f"Added ${amount}")

    return jsonify({
        "success": True,
        "message": f"${amount} added successfully",
        "new_balance": new_balance,
        "transaction_id": balance_txn['id']
    })


@app.route('/api/balance/check', methods=['GET'])
def check_balance():
    """Check customer balance"""
    customer_email = request.args.get('customer_email')

    customer = customers_coll.find_one({"email": customer_email})
    balance = customer.get('balance', 0) if customer else 0

    return jsonify({
        "customer": customer_email,
        "balance": balance,
        "currency": "USD"
    })


@app.route('/api/receipt/<txn_id>', methods=['GET'])
def get_receipt(txn_id):
    """Generate and return receipt for transaction"""
    transaction = transactions_coll.find_one({"id": txn_id})

    if not transaction:
        return jsonify({"error": "Transaction not found"}), 404

    # Generate receipt HTML
    receipt_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Payment Receipt - {txn_id}</title>
        <style>
            body {{
                font-family: 'Arial', sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 30px;
                background: #f5f5f5;
            }}
            .receipt {{
                background: white;
                padding: 40px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            .header {{
                text-align: center;
                border-bottom: 2px solid #4CAF50;
                padding-bottom: 20px;
                margin-bottom: 30px;
            }}
            .header h1 {{
                color: #4CAF50;
                margin: 0;
                font-size: 28px;
            }}
            .status {{
                display: inline-block;
                padding: 8px 20px;
                border-radius: 20px;
                font-weight: bold;
                margin-top: 10px;
            }}
            .status.approved {{
                background: #4CAF50;
                color: white;
            }}
            .details {{
                margin: 30px 0;
            }}
            .detail-row {{
                display: flex;
                justify-content: space-between;
                padding: 12px 0;
                border-bottom: 1px solid #eee;
            }}
            .detail-label {{
                color: #666;
                font-weight: 500;
            }}
            .detail-value {{
                color: #333;
                font-weight: 600;
            }}
            .amount {{
                font-size: 32px;
                color: #4CAF50;
                text-align: center;
                margin: 30px 0;
                font-weight: bold;
            }}
            .footer {{
                text-align: center;
                margin-top: 40px;
                padding-top: 20px;
                border-top: 2px solid #eee;
                color: #999;
                font-size: 12px;
            }}
            .print-btn {{
                background: #2196F3;
                color: white;
                border: none;
                padding: 12px 30px;
                border-radius: 5px;
                cursor: pointer;
                font-size: 16px;
                margin-top: 20px;
            }}
            .print-btn:hover {{
                background: #1976D2;
            }}
            @media print {{
                body {{
                    background: white;
                }}
                .print-btn {{
                    display: none;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="receipt">
            <div class="header">
                <h1>🏦 Swift Bank</h1>
                <p style="color: #666; margin: 10px 0;">Payment Receipt</p>
                <span class="status approved">{transaction['status']}</span>
            </div>
            
            <div class="amount">
                ${transaction['amount']:.2f}
            </div>
            
            <div class="details">
                <div class="detail-row">
                    <span class="detail-label">Transaction ID</span>
                    <span class="detail-value">{transaction['id']}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Date & Time</span>
                    <span class="detail-value">{transaction['timestamp'].strftime('%B %d, %Y at %I:%M %p')}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Merchant</span>
                    <span class="detail-value">{transaction.get('merchant', 'N/A')}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Customer</span>
                    <span class="detail-value">{transaction['customer']}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Payment Method</span>
                    <span class="detail-value">Account Balance</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Previous Balance</span>
                    <span class="detail-value">${transaction.get('previous_balance', 0):.2f}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">New Balance</span>
                    <span class="detail-value">${transaction.get('new_balance', 0):.2f}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Fraud Risk Score</span>
                    <span class="detail-value">{transaction['risk_score']}/100 (Low Risk)</span>
                </div>
            </div>
            
            <div style="text-align: center;">
                <button class="print-btn" onclick="window.print()">🖨️ Print Receipt</button>
            </div>
            
            <div class="footer">
                <p>This is a computer-generated receipt and does not require a signature.</p>
                <p>Protected by AI-powered fraud detection | Swift Bank © 2026</p>
                <p>Transaction secured with end-to-end encryption</p>
            </div>
        </div>
    </body>
    </html>
    """

    return receipt_html


# --- ACCOUNT DASHBOARD APIs ---
@app.route('/api/account/summary', methods=['GET'])
def get_account_summary():
    """Get comprehensive account summary for dashboard"""
    email = request.args.get('email')

    if not email:
        return jsonify({"error": "Email parameter required"}), 400

    # Get customer data
    customer = customers_coll.find_one({"email": email})

    # Check Merchant if not Customer
    if not customer:
        merchant = merchants_coll.find_one({"email": email})
        if merchant:
            return jsonify({
                "account_number": merchant.get('account_number', 'N/A'),
                "balance": merchant.get('total_revenue', 0),
                "total_credit_limit": 0,
                "available_credit": 0,
                "total_spent": 0,
                "account_status": merchant.get('status', 'Active'),
                "member_since": merchant.get('created_at'),
                "customer_name": merchant.get('business_name', 'Merchant'),
                "email": merchant.get('email'),
                "phone": merchant.get('phone', ''),
                "total_transactions": transactions_coll.count_documents({"merchant": email}),
                "approved_transactions": merchant.get('approved_count', 0),
                "blocked_transactions": merchant.get('blocked_count', 0),
                "review_transactions": 0,
                "linked_cards_count": 0,
                "is_merchant": True
            })
        return jsonify({"error": "User not found"}), 404

    # Get linked cards
    cards = list(credit_cards_coll.find({"user_email": email}))

    # Calculate credit totals
    total_credit_limit = sum(card.get('limit', 0) for card in cards)
    total_spent = sum(card.get('current_spent', 0) for card in cards)
    available_credit = total_credit_limit - total_spent

    # Get transaction stats
    total_transactions = transactions_coll.count_documents({
        "$or": [{"customer": email}, {"from_email": email}]
    })

    # Get recent transaction count by status
    approved_count = transactions_coll.count_documents({
        "$or": [{"customer": email}, {"from_email": email}],
        "status": {"$in": ["Approved", "APPROVED"]}
    })

    blocked_count = transactions_coll.count_documents({
        "$or": [{"customer": email}, {"from_email": email}],
        "status": {"$in": ["Blocked", "BLOCKED"]}
    })

    review_count = transactions_coll.count_documents({
        "$or": [{"customer": email}, {"from_email": email}],
        "status": {"$in": ["Review", "REVIEW"]}
    })

    return jsonify({
        "account_number": customer.get('account_number', 'N/A'),
        "balance": customer.get('balance', 0),
        "total_credit_limit": total_credit_limit,
        "available_credit": available_credit,
        "total_spent": total_spent,
        "account_status": customer.get('status', 'Active'),
        "member_since": customer.get('created_at'),
        "customer_name": customer.get('name', 'Customer'),
        "email": customer.get('email'),
        "phone": customer.get('phone', ''),
        "total_transactions": total_transactions,
        "approved_transactions": approved_count,
        "blocked_transactions": blocked_count,
        "review_transactions": review_count,
        "linked_cards_count": len(cards)
    })


@app.route('/api/account/recent-transactions', methods=['GET'])
def get_recent_transactions():
    """Get recent transactions for account dashboard"""
    email = request.args.get('email')
    limit = int(request.args.get('limit', 10))

    if not email:
        return jsonify({"error": "Email parameter required"}), 400

    query = {"$or": [{"customer": email}, {"from_email": email}]}
    txns = list(transactions_coll.find(
        query).sort("timestamp", -1).limit(limit))

    for t in txns:
        t['_id'] = str(t['_id'])

    return jsonify(txns)


if __name__ == '__main__':
    print("--- Swift Bank World-Class Backend Running ---")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
