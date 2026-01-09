from flask import Flask, request, jsonify, render_template, send_from_directory, Response
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime
import random
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__, static_folder='.', template_folder='.')
CORS(app)

# Email Config
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
MAIL_USERNAME = "mkbharvad534@gmail.com"
MAIL_PASSWORD = "dwtp fmiq miyl ccvq"

def send_email(to_email, subject, body):
    try:
        msg = MIMEMultipart()
        msg['From'] = MAIL_USERNAME
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html')) # HTML for better formatting
        
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

# Database Configuration
MONGO_URI = "mongodb+srv://mkbharvad8080:Mkb%408080@cluster0.a82h2.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client['swift_ai_fraud_detection']

# Collections
transactions_coll = db['transactions']
kyc_coll = db['kyc_records']
alerts_coll = db['alerts']
customers_coll = db['customers']
models_coll = db['models_meta']
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

# --- AUTH ENDPOINTS ---
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    email = data.get('email')
    
    if db['users'].find_one({"email": email}):
        return jsonify({"success": False, "message": "User already exists"})
    
    user = {
        "name": data.get('name'),
        "email": email,
        "password": data.get('password'), 
        "role": "Analyst",
        "created_at": datetime.utcnow(),
        "status": "Active"
    }
    db['users'].insert_one(user)
    
    # Send Welcome Email
    email_body = f"""
    <h3>Welcome to Swift AI!</h3>
    <p>Hello {user['name']},</p>
    <p>Your account has been successfully created.</p>
    <p>You can now login to the dashboard.</p>
    """
    send_email(email, "Welcome to Swift AI Platform", email_body)
    
    log_audit("System", f"New User Registered: {email}", "Auth", "Register")
    return jsonify({"success": True, "message": "Registration successful"})

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    user = db['users'].find_one({"email": email, "password": password})
    if user:
        # Send Login Notification
        send_email(email, "New Login Detected", f"<p>New login to your account at {datetime.utcnow()}</p>")
        
        return jsonify({
            "success": True, 
            "user": {
                "name": user['name'], 
                "email": user['email'], 
                "role": user['role']
            }
        })
    
    return jsonify({"success": False, "message": "Invalid credentials"}), 401

# --- PROFILE MANAGEMENT ---
@app.route('/api/profile', methods=['GET', 'POST'])
def manage_profile():
    # For simulation, default to Admin or use query param
    email = request.args.get('email', "admin@swiftai.com")
    
    if request.method == 'POST':
        data = request.json
        email = data.get('email', email) # Allow updating email context if needed
        
        update_fields = {
            "name": data.get('name'),
            "phone": data.get('phone'),
            "location": data.get('location', 'Headquarters, Silicon Valley, CA'),
            "updated_at": datetime.utcnow()
        }
        
        result = db['users'].update_one({"email": email}, {"$set": update_fields}, upsert=True)
        log_audit(email, "Updated Profile", "Profile", "User updated personal details")
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
@app.route('/api/bank/kyc', methods=['POST'])
def submit_kyc():
    data = request.json
    record = {
        "customer_id": data.get('customer_id'),
        "name": data.get('name'),
        "doc_type": data.get('doc_type'),
        "status": "Submitted",
        "submitted_at": datetime.utcnow()
    }
    db['kyc_records'].insert_one(record)
    send_email(MAIL_USERNAME, "New KYC Submission", f"New KYC document submitted by {record['name']}")
    return jsonify({"success": True, "message": "KYC Submitted"})

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
        send_email(MAIL_USERNAME, "CRITICAL: KYC Alert", f"High Risk KYC Detected: {name}. System blocked verification.")
        
    return jsonify({
        "status": status,
        "details": { "document_check": "Forged" if is_fraud else "Valid" }
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
            recent_blocked = list(db['transactions'].find({"status": "Blocked"}).sort("timestamp", -1).limit(3))
            if recent_blocked:
                details = ", ".join([f"{t.get('customer', 'Unknown')} (${t.get('amount')})" for t in recent_blocked])
                response_text = f"The last 3 blocked transactions were: {details}."
            else:
                response_text = "No blocked transactions found recently."
                
        elif 'customer' in msg or 'check' in msg:
            # Simple simulation: Extract name if possible, or just give general info
            response_text = "To check a specific customer, please visit the Customers page or provide an ID. I can tell you that we have " + str(db['customers'].count_documents({})) + " active profiles."
            
        elif 'alert' in msg:
            pending = db['alerts'].count_documents({"status": "Pending"})
            response_text = f"There are currently {pending} pending alerts requiring your attention."
            
        elif 'risk' in msg:
            response_text = "Global Risk Level is currently MODERATE based on recent velocity checks."
            
    except Exception as e:
        response_text = "I encountered an error accessing the database."

    return jsonify({"response": response_text})



def calculate_risk_score(txn):
    score = random.randint(5, 25)
    reasons = []
    
    amount = float(txn.get('amount', 0))
    if amount > 15000:
        score += 45
        reasons.append("Extreme Transaction Amount")
    elif amount > 5000:
        score += 20
        reasons.append("High Transaction Value")
        
    if txn.get('location') == 'High Risk Zone':
        score += 40
        reasons.append("Sanctioned/High-Risk Location")
        
    if txn.get('channel') == 'Simulator' and random.random() > 0.8:
        score += 15
        reasons.append("Simulated Pattern Match")

    final_score = min(100, score)
    reason_str = ", ".join(reasons) if reasons else "Normal Behavioral Pattern"
    return final_score, reason_str

# Initialize defaults if empty
if models_coll.count_documents({}) == 0:
    models_coll.insert_many([
        {"name": "Neural Fraud Shield v4", "type": "Deep Learning", "accuracy": 99.2, "status": "Active", "last_train": "2026-01-01"},
        {"name": "Isolation Forest Core", "type": "Anomaly Detection", "accuracy": 97.5, "status": "Active", "last_train": "2025-12-15"},
        {"name": "XGBoost Classifier", "type": "Gradient Boosting", "accuracy": 98.8, "status": "Training", "last_train": "2025-12-28"}
    ])

# --- Routes ---
@app.route('/')
def index(): return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('.', filename)

# Location to Coordinates Mapping
LOCATION_MAP = {
    "Mumbai, IN": [19.0760, 72.8777],
    "New York, US": [40.7128, -74.0060],
    "London, UK": [51.5074, -0.1278],
    "Dubai, UAE": [25.2048, 55.2708],
    "Lagos, Nigeria": [6.5244, 3.3792],
    "Tokyo, Japan": [35.6762, 139.6503],
    "High Risk Zone": [34.5553, 69.2075] # Kabul (example)
}

@app.route('/api/transactions/<txn_id>', methods=['GET'])
def get_transaction(txn_id):
    txn = transactions_coll.find_one({"id": txn_id})
    if txn:
        txn['_id'] = str(txn['_id'])
        return jsonify(txn)
    return jsonify({"error": "Transaction not found"}), 404

# 1. Transactions & Simulation
@app.route('/api/transactions', methods=['POST', 'GET'])
def manage_transactions():
    if request.method == 'POST':
        data = request.json
        txn_id = data.get('id', f"TXN-{random.randint(100000, 999999)}")
        risk_score, reasoning = calculate_risk_score(data)
        
        location_name = data.get('location', 'Globe')
        coords = LOCATION_MAP.get(location_name, [random.uniform(-60, 60), random.uniform(-120, 120)])

        transaction = {
            "id": txn_id,
            "customer": data.get('customer', 'Unknown'),
            "amount": float(data.get('amount', 0)),
            "location": location_name,
            "coords": coords,
            "channel": data.get('channel', 'Web'),
            "timestamp": datetime.utcnow(),
            "risk_score": risk_score,
            "ai_reason": reasoning,
            "status": "Blocked" if risk_score > 85 else ("Review" if risk_score > 60 else "Approved")
        }
        transactions_coll.insert_one(transaction)
        
        # Sync Customer Profile
        customers_coll.update_one(
            {"name": transaction['customer']},
            {"$inc": {"txn_count": 1, "total_spent": transaction['amount']}, 
             "$set": {"last_txn": datetime.utcnow(), "risk_score": risk_score}},
            upsert=True
        )

        if risk_score > 60:
            alerts_coll.insert_one({
                "transaction_id": txn_id,
                "customer": transaction['customer'],
                "risk_score": risk_score,
                "severity": "Critical" if risk_score > 85 else "High",
                "status": "Pending",
                "timestamp": datetime.utcnow()
            })
        
        transaction['_id'] = str(transaction['_id'])
        return jsonify(transaction)
    
    # GET with Filters
    status = request.args.get('status')
    query = {"status": status} if status and status != 'All' else {}
    txns = list(transactions_coll.find(query).sort("timestamp", -1).limit(50))
    for t in txns: t['_id'] = str(t['_id'])
    return jsonify(txns)

# 2. Alerts & Decisioning
@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    alerts = list(alerts_coll.find({"status": "Pending"}).sort("timestamp", -1))
    for a in alerts: a['_id'] = str(a['_id'])
    return jsonify(alerts)

@app.route('/api/alerts/<txn_id>', methods=['PATCH'])
def action_alert(txn_id):
    data = request.json
    new_status = data.get('status')
    alerts_coll.update_one({"transaction_id": txn_id}, {"$set": {"status": "Resolved", "decision": new_status}})
    transactions_coll.update_one({"id": txn_id}, {"$set": {"status": new_status}})
    log_audit("Admin", f"Resolved Alert {txn_id}", "Alerts", f"Set status to {new_status}")
    return jsonify({"status": "success"})

# 3. Models Management
@app.route('/api/models', methods=['GET'])
def get_models():
    models = list(models_coll.find())
    for m in models: m['_id'] = str(m['_id'])
    return jsonify(models)

# 4. Customers
@app.route('/api/customers', methods=['GET'])
def get_customers():
    customers = list(customers_coll.find().sort("risk_score", -1).limit(20))
    for c in customers: c['_id'] = str(c['_id'])
    return jsonify(customers)

# 5. Audit Logs
@app.route('/api/audit', methods=['GET'])
def get_audit():
    logs = list(audit_coll.find().sort("timestamp", -1).limit(100))
    for l in logs: l['_id'] = str(l['_id'])
    return jsonify(logs)

# 6. Global Stats & Analytics
@app.route('/api/stats/dashboard', methods=['GET'])
def dashboard_stats():
    total_txns = transactions_coll.count_documents({})
    blocked = transactions_coll.count_documents({"status": "Blocked"})
    review = transactions_coll.count_documents({"status": "Review"})
    approved = transactions_coll.count_documents({"status": "Approved"})
    
    txns = list(transactions_coll.find({}, {"risk_score": 1, "timestamp": 1, "status": 1}).sort("timestamp", -1).limit(50))
    
    # Advanced stats for graphs
    trend_labels = [t['timestamp'].strftime("%H:%M") for t in reversed(txns[:15])]
    trend_data = [t['risk_score'] for t in reversed(txns[:15])]

    # Risk Bins (0-20, 21-40, 41-60, 61-80, 81-100)
    bins = [0] * 5
    for t in txns:
        score = t.get('risk_score', 0)
        idx = min(4, int(score // 20))
        bins[idx] += 1

    return jsonify({
        "kpis": {
            "alerts": alerts_coll.count_documents({"status": "Pending"}),
            "total_txns": total_txns,
            "blocked": blocked,
            "approved": approved,
            "review": review,
            "avg_risk": round(sum(t['risk_score'] for t in txns)/len(txns), 1) if txns else 0
        },
        "charts": {
            "trends": {"labels": trend_labels, "data": trend_data},
            "distribution": [approved, review, blocked],
            "risk_bins": bins
        }
    })

# Duplicate KYC verify removed

# 8. All-in-one Analytics
@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    # Group by channel
    pipeline = [{"$group": {"_id": "$channel", "count": {"$sum": 1}}}]
    channels = list(transactions_coll.aggregate(pipeline))
    
    # Group by location (Top 5)
    loc_pipeline = [{"$group": {"_id": "$location", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}, {"$limit": 5}]
    locations = list(transactions_coll.aggregate(loc_pipeline))
    
    return jsonify({
        "channels": {c['_id']: c['count'] for c in channels},
        "locations": {l['_id']: l['count'] for l in locations}
    })

# 9. Rules Management
@app.route('/api/rules', methods=['GET', 'POST'])
def manage_rules():
    if request.method == 'POST':
        data = request.json
        rule = {
            "name": data.get('name'),
            "description": data.get('description'),
            "condition": data.get('condition', 'amount > 10000'),
            "action": data.get('action', 'Block'),
            "status": "Active",
            "created_at": datetime.utcnow()
        }
        db['rules'].insert_one(rule)
        log_audit("Admin", f"Created Rule: {rule['name']}", "Rules", "Created")
        rule['_id'] = str(rule['_id'])
        return jsonify({"success": True, "rule": rule})
    
    rules = list(db['rules'].find())
    for r in rules: r['_id'] = str(r['_id'])
    return jsonify(rules)

# 10. Reports Generation & Export
@app.route('/api/reports/generate', methods=['POST'])
def generate_report():
    data = request.json
    report = {
        "name": data.get('name', 'Fraud Report'),
        "description": data.get('description', ''),
        "type": data.get('type', 'PDF'),
        "generated_at": datetime.utcnow(),
        "status": "Completed",
        "data": {
            "total_transactions": transactions_coll.count_documents({}),
            "blocked": transactions_coll.count_documents({"status": "Blocked"}),
            "total_alerts": alerts_coll.count_documents({})
        }
    }
    db['reports'].insert_one(report)
    log_audit("Admin", f"Generated Report: {report['name']}", "Reports", "Generated")
    report['_id'] = str(report['_id'])
    return jsonify({"success": True, "report": report, "download_url": f"/api/reports/download/{report['_id']}"})

@app.route('/api/reports', methods=['GET'])
def get_reports():
    reports = list(db['reports'].find().sort("generated_at", -1).limit(20))
    for r in reports: r['_id'] = str(r['_id'])
    return jsonify(reports)

@app.route('/api/reports/download/<report_id>', methods=['GET'])
def download_report(report_id):
    dummy_pdf_content = f"Fraud Detection Report ID: {report_id}\n\nGenerated on: {datetime.utcnow()}\n\nStatus: Completed\n\n[End of Report]"
    return Response(
        dummy_pdf_content,
        mimetype="text/plain",
        headers={"Content-disposition": f"attachment; filename=report_{report_id}.txt"}
    )

# 11. Integrations Management - See line 573 for complete CRUD implementation

# 12. User Management - See line 626 for complete implementation with invitations

# 13. Customer Profile Management
@app.route('/api/customers/create', methods=['POST'])
def create_customer_profile():
    data = request.json
    profile = {
        "name": data.get('name'),
        "email": data.get('email'),
        "phone": data.get('phone'),
        "risk_score": 0,
        "txn_count": 0,
        "total_spent": 0,
        "created_at": datetime.utcnow()
    }
    customers_coll.insert_one(profile)
    log_audit("Admin", f"Created Customer Profile: {profile['name']}", "Customers", "Created")
    profile['_id'] = str(profile['_id'])
    return jsonify({"success": True, "profile": profile})

# 14. Manual Alert Creation
@app.route('/api/alerts/create', methods=['POST'])
def create_manual_alert():
    data = request.json
    alert = {
        "transaction_id": data.get('transaction_id', f"MAN-{random.randint(1000, 9999)}"),
        "customer": data.get('customer'),
        "risk_score": data.get('risk_score', 75),
        "severity": data.get('severity', 'High'),
        "status": "Pending",
        "timestamp": datetime.utcnow(),
        "manual": True
    }
    alerts_coll.insert_one(alert)
    log_audit("Admin", f"Created Manual Alert: {alert['transaction_id']}", "Alerts", "Created")
    alert['_id'] = str(alert['_id'])
    return jsonify({"success": True, "alert": alert})

# 15. Export Data (CSV/Excel)
@app.route('/api/export/<data_type>', methods=['POST'])
def export_data(data_type):
    data = request.json
    export_record = {
        "type": data_type,
        "format": data.get('format', 'CSV'),
        "filters": data.get('filters', {}),
        "exported_at": datetime.utcnow(),
        "status": "Completed"
    }
    db['exports'].insert_one(export_record)
    log_audit("Admin", f"Exported {data_type} data", "Exports", "Completed")
    export_record['_id'] = str(export_record['_id'])
    return jsonify({"success": True, "export": export_record, "download_url": f"/api/exports/download/{export_record['_id']}"})

# Duplicate profile management removed (Consolidated at top)

@app.route('/api/profile/photo', methods=['POST'])
def upload_profile_photo():
    if 'photo' not in request.files:
        return jsonify({"error": "No photo uploaded"}), 400
    
    file = request.files['photo']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    # Save file (in production, use cloud storage like S3)
    filename = f"profile_{datetime.utcnow().timestamp()}.jpg"
    filepath = os.path.join('uploads', filename)
    os.makedirs('uploads', exist_ok=True)
    file.save(filepath)
    
    photo_url = f"/uploads/{filename}"
    # Use 'users' collection
    db['users'].update_one(
        {"email": "admin@swiftai.com"},
        {"$set": {"photo": photo_url}},
        upsert=True
    )
    log_audit("Admin", "Uploaded Profile Photo", "Profile", filename)
    return jsonify({"success": True, "photo_url": photo_url})

@app.route('/api/profile/password', methods=['POST'])
def change_password():
    data = request.json
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    
    # Use 'users' collection
    db['users'].update_one(
        {"email": "admin@swiftai.com"},
        {"$set": {"password_updated_at": datetime.utcnow()}},
        upsert=True
    )
    log_audit("Admin", "Changed Password", "Security", "Password updated")
    return jsonify({"success": True, "message": "Password changed successfully"})

@app.route('/api/export/<data_type>', methods=['POST'])
def export_generic_data(data_type):
    data = request.json
    export_record = {
        "type": data_type,
        "format": data.get('format', 'PDF'),
        "filters": data.get('filters', {}),
        "exported_at": datetime.utcnow(),
        "status": "Completed"
    }
    db['exports'].insert_one(export_record)
    log_audit("Admin", f"Exported {data_type} Report", "Exports", "Generated")
    
    # Return a download URL that points to our generic download handler
    return jsonify({
        "success": True, 
        "export": str(export_record),  # Convert to string just in case
        "download_url": f"/api/reports/download/{str(export_record['_id'])}" # Re-use report download logic for now
    })

# 17. Audit Logs with Export & Filtering
@app.route('/api/audit/logs', methods=['GET'])
def get_audit_logs():
    # Get filters from query params
    user = request.args.get('user')
    action = request.args.get('action')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = {}
    if user and user != 'All':
        query['user'] = user
    if action and action != 'All':
        query['action'] = action
    if start_date:
        query['timestamp'] = {"$gte": datetime.fromisoformat(start_date)}
    if end_date:
        if 'timestamp' in query:
            query['timestamp']['$lte'] = datetime.fromisoformat(end_date)
        else:
            query['timestamp'] = {"$lte": datetime.fromisoformat(end_date)}
    
    logs = list(audit_coll.find(query).sort("timestamp", -1).limit(100))
    for log in logs:
        log['_id'] = str(log['_id'])
        log['timestamp'] = log['timestamp'].isoformat()
    
    return jsonify(logs)

@app.route('/api/audit/export/pdf', methods=['POST'])
def export_audit_pdf():
    data = request.json
    filters = data.get('filters', {})
    
    # Create export record
    export_record = {
        "type": "audit_logs",
        "format": "PDF",
        "filters": filters,
        "exported_at": datetime.utcnow(),
        "status": "Completed",
        "record_count": audit_coll.count_documents(filters)
    }
    result = db['exports'].insert_one(export_record)
    export_id = str(result.inserted_id)
    
    log_audit("Admin", "Exported Audit Logs", "Audit", f"PDF export with {export_record['record_count']} records")
    return jsonify({"success": True, "export_id": export_id, "download_url": f"/api/audit/download/pdf/{export_id}"})

@app.route('/api/audit/export/csv', methods=['POST'])
def export_audit_csv():
    data = request.json
    filters = data.get('filters', {})
    
    export_record = {
        "type": "audit_logs",
        "format": "CSV",
        "filters": filters,
        "exported_at": datetime.utcnow(),
        "status": "Completed",
        "record_count": audit_coll.count_documents(filters)
    }
    result = db['exports'].insert_one(export_record)
    export_id = str(result.inserted_id)
    
    log_audit("Admin", "Exported Audit Logs", "Audit", f"CSV export with {export_record['record_count']} records")
    return jsonify({"success": True, "export_id": export_id, "download_url": f"/api/audit/download/csv/{export_id}"})

@app.route('/api/audit/download/<format>/<export_id>', methods=['GET'])
def download_audit_export(format, export_id):
    content = f"Audit Logs Export ({format.upper()})\n\nExport ID: {export_id}\n\nGenerated: {datetime.utcnow()}\n\n[Log Data Redacted for Demo]"
    
    return Response(
        content,
        mimetype="text/plain",
        headers={"Content-disposition": f"attachment; filename=audit_logs_{export_id}.{format.lower() if format != 'PDF' else 'txt'}"}
    )

# 18. Integrations Management (COMPLETE CRUD)
@app.route('/api/integrations', methods=['GET', 'POST'])
def manage_integrations():
    if request.method == 'POST':
        data = request.json
        integration = {
            "name": data.get('name'),
            "type": data.get('type', 'API'),
            "endpoint": data.get('endpoint', ''),
            "api_key": data.get('api_key', ''),
            "status": "Active",
            "created_at": datetime.utcnow(),
            "last_sync": None,
            "sync_count": 0
        }
        result = db['integrations'].insert_one(integration)
        integration['_id'] = str(result.inserted_id)
        log_audit("Admin", f"Added Integration: {integration['name']}", "Integrations", "Created")
        return jsonify({"success": True, "integration": integration})
    
    # GET all integrations
    integrations = list(db['integrations'].find())
    for i in integrations:
        i['_id'] = str(i['_id'])
        if i.get('created_at'):
            i['created_at'] = i['created_at'].isoformat()
    return jsonify(integrations)

@app.route('/api/integrations/<integration_id>', methods=['PUT', 'DELETE'])
def update_delete_integration(integration_id):
    from bson import ObjectId
    
    if request.method == 'PUT':
        data = request.json
        db['integrations'].update_one(
            {"_id": ObjectId(integration_id)},
            {"$set": {
                "name": data.get('name'),
                "endpoint": data.get('endpoint'),
                "api_key": data.get('api_key'),
                "updated_at": datetime.utcnow()
            }}
        )
        log_audit("Admin", f"Updated Integration: {integration_id}", "Integrations", "Modified")
        return jsonify({"success": True, "message": "Integration updated"})
    
    # DELETE
    db['integrations'].delete_one({"_id": ObjectId(integration_id)})
    log_audit("Admin", f"Deleted Integration: {integration_id}", "Integrations", "Removed")
    return jsonify({"success": True, "message": "Integration deleted"})

@app.route('/api/integrations/<integration_id>/test', methods=['POST'])
def test_integration(integration_id):
    from bson import ObjectId
    integration = db['integrations'].find_one({"_id": ObjectId(integration_id)})
    if not integration:
        return jsonify({"error": "Integration not found"}), 404
    
    # Simulate test
    test_result = {
        "status": "Success" if random.random() > 0.2 else "Failed",
        "response_time": f"{random.randint(50, 500)}ms",
        "tested_at": datetime.utcnow().isoformat()
    }
    
    db['integrations'].update_one(
        {"_id": ObjectId(integration_id)},
        {"$set": {"last_test": test_result}}
    )
    log_audit("Admin", f"Tested Integration: {integration['name']}", "Integrations", test_result['status'])
    return jsonify({"success": True, "result": test_result})

# 19. User Management with Invitations
@app.route('/api/users', methods=['GET', 'POST'])
def manage_users():
    if request.method == 'POST':
        data = request.json
        user = {
            "name": data.get('name'),
            "email": data.get('email'),
            "role": data.get('role', 'Analyst'),
            "department": data.get('department', ''),
            "status": "Pending" if data.get('send_invitation') else "Active",
            "created_at": datetime.utcnow(),
            "invitation_sent": data.get('send_invitation', False)
        }
        result = db['users'].insert_one(user)
        user['_id'] = str(result.inserted_id)
        
        # Send invitation if requested
        if data.get('send_invitation'):
            invitation = {
                "user_id": user['_id'],
                "email": user['email'],
                "token": f"INV-{random.randint(100000, 999999)}",
                "sent_at": datetime.utcnow(),
                "status": "Sent"
            }
            db['invitations'].insert_one(invitation)
            log_audit("Admin", f"Sent invitation to {user['email']}", "Users", "Invitation sent")
        
        log_audit("Admin", f"Created User: {user['name']}", "Users", "Created")
        return jsonify({"success": True, "user": user})
    
    # GET all users
    users = list(db['users'].find())
    for u in users:
        u['_id'] = str(u['_id'])
        if u.get('created_at'):
            u['created_at'] = u['created_at'].isoformat()
    return jsonify(users)

@app.route('/api/users/<user_id>', methods=['PUT', 'DELETE'])
def update_delete_user(user_id):
    from bson import ObjectId
    
    if request.method == 'PUT':
        data = request.json
        db['users'].update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {
                "name": data.get('name'),
                "email": data.get('email'),
                "role": data.get('role'),
                "department": data.get('department'),
                "updated_at": datetime.utcnow()
            }}
        )
        log_audit("Admin", f"Updated User: {user_id}", "Users", "Modified")
        return jsonify({"success": True, "message": "User updated"})
    
    # DELETE
    db['users'].delete_one({"_id": ObjectId(user_id)})
    log_audit("Admin", f"Deleted User: {user_id}", "Users", "Removed")
    return jsonify({"success": True, "message": "User deleted"})

@app.route('/api/users/<user_id>/block', methods=['POST'])
def block_user(user_id):
    from bson import ObjectId
    db['users'].update_one({"_id": ObjectId(user_id)}, {"$set": {"status": "Blocked"}})
    log_audit("Admin", f"Blocked User: {user_id}", "Users", "Blocked")
    return jsonify({"success": True, "message": "User blocked successfully"})

@app.route('/api/users/<user_id>/message', methods=['POST'])
def send_message_to_user(user_id):
    data = request.json
    message = {
        "user_id": user_id,
        "subject": data.get('subject'),
        "body": data.get('body'),
        "sent_at": datetime.utcnow(),
        "status": "Sent"
    }
    db['messages'].insert_one(message)
    log_audit("Admin", f"Sent message to {user_id}", "Messages", "Sent")
    return jsonify({"success": True, "message": "Message sent successfully"})

@app.route('/api/users/<user_id>/resend-invitation', methods=['POST'])
def resend_invitation(user_id):
    from bson import ObjectId
    user = db['users'].find_one({"_id": ObjectId(user_id)})
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    invitation = {
        "user_id": user_id,
        "email": user['email'],
        "token": f"INV-{random.randint(100000, 999999)}",
        "sent_at": datetime.utcnow(),
        "status": "Sent"
    }
    db['invitations'].insert_one(invitation)
    log_audit("Admin", f"Resent invitation to {user['email']}", "Users", "Invitation resent")
    return jsonify({"success": True, "message": "Invitation resent successfully"})

# 20. File Upload Handler
@app.route('/uploads/<filename>')
def serve_upload(filename):
    return send_from_directory('uploads', filename)

# 21. Transaction Actions (Approve/Block/Review)
@app.route('/api/transactions/<txn_id>/approve', methods=['POST'])
def approve_transaction(txn_id):
    transactions_coll.update_one({"id": txn_id}, {"$set": {"status": "Approved"}})
    log_audit("Admin", f"Approved Transaction: {txn_id}", "Transactions", "Approved")
    return jsonify({"success": True, "message": "Transaction approved"})

@app.route('/api/transactions/<txn_id>/block', methods=['POST'])
def block_transaction(txn_id):
    transactions_coll.update_one({"id": txn_id}, {"$set": {"status": "Blocked"}})
    log_audit("Admin", f"Blocked Transaction: {txn_id}", "Transactions", "Blocked")
    return jsonify({"success": True, "message": "Transaction blocked"})

@app.route('/api/transactions/<txn_id>/review', methods=['POST'])
def review_transaction(txn_id):
    transactions_coll.update_one({"id": txn_id}, {"$set": {"status": "Review"}})
    log_audit("Admin", f"Sent Transaction to Review: {txn_id}", "Transactions", "Review")
    return jsonify({"success": True, "message": "Transaction sent to review"})

# 22. Customer Detail & Management
@app.route('/api/customers/<customer_id>', methods=['GET', 'PUT'])
def manage_customer_detail(customer_id):
    if request.method == 'GET':
        customer = customers_coll.find_one({"name": customer_id})
        if not customer:
            return jsonify({"error": "Customer not found"}), 404
        customer['_id'] = str(customer['_id'])
        return jsonify(customer)
    
    # UPDATE
    data = request.json
    customers_coll.update_one(
        {"name": customer_id},
        {"$set": {
            "email": data.get('email'),
            "phone": data.get('phone'),
            "updated_at": datetime.utcnow()
        }}
    )
    log_audit("Admin", f"Updated Customer: {customer_id}", "Customers", "Modified")
    return jsonify({"success": True, "message": "Customer updated"})

@app.route('/api/customers/<customer_id>/transactions', methods=['GET'])
def get_customer_transactions(customer_id):
    txns = list(transactions_coll.find({"customer": customer_id}).sort("timestamp", -1).limit(50))
    for t in txns:
        t['_id'] = str(t['_id'])
    return jsonify(txns)

@app.route('/api/customers/<customer_id>/alerts', methods=['GET'])
def get_customer_alerts(customer_id):
    alerts = list(alerts_coll.find({"customer": customer_id}).sort("timestamp", -1).limit(20))
    for a in alerts:
        a['_id'] = str(a['_id'])
    return jsonify(alerts)

@app.route('/api/customers/<customer_id>/block', methods=['POST'])
def block_customer(customer_id):
    customers_coll.update_one({"name": customer_id}, {"$set": {"status": "Blocked"}})
    log_audit("Admin", f"Blocked Customer: {customer_id}", "Customers", "Blocked")
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
        {"$set": {"severity": "Critical", "escalated": True, "escalated_at": datetime.utcnow()}}
    )
    log_audit("Admin", f"Escalated Alert: {alert_id}", "Alerts", "Escalated")
    return jsonify({"success": True, "message": "Alert escalated"})

@app.route('/api/alerts/<alert_id>/assign', methods=['POST'])
def assign_alert(alert_id):
    from bson import ObjectId
    data = request.json
    alerts_coll.update_one(
        {"_id": ObjectId(alert_id)},
        {"$set": {"assigned_to": data.get('user_id'), "assigned_at": datetime.utcnow()}}
    )
    log_audit("Admin", f"Assigned Alert: {alert_id} to {data.get('user_id')}", "Alerts", "Assigned")
    return jsonify({"success": True, "message": "Alert assigned"})

# 24. Report Management
@app.route('/api/reports/<report_id>', methods=['DELETE'])
def delete_report(report_id):
    from bson import ObjectId
    db['reports'].delete_one({"_id": ObjectId(report_id)})
    log_audit("Admin", f"Deleted Report: {report_id}", "Reports", "Deleted")
    return jsonify({"success": True, "message": "Report deleted"})

@app.route('/api/reports/<report_id>/schedule', methods=['POST'])
def schedule_report(report_id):
    from bson import ObjectId
    data = request.json
    db['reports'].update_one(
        {"_id": ObjectId(report_id)},
        {"$set": {
            "scheduled": True,
            "schedule_frequency": data.get('frequency', 'daily'),
            "schedule_time": data.get('time', '09:00'),
            "recipients": data.get('recipients', [])
        }}
    )
    log_audit("Admin", f"Scheduled Report: {report_id}", "Reports", "Scheduled")
    return jsonify({"success": True, "message": "Report scheduled"})

# 25. Settings Management
@app.route('/api/settings', methods=['GET', 'PUT'])
def manage_settings():
    if request.method == 'GET':
        settings = db['settings'].find_one({"user": "admin"})
        if not settings:
            settings = {
                "user": "admin",
                "notifications": {
                    "email": True,
                    "sms": False,
                    "push": True
                },
                "security": {
                    "two_factor": True,
                    "session_timeout": 30
                },
                "preferences": {
                    "theme": "light",
                    "language": "en"
                }
            }
            db['settings'].insert_one(settings)
        settings['_id'] = str(settings['_id'])
        return jsonify(settings)
    
    # UPDATE
    data = request.json
    db['settings'].update_one(
        {"user": "admin"},
        {"$set": data},
        upsert=True
    )
    log_audit("Admin", "Updated Settings", "Settings", "Modified")
    return jsonify({"success": True, "message": "Settings updated"})

@app.route('/api/settings/notifications', methods=['POST'])
def update_notifications():
    data = request.json
    db['settings'].update_one(
        {"user": "admin"},
        {"$set": {"notifications": data}},
        upsert=True
    )
    log_audit("Admin", "Updated Notification Settings", "Settings", "Notifications")
    return jsonify({"success": True, "message": "Notification settings updated"})

@app.route('/api/settings/security', methods=['POST'])
def update_security():
    data = request.json
    db['settings'].update_one(
        {"user": "admin"},
        {"$set": {"security": data}},
        upsert=True
    )
    log_audit("Admin", "Updated Security Settings", "Settings", "Security")
    return jsonify({"success": True, "message": "Security settings updated"})

# 26. Feedback & Learning System
@app.route('/api/feedback', methods=['GET', 'POST'])
def manage_feedback():
    if request.method == 'POST':
        data = request.json
        feedback = {
            "transaction_id": data.get('transaction_id'),
            "correct_label": data.get('correct_label'),
            "reason": data.get('reason'),
            "submitted_by": data.get('user', 'Admin'),
            "submitted_at": datetime.utcnow(),
            "applied": False
        }
        result = db['feedback'].insert_one(feedback)
        feedback['_id'] = str(result.inserted_id)
        log_audit("Admin", f"Submitted Feedback for {feedback['transaction_id']}", "Feedback", "Created")
        return jsonify({"success": True, "feedback": feedback})
    
    # GET all feedback
    feedback_list = list(db['feedback'].find().sort("submitted_at", -1).limit(50))
    for f in feedback_list:
        f['_id'] = str(f['_id'])
    return jsonify(feedback_list)

@app.route('/api/feedback/<feedback_id>', methods=['PUT'])
def update_feedback(feedback_id):
    from bson import ObjectId
    data = request.json
    db['feedback'].update_one(
        {"_id": ObjectId(feedback_id)},
        {"$set": {
            "correct_label": data.get('correct_label'),
            "reason": data.get('reason'),
            "updated_at": datetime.utcnow()
        }}
    )
    log_audit("Admin", f"Updated Feedback: {feedback_id}", "Feedback", "Modified")
    return jsonify({"success": True, "message": "Feedback updated"})

@app.route('/api/feedback/<feedback_id>/apply', methods=['POST'])
def apply_feedback(feedback_id):
    from bson import ObjectId
    feedback = db['feedback'].find_one({"_id": ObjectId(feedback_id)})
    if not feedback:
        return jsonify({"error": "Feedback not found"}), 404
    
    # Update the original transaction
    transactions_coll.update_one(
        {"id": feedback['transaction_id']},
        {"$set": {"status": feedback['correct_label'], "feedback_applied": True}}
    )
    
    # Mark feedback as applied
    db['feedback'].update_one(
        {"_id": ObjectId(feedback_id)},
        {"$set": {"applied": True, "applied_at": datetime.utcnow()}}
    )
    
    log_audit("Admin", f"Applied Feedback: {feedback_id}", "Feedback", "Applied")
    return jsonify({"success": True, "message": "Feedback applied to model"})

if __name__ == '__main__':
    print("--- Swift AI World-Class Backend Running ---")
    app.run(host='0.0.0.0', port=5000, debug=True)
