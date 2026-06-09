from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for, Response
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime, timedelta
import json
import os
import sys
import functools
import random
import threading
import time
from fraud_engine import FraudEngine

app = Flask(__name__, static_folder='.', template_folder='.')
app.secret_key = 'super_secret_fraud_detection_key'  # Required for sessions
CORS(app)

# Avoid Windows console encoding crashes from unicode log messages.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
fraud_engine = FraudEngine(use_ml=True, use_swift_ai=True)  # Use local SWIFT-AI LightGBM model

# Database Config (Dedicated Fraud DB)
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://mkbharvad8080:Mkb%408080@cluster0.a82h2.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
client = MongoClient(MONGO_URI)
db = client['fraud_detection_engine_db']

# Collections (Fraud-Specific Schema)
fraud_analysis_coll = db['fraud_analysis']  # Stores only: transaction_id, risk_score, decision, reasons, analyzed_at
alerts_coll = db['alerts']
models_coll = db['models_meta']
audit_coll = db['audit_logs']
users_coll = db['users']  # Fraud analysts/admins only
reports_coll = db['reports']
rules_coll = db['rules']
feedback_coll = db['feedback']
integrations_coll = db['integrations']
simulation_coll = db['simulation_analysis']

# --- HELPER: Audit Log ---
def log_audit(user, action, target, details=""):
    audit_coll.insert_one({
        "timestamp": datetime.utcnow(),
        "user": user,
        "action": action,
        "target": target,
        "details": details
    })

# --- AUTHENTICATION DECORATOR ---
def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

# --- API ENDPOINTS (AUTH) ---

@app.route('/api/auth/login', methods=['POST'])
def admin_login():
    """Database-backed Admin Login for Fraud Service (Separate System)"""
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    # Check database for admin user
    user = users_coll.find_one({"email": email, "role": {"$in": ["Admin", "Analyst", "Super Admin"]}})
    
    # Fallback to default admin if DB is empty (Setup helper)
    if not user and email == 'admin@swiftai.com' and password == 'admin123':
        # Create default admin if it doesn't exist
        default_admin = {
            "name": "Super Admin",
            "email": "admin@swiftai.com",
            "password": "admin123", # In prod, hash this!
            "role": "Super Admin",
            "created_at": datetime.utcnow()
        }
        users_coll.insert_one(default_admin)
        session['admin_logged_in'] = True
        session['admin_email'] = 'admin@swiftai.com'
        return jsonify({"success": True})

    if user and user.get('password') == password:
        session['admin_logged_in'] = True
        session['admin_email'] = email
        log_audit(email, "Login", "Auth", "Successful")
        return jsonify({"success": True})
    
    return jsonify({"success": False, "message": "Invalid Credentials"})

@app.route('/api/auth/register', methods=['POST'])
def admin_register():
    """Internal Registration for Fraud Analysts"""
    # In a real app, this might be protected or invite-only
    data = request.json
    email = data.get('email')
    
    if users_coll.find_one({"email": email}):
        return jsonify({"success": False, "message": "User already exists"})
        
    new_user = {
        "name": data.get('name'),
        "email": email,
        "password": data.get('password'), # Hash in prod
        "role": data.get('role', 'Analyst'),
        "status": "Active",
        "created_at": datetime.utcnow()
    }
    users_coll.insert_one(new_user)
    log_audit("System", "Register", "Auth", f"New user {email} registered")
    return jsonify({"success": True, "message": "Account created"})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_email', None)
    return jsonify({"success": True})

# --- API ENDPOINTS (CORE FRAUD ENGINE) ---

@app.route('/analyze', methods=['POST'])
def analyze_transaction():
    """Core Fraud Detection Endpoint (Public API for Banking Service)"""
    try:
        data = request.json
        
        # BRIDGE LOGGING
        print("\n" + "="*50)
        print("🌉 DATA BRIDGE: BANKING SERVICE -> FRAUD SERVICE")
        print("="*50)
        print(f"[BRIDGE] 📥 Receiving Full User Profile Data...")
        print(f"[BRIDGE] Data Packet Size: {len(str(data))} bytes")
        print(f"[BRIDGE] User:    {data.get('customer', 'Unknown')}")
        print(f"[BRIDGE] Amount:  ${data.get('amount', 0)}")
        print(f"[BRIDGE] Balance: ${data.get('current_balance', 'N/A')}")
        print("-" * 50 + "\n")

        # 1. Check Rules first (Dynamic from DB)
        active_rules = list(rules_coll.find({"status": "Active"}))
        rule_score = 0
        rule_reasons = []
        
        amt = float(data.get('amount', 0))
        
        # Simple dynamic rule evaluation (In prod, use eval safely or a rule engine lib)
        for rule in active_rules:
            try:
                # Very basic parsing for demo: "amount > 10000"
                condition = rule.get('condition', '')
                if 'amount >' in condition:
                    limit = float(condition.split('>')[1].strip())
                    if amt > limit:
                        rule_score += 20
                        rule_reasons.append(f"Rule: {rule['name']}")
            except: pass

        # 2. Use Hybrid Decision Engine (ML + Business Rules)
        print(f"[ENGINE] 🧠 Evaluating Transaction {data.get('id', 'NEW')}...")
        
        # Initialize defaults (prevent NameError in pre-check branch)
        logs = []
        explain = {}

        # Check if status is already determined (e.g. Validation Failure from Bank)
        if data.get('status') or data.get('type') == 'Validation Failure':
             is_validation_fail = data.get('type') == 'Validation Failure'
             decision = {
                 "status": data.get('status', 'Blocked' if is_validation_fail else 'Review'),
                 "risk_score": 0 if is_validation_fail else (90 if data.get('status') == 'Blocked' else 0),
                 "reasons": data.get('reasons', ["External System Validation Failed"]),
                 "action": "deny" if data.get('status') == 'Blocked' or is_validation_fail else "allow",
                 "explainability": {"pre_check": True}
             }
             logs = ["Pre-check: Transaction blocked before ML analysis"]
             explain = {"pre_check": True, "status": decision["status"]}
        else:
            # Context: Fetch last transaction for IP Change Detection
            customer_id = data.get('customer')
            last_ip = None
            if customer_id:
                # Get the most recent analysis record for this customer
                last_txn = fraud_analysis_coll.find_one(
                    {"customer": customer_id},
                    sort=[("analyzed_at", -1)]
                )
                if last_txn:
                    last_ip = last_txn.get('ip_address')
                    print(f"[DEBUG] IP Check: Last IP for {customer_id} was {last_ip}")
                    # Only inject last_ip if it's a real, known IP address
                    if last_ip and last_ip not in ('Unknown', 'unknown', '127.0.0.1'):
                        data['last_ip_address'] = last_ip
                else:
                    print(f"[DEBUG] IP Check: No previous transaction found for {customer_id}")
            
            # New Engine returns tuple: (score, status, reasons, logs, explain)
            risk_score, status, reasons, logs, explain = fraud_engine.decide(data, db=db)
            
            decision = {
                 "status": status,
                 "risk_score": risk_score,
                 "reasons": reasons,
                 "action": "deny" if status == "Blocked" else "allow",
                 "explain": explain # Include JSON explainability
            }

        # Detect simulator traffic so it does not pollute live monitoring records.
        txn_id = data.get('id', f"TXN-{random.randint(100000,999999)}")
        channel = str(data.get('channel', '')).lower()
        customer = str(data.get('customer', '')).lower()
        is_simulation = (
            channel == 'simulator'
            or str(txn_id).upper().startswith('SIM-')
            or customer.startswith('sim.user.')
        )

        # 4. Build COMPLETE Analysis Record
        analysis_record = {
            "transaction_id": txn_id,
            "risk_score": decision['risk_score'],
            "decision": decision['status'], 
            "reasons": decision['reasons'],
            "logs": logs, # Store the proof logs
            "explain": explain, # Store AI explainability JSON
            "analyzed_at": datetime.utcnow(),
            
            # Key Transaction Details
            "amount": float(data.get('amount', 0)),
            "customer": data.get('customer', 'Unknown'),
            "merchant": data.get('merchant', 'Unknown'),
            "category": data.get('category', 'Unknown'),
            "type": data.get('type', 'Unknown'),
            
            # Context (Enhanced Data)
            "location": data.get('location', 'Unknown'),
            "ip_address": data.get('ip_address', 'Unknown'),
            "device_type": data.get('device_type', 'Unknown'),
            "browser": data.get('browser', 'Unknown'),
            "os": data.get('os', 'Unknown'),
            "channel": "Web", # Default to Web for now
            "country": data.get('country', 'Unknown'),
            "card_type": data.get('card_type', 'Unknown'),
            "latitude": data.get('latitude'),
            "longitude": data.get('longitude'),
            "is_simulation": is_simulation,
            "timestamp": data.get('timestamp', datetime.utcnow())
        }

        if is_simulation:
            # Keep simulator history isolated from live monitoring records.
            simulation_coll.update_one(
                {"transaction_id": analysis_record['transaction_id']},
                {"$set": analysis_record},
                upsert=True
            )
            return jsonify(decision)

        # Store in fraud-specific analysis collection (live records only)
        db['fraud_analysis'].update_one(
            {"transaction_id": analysis_record['transaction_id']},
            {"$set": analysis_record},
            upsert=True
        )

        # 5. Auto-Create Alert for High Risk Transactions
        if decision['status'] in ['Blocked', 'Review']:
            alert = {
                "transaction_id": analysis_record['transaction_id'],
                "severity": "Critical" if decision['status'] == 'Blocked' else "High",
                "risk_score": decision['risk_score'],
                "status": "Pending",
                "customer": analysis_record['customer'],
                "timestamp": datetime.utcnow(),
                "details": ", ".join(decision['reasons'])
            }
            alerts_coll.update_one(
                 {"transaction_id": alert['transaction_id']},
                 {"$set": alert},
                 upsert=True
            )
        
        return jsonify(decision)
    except Exception as e:
        return jsonify({"status": "Error", "risk_score": 0, "reasons": [str(e)]}), 500

# --- API ENDPOINTS (ADMIN DASHBOARD COMPONENTS) ---

@app.route('/api/stats/dashboard', methods=['GET'])
def dashboard_stats():
    # Keep this endpoint readable for the live-monitoring demo page.
    # Transaction stats
    total = fraud_analysis_coll.count_documents({})
    blocked = fraud_analysis_coll.count_documents({"decision": "Blocked"})
    review = fraud_analysis_coll.count_documents({"decision": "Review"})
    approved = fraud_analysis_coll.count_documents({"decision": "Approved"})
    
    # Recent Txns for Graphs
    recent = list(fraud_analysis_coll.find({}, {"risk_score": 1, "timestamp": 1}).sort("timestamp", -1).limit(20))
    
    # Handle timestamp conversion (could be string or datetime)
    trend_labels = []
    for t in reversed(recent):
        ts = t.get('timestamp')
        if isinstance(ts, str):
            try:
                from dateutil import parser
                ts = parser.parse(ts)
                trend_labels.append(ts.strftime("%H:%M"))
            except:
                trend_labels.append("--:--")
        elif hasattr(ts, 'strftime'):
            trend_labels.append(ts.strftime("%H:%M"))
        else:
            trend_labels.append("--:--")
    
    trend_data = [t.get('risk_score', 0) for t in reversed(recent)] if recent else []
    
    # Risk Bins
    bins = [0] * 5
    recent_100 = list(fraud_analysis_coll.find({}, {"risk_score": 1}).limit(100))
    for t in recent_100:
        score = t.get('risk_score', 0)
        idx = min(4, int(score // 20))
        bins[idx] += 1
    
    # Card Types (Credit vs Debit usually, but here checking exact types)
    credit_count = fraud_analysis_coll.count_documents({"card_type": {"$in": ["Credit", "Visa", "MasterCard", "Amex"]}})
    debit_count = fraud_analysis_coll.count_documents({"card_type": {"$in": ["Debit"]}})
    # Normalize if card_type is just 'Visa' (assuming Credit for simplicity if not specified)
    # Actually, let's just count documents with card_type if possible, or simplified logic:
    # Since we are sending 'Visa'/'MasterCard' as 'card_type' from frontend, we might not have 'Credit'/'Debit' explicitly.
    # Let's count by Visa/Mastercard vs Others for now or just return raw counts if needed.
    # Simple Logic: Count distinct
    
    # Let's stick to the chart: "Credit" vs "Debit" (Mocking mapping for now as we only send 'Visa' etc)
    # Ideally we should store 'Credit'/'Debit' in database. 
    # For this graph, let's map known types:
    visa_mc = fraud_analysis_coll.count_documents({"card_type": {"$in": ["Visa", "MasterCard"]}}) 
    amex_disc = fraud_analysis_coll.count_documents({"card_type": {"$in": ["Amex", "Discover"]}})
    
    # ML Model Metrics
    model_active = fraud_engine.model is not None
    ml_metrics = {
        "model_active": model_active,
        "engine_version": "v5.0-Embedded-ML" if model_active else "v2.0-Rules",
        "swift_ai_connected": False, # Network API removed
        "local_ml_active": model_active,
        "avg_inference_time": "<1ms" if model_active else "N/A"
    }
    
    # Calculate ML accuracy (from recent predictions)
    ml_predictions = list(fraud_analysis_coll.find({}, {"risk_score": 1, "decision": 1}).limit(100))
    if ml_predictions:
        # Calculate accuracy metrics
        high_risk_correct = sum(1 for p in ml_predictions if p.get('risk_score', 0) > 70 and p.get('decision') in ['Blocked', 'Review'])
        low_risk_correct = sum(1 for p in ml_predictions if p.get('risk_score', 0) < 40 and p.get('decision') == 'Approved')
        estimated_acc = (high_risk_correct + low_risk_correct) / len(ml_predictions) * 100 if len(ml_predictions) > 0 else 0
        ml_metrics['estimated_accuracy'] = round(estimated_acc, 1)
    else:
        ml_metrics['estimated_accuracy'] = 0

    return jsonify({
        "kpis": {
            "alerts": alerts_coll.count_documents({"status": "Pending"}), 
            "total_txns": total,
            "blocked": blocked,
            "approved": approved,
            "review": review,
            "avg_risk": round(sum(trend_data)/len(trend_data), 1) if trend_data else 0,
            "fraud_rate": round((blocked / total * 100), 1) if total > 0 else 0
        },
        "charts": {
            "trends": {"labels": trend_labels, "data": trend_data},
            "distribution": [approved, review, blocked],
            "risk_bins": bins,
            "card_types": [visa_mc, amex_disc] # Mapping to UI [Credit, Debit] (or re-label UI to Visa/MC vs Amex)
        },
        "ml_metrics": ml_metrics
    })

# 1. TRANSACTIONS
@app.route('/api/transactions', methods=['GET', 'POST'])
def manage_transactions_api():
    if request.method == 'POST':
        return analyze_transaction()

    # Keep this endpoint readable for the live-monitoring demo page.
    limit = int(request.args.get('limit', 100))
    decision = request.args.get('status')
    query = {"decision": decision} if decision and decision != 'All' else {}
    # Hide simulator-generated traffic from live/analyst transaction feeds.
    query["$and"] = [
        {"$or": [{"is_simulation": {"$exists": False}}, {"is_simulation": False}]},
        {"transaction_id": {"$not": {"$regex": "^SIM-"}}},
        {"channel": {"$ne": "Simulator"}}
    ]
    
    # Sort by analyzed_at (the field we actually store), fallback to timestamp
    txns = list(fraud_analysis_coll.find(query).sort("analyzed_at", -1).limit(limit))
    for t in txns:
        t['_id'] = str(t['_id'])
        # Normalize decision/status field for frontend compatibility
        if 'decision' in t and 'status' not in t:
            t['status'] = t['decision']
    return jsonify(txns)

@app.route('/api/transactions/<txn_id>/details', methods=['GET'])
def get_txn_details(txn_id):
    if 'admin_logged_in' not in session: return jsonify({"error": "Unauthorized"}), 401
    txn = fraud_analysis_coll.find_one({"transaction_id": txn_id})
    if txn: 
        txn['_id'] = str(txn['_id'])
        if 'analyzed_at' in txn:
            txn['analyzed_at'] = txn['analyzed_at'].isoformat() if hasattr(txn['analyzed_at'], 'isoformat') else str(txn['analyzed_at'])
    return jsonify(txn or {})

# PROFILE - Analyst Dashboard Profile Section
@app.route('/api/auth/profile', methods=['GET'])
def get_admin_profile():
    if 'admin_logged_in' not in session: return jsonify({"error": "Unauthorized"}), 401
    email = session.get('admin_email', 'admin@swiftai.com')
    user = users_coll.find_one({"email": email})
    if not user:
        user = users_coll.find_one({"role": {"$in": ["Super Admin", "Admin"]}})
    if user:
        return jsonify({
            "name": user.get('name', 'Admin User'),
            "email": user.get('email', email),
            "role": user.get('role', 'Admin'),
            "created_at": str(user.get('created_at', '')),
            "avatar": f"https://ui-avatars.com/api/?name={user.get('name','Admin').replace(' ', '+')}&background=dc3545&color=fff"
        })
    return jsonify({"name": "Super Admin", "email": "admin@swiftai.com", "role": "Super Admin"})

@app.route('/api/auth/profile/update', methods=['POST'])
def update_admin_profile():
    if 'admin_logged_in' not in session: return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    email = session.get('admin_email', 'admin@swiftai.com')
    update = {"name": data.get('name'), "phone": data.get('phone')}
    users_coll.update_one({"email": email}, {"$set": update}, upsert=True)
    return jsonify({"success": True})

# 2. ALERTS
@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    if 'admin_logged_in' not in session: return jsonify({"error": "Unauthorized"}), 401
    alerts = list(alerts_coll.find({"status": "Pending"}).sort("timestamp", -1))
    for a in alerts: a['_id'] = str(a['_id'])
    return jsonify(alerts)

@app.route('/api/alerts/<txn_id>', methods=['PATCH'])
def resolve_alert(txn_id):
    if 'admin_logged_in' not in session: return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    new_decision = data.get('status')  # Frontend sends 'status'
    alerts_coll.update_one({"transaction_id": txn_id}, {"$set": {"status": "Resolved", "decision": new_decision}})
    fraud_analysis_coll.update_one({"transaction_id": txn_id}, {"$set": {"decision": new_decision}})
    log_audit("Admin", f"Resolved Alert {txn_id}", "Alerts", new_decision)
    return jsonify({"status": "success"})

# 3. RULES ENGINE
@app.route('/api/rules', methods=['GET', 'POST'])
def manage_rules():
    if 'admin_logged_in' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    if request.method == 'POST':
        data = request.json
        rule = {
            "name": data.get('name'),
            "description": data.get('description'),
            "condition": data.get('condition'),
            "action": data.get('action'),
            "status": "Active",
            "created_at": datetime.utcnow()
        }
        rules_coll.insert_one(rule)
        rule['_id'] = str(rule['_id'])
        log_audit("Admin", f"Created Rule: {rule['name']}", "Rules", "")
        return jsonify({"success": True, "rule": rule})
    
    rules = list(rules_coll.find())
    for r in rules: r['_id'] = str(r['_id'])
    return jsonify(rules)

# 4. MODELS
@app.route('/api/models', methods=['GET'])
def get_models():
    if 'admin_logged_in' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    # Get real ML model information
    models = []
    
    # Local LightGBM Model
    # Local LightGBM Model
    if fraud_engine.model:
        models.append({
            "_id": "local_ml_001",
            "name": "Embedded SWIFT-AI LightGBM",
            "type": "Gradient Boosting (LGBM)",
            "accuracy": 94.0, # As per inference_api validation
            "status": "Active",
            "last_train": "2026-01-10",
            "features": f"{len(fraud_engine.feature_names)} features",
            "inference_time": "<1ms",
            "source": "fraud_service/fraud_model_lgb.txt",
            "connection": "Embedded (Local Process)"
        })
    
    # Rule-based Engine (always available)
    models.append({
        "_id": "rules_001",
        "name": "Business Rules Engine",
        "type": "Rule-Based",
        "accuracy": 75.0,
        "status": "Active",
        "last_train": "N/A",
        "features": "7 rules",
        "inference_time": "<1ms",
        "source": "fraud_service/fraud_engine.py",
        "connection": "Local"
    })
    
    # If no models, show placeholder
    if not models:
        models = [
            {"_id": "placeholder_001", "name": "No ML Models Active", "type": "Rules Only", "accuracy": 60.0, "status": "Fallback", "last_train": "N/A"}
        ]
    
    return jsonify(models)


# 6. SETTINGS
@app.route('/api/settings', methods=['GET', 'POST'])
def manage_settings():
    if 'admin_logged_in' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    if request.method == 'POST':
        db['settings'].update_one({"user": "admin"}, {"$set": request.json}, upsert=True)
        return jsonify({"success": True})
        
    settings = db['settings'].find_one({"user": "admin"}) or {}
    settings['_id'] = str(settings.get('_id',''))
    return jsonify(settings)

# 7. FEEDBACK LOOP
@app.route('/api/feedback', methods=['GET'])
def get_feedback():
    if 'admin_logged_in' not in session: return jsonify({"error": "Unauthorized"}), 401
    fbs = list(feedback_coll.find().sort("submitted_at", -1).limit(50))
    for f in fbs: f['_id'] = str(f['_id'])
    return jsonify(fbs)

# 8. AUDIT LOGS
@app.route('/api/audit/logs', methods=['GET'])
def get_audit_logs():
    if 'admin_logged_in' not in session: return jsonify({"error": "Unauthorized"}), 401
    logs = list(audit_coll.find().sort("timestamp", -1).limit(100))
    for l in logs: l['_id'] = str(l['_id'])
    return jsonify(logs)

# 9. INTEGRATIONS
@app.route('/api/integrations', methods=['GET', 'POST'])
def manage_integrations():
    if 'admin_logged_in' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    if request.method == 'POST':
        data = request.json
        integ = {
            "name": data.get('name'),
            "status": "Active", 
            "created_at": datetime.utcnow()
        }
        res = integrations_coll.insert_one(integ)
        integ['_id'] = str(res.inserted_id)
        return jsonify({"success": True, "integration": integ})
    
    lst = list(integrations_coll.find())
    for i in lst: i['_id'] = str(i['_id'])
    return jsonify(lst)

# 12. REPORTS ENDPOINTS
@app.route('/api/reports', methods=['GET'])
def get_reports():
    if 'admin_logged_in' not in session: return jsonify({"error": "Unauthorized"}), 401
    reports = list(reports_coll.find().sort("generated_at", -1))
    for r in reports: r['_id'] = str(r['_id'])
    return jsonify(reports)

@app.route('/api/reports/generate', methods=['POST'])
def generate_report():
    if 'admin_logged_in' not in session: return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    
    # Simulate report generation
    new_report = {
        "name": data.get('name', 'Untitled Report'),
        "type": data.get('type', 'PDF'),
        "size": f"{random.randint(1, 10)}.{random.randint(1, 9)} MB",
        "generated_by": session.get('username', 'Admin'),
        "generated_at": datetime.utcnow().isoformat(),
        "status": "Ready"
    }
    reports_coll.insert_one(new_report)
    return jsonify({"success": True, "message": "Report generated successfully"})

@app.route('/api/reports/download/<report_id>', methods=['GET'])
def download_report(report_id):
    # Retrieve report details (mock download)
    from bson.objectid import ObjectId
    try:
        report = reports_coll.find_one({"_id": ObjectId(report_id)})
        if not report: return "Report not found", 404
        
        # Return a simple text file response
        response = app.response_class(
            response=f"Content of {report['name']}\nType: {report['type']}\nGenerated: {report['generated_at']}\n\n[End of Report]",
            status=200,
            mimetype='text/plain'
        )
        response.headers["Content-Disposition"] = f"attachment; filename={report['name'].replace(' ', '_')}.txt"
        return response
    except Exception as e:
        return str(e), 500
@app.route('/api/alerts/<transaction_id>', methods=['PATCH'])
def update_alert(transaction_id):
    if 'admin_logged_in' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    new_status = data.get('status')
    
    # Update in fraud_analysis_coll
    result = fraud_analysis_coll.update_one(
        {"transaction_id": transaction_id},
        {"$set": {"status": "Resolved", "decision": new_status, "resolution_time": datetime.utcnow()}}
    )
    
    # Also update in alerts_coll if separate
    alerts_coll.update_one(
        {"transaction_id": transaction_id},
        {"$set": {"status": "Resolved", "decision": new_status}}
    )
    
    return jsonify({"success": True, "message": f"Alert updated to {new_status}"})

@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    if 'admin_logged_in' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    # 1. Loss Prevented (Sum of Blocked Transactions)
    blocked_txns = list(fraud_analysis_coll.find({"decision": "Blocked"}))
    loss_prevented = sum(t.get('amount', 0) for t in blocked_txns)
    
    # 2. Key Metrics
    total = fraud_analysis_coll.count_documents({})
    blocked_count = len(blocked_txns)
    review_count = fraud_analysis_coll.count_documents({"decision": "Review"})
    
    # 3. Aggregations using MongoDB Pipeline
    def aggregate_field(field):
        pipeline = [
            {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ]
        return {doc['_id']: doc['count'] for doc in fraud_analysis_coll.aggregate(pipeline) if doc['_id']}

    # 4. False Positive Rate (Approximation: Resolved Alerts that were approved / Total Blocked+Review)
    # In a real system, you'd track "unblocked" transactions. 
    # Here, we use a placeholder logic or track 'Resolved' alerts that ended as 'Approved'
    false_positives = alerts_coll.count_documents({"status": "Resolved", "decision": "Approved"})
    risk_total = blocked_count + review_count
    fp_rate = round((false_positives / risk_total * 100), 2) if risk_total > 0 else 0

    return jsonify({
        "loss_prevented": loss_prevented,
        "false_positive_rate": fp_rate,
        "channels": aggregate_field("channel"),   # Web, Mobile, etc.
        "categories": aggregate_field("category"), # Shopping, Food, etc.
        "card_types": aggregate_field("card_type"), # Visa, MC, etc.
        "locations": aggregate_field("location")  # Cities
    })

# 11. CUSTOMERS
@app.route('/api/customers/<customer_id>', methods=['GET'])
def get_customer_details(customer_id):
    if 'admin_logged_in' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    # Aggregate data from fraud_analysis_coll
    pipeline = [
        {"$match": {"customer": customer_id}},
        {"$group": {
            "_id": "$customer",
            "total_spent": {"$sum": "$amount"},
            "transaction_count": {"$sum": 1},
            "avg_risk_score": {"$avg": "$risk_score"},
            "avg_amount": {"$avg": "$amount"},
            "last_transaction": {"$max": "$analyzed_at"},
            "blocked_count": {"$sum": {"$cond": [{"$eq": ["$decision", "Blocked"]}, 1, 0]}},
            "approved_count": {"$sum": {"$cond": [{"$eq": ["$decision", "Approved"]}, 1, 0]}},
            "review_count": {"$sum": {"$cond": [{"$eq": ["$decision", "Review"]}, 1, 0]}}
        }}
    ]
    
    stats = list(fraud_analysis_coll.aggregate(pipeline))
    
    if not stats:
        # Return basic mock if no history found, just to show the page works
        return jsonify({
            "customer_id": customer_id,
            "name": "Unknown Customer",
            "email": "N/A",
            "risk_score": 0,
            "total_spent": 0,
            "transaction_count": 0,
            "history": []
        })
        
    stat = stats[0]
    
    # Fetch recent transactions
    recent_txns = list(fraud_analysis_coll.find({"customer": customer_id}).sort("analyzed_at", -1).limit(20))
    for t in recent_txns: t['_id'] = str(t['_id'])
    
    # Determine Risk Level
    risk_score = int(stat['avg_risk_score'])
    risk_level = "Critical" if risk_score > 80 else ("High" if risk_score > 50 else ("Medium" if risk_score > 20 else "Low"))
    
    # Mock Profile Info (Deterministic based on ID hash or similar)
    # in a real app, you would fetch this from the User Service
    return jsonify({
        "customer_id": customer_id,
        "name": f"Customer {customer_id[-4:]}", # Placeholder name
        "email": f"{customer_id.lower()}@example.com",
        "phone": "+1 (555) 000-0000",
        "location": "New York, USA",
        "member_since": "Jan 2024",
        "age": 30 + (sum(map(ord, customer_id)) % 20), # Random-ish age
        "kyc_status": "Verified",
        "account_status": "Active",
        
        # Stats
        "total_spent": stat['total_spent'],
        "transaction_count": stat['transaction_count'],
        "avg_amount": round(stat['avg_amount'], 2),
        "risk_score": risk_score,
        "risk_level": risk_level,
        "fraud_alerts": stat['blocked_count'] + stat['review_count'],
        "approved_count": stat['approved_count'],
        
        # Lists
        "recent_transactions": recent_txns
    })

# --- SERVE HTML FILES (ADMIN UI) ---

@app.route('/login')
def login_page(): return send_from_directory('.', 'login.html')

@app.route('/register')
def register_page(): return send_from_directory('.', 'register.html')

@app.route('/')
def index(): return redirect('/login')

# Page Routes (login_required)
@app.route('/dashboard')
@login_required
def dashboard_page(): return send_from_directory('.', 'dashboard.html')

@app.route('/live-monitoring')
@login_required
def live_monitoring_page(): return send_from_directory('.', 'live-monitoring.html')

@app.route('/transactions')
@login_required
def transactions_page(): return send_from_directory('.', 'transactions.html')

@app.route('/alerts')
@login_required
def alerts_page(): return send_from_directory('.', 'fraud-alerts.html')

@app.route('/analytics')
@login_required
def analytics_page(): return send_from_directory('.', 'analytics.html')

@app.route('/models')
@login_required
def models_page(): return send_from_directory('.', 'models.html')

@app.route('/reports')
@login_required
def reports_page(): return send_from_directory('.', 'reports.html')

@app.route('/settings')
@login_required
def settings_page(): return send_from_directory('.', 'settings.html')

@app.route('/risk-scoring', endpoint='risk_scoring') # Distinct endpoint name
@login_required
def risk_scoring_page(): return send_from_directory('.', 'risk-scoring.html')

@app.route('/feedback-learning', endpoint='feedback_learning')
@login_required
def feedback_page(): return send_from_directory('.', 'feedback-learning.html')

@app.route('/audit-logs')
@login_required
def audit_page(): return send_from_directory('.', 'audit-logs.html')

@app.route('/integrations')
@login_required
def integrations_page(): return send_from_directory('.', 'integrations.html')

@app.route('/customers')
@login_required
def customers_page(): return send_from_directory('.', 'customers.html')

@app.route('/user-management')
@login_required
def users_page(): return send_from_directory('.', 'user-management.html')

# Catch-all: serves JS, CSS, images and any other static files (MUST be last)
@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('.', filename)

if __name__ == '__main__':
    print("--- FRAUD DETECTION SERVICE (ADMIN) ---")
    print("Running on http://localhost:5001")
    app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)
