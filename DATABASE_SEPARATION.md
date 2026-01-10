# COMPLETE DATABASE & SCHEMA SEPARATION

## Overview
The Banking Service and Fraud Detection Service are now **100% independent** with:
- ✅ Separate Databases
- ✅ Separate Schemas
- ✅ Separate Authentication Systems
- ✅ Zero Code Dependencies
- ✅ API-Only Communication

---

## 1. BANKING SERVICE

### Database
- **Name**: `banking_core_db`
- **Purpose**: Customer-facing banking operations

### Collections & Schema

#### `customers`
```json
{
  "email": "user@example.com",
  "name": "John Doe",
  "phone": "+1234567890",
  "created_at": "2026-01-10T00:00:00Z",
  "verified": true
}
```

#### `merchants`
```json
{
  "email": "merchant@store.com",
  "business_name": "My Store",
  "api_key": "MERCH-123456",
  "created_at": "2026-01-10T00:00:00Z"
}
```

#### `transactions`
```json
{
  "id": "TXN-847291",
  "customer": "user@example.com",
  "merchant": "merchant@store.com",
  "amount": 1500.00,
  "timestamp": "2026-01-10T00:00:00Z",
  "status": "Approved",  // Set by fraud service response
  "payment_method": "credit_card"
}
```

#### `credit_cards`
```json
{
  "customer_email": "user@example.com",
  "card_number": "4532********1234",
  "expiry": "12/26",
  "cvv": "***",
  "linked_at": "2026-01-10T00:00:00Z"
}
```

### Authentication
- **Type**: OTP-based verification
- **Users**: Customers and Merchants
- **Endpoints**: 
  - `/api/auth/send-otp` - Send OTP to email
  - `/api/auth/verify-otp` - Verify and login
  - `/api/merchants/register` - Merchant registration

### API Calls Made
- **To Fraud Service**: `POST {FRAUD_API_URL}/analyze`
  - Sends: `{id, amount, customer, merchant, timestamp, ...}`
  - Receives: `{risk_score, action: "Approved/Review/Blocked", reasons: [...]}`

---

## 2. FRAUD DETECTION SERVICE

### Database
- **Name**: `fraud_detection_engine_db`
- **Purpose**: Fraud analysis and admin operations

### Collections & Schema

#### `fraud_analysis` (Core Collection)
```json
{
  "transaction_id": "TXN-847291",  // Reference to banking txn
  "risk_score": 85,
  "decision": "Blocked",  // Approved/Review/Blocked
  "reasons": ["High amount", "New location"],
  "amount": 1500.00,  // Only for charts
  "timestamp": "2026-01-10T00:00:00Z",
  "analyzed_at": "2026-01-10T00:00:01Z"
}
```
**Note**: Does NOT store customer name, merchant, payment details, etc.

#### `users` (Fraud Analysts/Admins)
```json
{
  "name": "Admin User",
  "email": "admin@swiftai.com",
  "password": "admin123",  // Hash in production
  "role": "Super Admin",  // Admin/Analyst/Super Admin
  "created_at": "2026-01-10T00:00:00Z",
  "status": "Active"
}
```

#### `rules`
```json
{
  "name": "High Amount Block",
  "description": "Block transactions over $10k",
  "condition": "amount > 10000",
  "action": "Block",
  "status": "Active",
  "created_at": "2026-01-10T00:00:00Z"
}
```

#### `alerts`
```json
{
  "transaction_id": "TXN-847291",
  "risk_score": 85,
  "status": "Pending",  // Pending/Resolved
  "timestamp": "2026-01-10T00:00:00Z"
}
```

#### `models_meta`
```json
{
  "name": "Neural Fraud Shield v4",
  "type": "Deep Learning",
  "accuracy": 99.2,
  "status": "Active",
  "last_train": "2026-01-01"
}
```

#### `reports`
```json
{
  "name": "Monthly Risk Report",
  "type": "PDF",
  "generated_at": "2026-01-10T00:00:00Z",
  "status": "Completed"
}
```

#### `feedback`
```json
{
  "transaction_id": "TXN-847291",
  "correct_label": "Approved",
  "reason": "False positive - legitimate customer",
  "submitted_by": "analyst@swiftai.com",
  "submitted_at": "2026-01-10T00:00:00Z"
}
```

#### `integrations`
```json
{
  "name": "Stripe Integration",
  "status": "Active",
  "created_at": "2026-01-10T00:00:00Z"
}
```

#### `audit_logs`
```json
{
  "timestamp": "2026-01-10T00:00:00Z",
  "user": "admin@swiftai.com",
  "action": "Login",
  "target": "Auth",
  "details": "Successful"
}
```

### Authentication
- **Type**: Database-backed username/password
- **Users**: Fraud Analysts and Admins ONLY
- **Endpoints**:
  - `/api/auth/login` - Admin login (checks `users` collection)
  - `/api/auth/register` - Create new analyst account
  - `/api/auth/logout` - Logout

### API Endpoints Exposed
- **Public**: `POST /analyze` - Called by Banking Service
- **Protected** (require admin session):
  - `/api/stats/dashboard` - Dashboard KPIs
  - `/api/transactions` - List analyzed transactions
  - `/api/alerts` - Pending alerts
  - `/api/rules` - Fraud detection rules
  - `/api/models` - ML models
  - `/api/reports` - Generate/download reports
  - `/api/feedback` - Analyst feedback
  - `/api/integrations` - System integrations
  - `/api/audit/logs` - Audit trail

---

## 3. COMMUNICATION FLOW

### Transaction Processing
```
1. Customer makes payment on Banking Service (localhost:5000)
2. Banking Service calls Fraud Service API:
   POST http://localhost:5001/analyze
   Body: {id, amount, customer, merchant, timestamp, ...}
   
3. Fraud Service:
   - Analyzes transaction
   - Stores ONLY: {transaction_id, risk_score, decision, reasons, amount, timestamp}
   - Returns: {risk_score, action, reasons}
   
4. Banking Service:
   - Receives decision
   - Updates transaction status in banking_core_db
   - Shows result to customer
```

### Data Independence
- Banking Service NEVER reads from `fraud_detection_engine_db`
- Fraud Service NEVER reads from `banking_core_db`
- Fraud Service stores minimal data (no customer PII, no payment details)
- Each service can be deployed on separate EC2 instances

---

## 4. DEPLOYMENT CONFIGURATION

### Local Development
```bash
# Banking Service
cd banking_service
python app.py  # Runs on localhost:5000

# Fraud Service
cd fraud_service
python app.py  # Runs on localhost:5001
```

### EC2 Production
```bash
# Banking EC2 Instance
export FRAUD_API_URL="http://<FRAUD_EC2_IP>:5001/analyze"
python app.py

# Fraud EC2 Instance
python app.py  # No env vars needed
```

---

## 5. SECURITY NOTES

### Current Implementation (Development)
- Passwords stored in plaintext
- Hardcoded credentials for initial setup
- No API key authentication between services

### Production Requirements
- Hash all passwords (bcrypt/argon2)
- Add API key authentication for /analyze endpoint
- Use HTTPS for all communication
- Implement rate limiting
- Add request signing/verification
- Use environment variables for all secrets

---

## 6. TESTING INDEPENDENCE

### Test 1: Database Isolation
```bash
# Delete fraud_detection_engine_db
# Banking service should still work (payments fail fraud check)

# Delete banking_core_db
# Fraud service dashboard should still work (no new transactions)
```

### Test 2: Service Isolation
```bash
# Stop fraud service
# Banking service should handle gracefully (fallback to approve/timeout)

# Stop banking service
# Fraud service admin panel should still work
```

---

## SUMMARY

✅ **Separate Databases**: `banking_core_db` vs `fraud_detection_engine_db`
✅ **Separate Schemas**: Different collections, different field names
✅ **Separate Auth**: OTP (banking) vs Username/Password (fraud)
✅ **Separate Users**: Customers/Merchants vs Analysts/Admins
✅ **API-Only Communication**: Single endpoint `/analyze`
✅ **Zero Dependencies**: Each service runs independently
✅ **EC2 Ready**: Environment variable for cross-server communication
