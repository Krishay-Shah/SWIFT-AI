# Swift AI - Full-Stack Fraud Detection & Real-Time Analytics Platform 🚀

A production-ready, full-stack fraud detection system powered by Machine Learning, adaptive business rules, and real-time transaction monitoring. 

This platform connects a **Customer Banking Core** with a **Fraud Analyst Control Center**, backed by MongoDB and an embedded Python Random Forest classifier.

---

## 🏗️ System Architecture

The project is structured as a dual-microservice architecture communicating via REST APIs:

```
                  ┌─────────────────────────────────────────┐
                  │          Customer Bank Portal           │
                  │   (Port 5000 / swift-bank.vercel.app)   │
                  └────────────────────┬────────────────────┘
                                       │
                         Sends Transaction Payload
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │         Fraud Detection Service         │
                  │  (Port 5001 / swift-fraud.vercel.app)   │
                  └────────────────────┬────────────────────┘
                                       │
                      Decides Risk using Hybrid Engine:
                      - Business Rules & Blocklists
                      - ML Random Forest model (.pkl)
                      - Contextual Session Analysis
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │           MongoDB Databases             │
                  │     (banking_core_db & fraud_db)        │
                  └─────────────────────────────────────────┘
```

### 1. Customer Banking Core (`banking_service`)
* **Role**: Simulates a banking platform where users register, link credit cards, transfer funds, and initiate payments.
* **Technology**: Python Flask, MongoDB (`banking_core_db`), HTML5/CSS3/JavaScript.
* **Key Feature**: Queries the Fraud Detection Service on checkout/payment requests, blocking or holding transactions based on real-time risk scores.

### 2. Fraud Analyst Dashboard (`fraud_service`)
* **Role**: The centralized control panel where fraud analysts manage system rules, view live-transaction tickers, review flagged cases, and monitor ML model performance.
* **Technology**: Python Flask, Scikit-Learn, Joblib, MongoDB (`fraud_detection_engine_db`), HTML5/CSS3.
* **Key Feature**: Hosts the hybrid Decision Engine and exposes the `/analyze` API endpoint.

---

## 🧠 The Hybrid Decision Engine

The platform utilizes a **four-layer decision matrix** to evaluate transactions in under **20ms**:

1. **Profile Identification (Layer 1)**: Analyzes historical customer patterns and looks for existing fraud flags or merchant-specific threat levels stored in MongoDB.
2. **Rule-Based Filtering (Layer 2)**: Evaluates static parameters, global merchant blocklists, extreme transactional velocity limits, geofencing coordinates, and session hijacking flags (e.g. session IP changes).
3. **Machine Learning Model (Layer 3)**: Evaluates transaction metadata (amount, category, hour of day, coordinate difference, etc.) using an embedded **Random Forest Classifier** (`custom_fraud_model.pkl`) to output a probability score.
4. **Heuristic Fallback (Layer 3.5)**: A rule-based backup scoring mechanism that takes over if the primary ML binary libraries are missing or crash.
5. **Final Aggregator (Layer 4)**: Weighs the outputs of the layers (20% Profile, 30% Rules, 50% ML Model) to assign a final Risk Score and status:
   * **Score < 60%**: `Approved`
   * **Score 60% - 84%**: `Review` (staged for analyst verification)
   * **Score ≥ 85%**: `Blocked` (automatic denial)

---

## 🎨 UI/UX Features & Aesthetics

* **Glassmorphic Design**: Modern dark theme dashboard utilizing vibrant accents (Coral Red, Teal, and Yellow) without conventional corporate blues/purples.
* **Real-time Live Ticker**: Feeds transactions dynamically into the analyst's queue.
* **Interactive Rule Builder**: Directly edit active fraud prevention rules from the UI, storing rules instantly in MongoDB.
* **Analytical Graphs**: Chart.js charts showing loss prevention, risk distribution bins, and card-type statistics.

---

## 📁 Repository Structure

```
Swift-AI/
├── banking_service/        # Customer bank portal app
│   ├── app.py              # Flask backend server
│   ├── vercel.json         # Vercel deployment configuration
│   └── requirements.txt    # Service dependencies
├── fraud_service/          # Fraud analyst system & ML engine
│   ├── app.py              # Flask backend server
│   ├── fraud_engine.py     # Hybrid decision engine
│   ├── vercel.json         # Vercel deployment configuration
│   ├── requirements.txt    # Service dependencies (optimized)
│   └── models/
│       ├── custom_fraud_model.pkl  # Trained Random Forest classifier
│       └── scaler.pkl              # Scaler for ML features
├── SWIFT_AI/               # Training pipeline & LightGBM API
│   ├── src/
│   │   ├── feature_eng.py  # Kaggle-inspired user ID creation
│   │   ├── train_model.py  # 5-fold cross-validation pipeline
│   │   └── inference_api.py# API using LightGBM
│   └── README.md           # Model training specific instructions
└── .gitignore              # Configured ignores for pycache, venv, and IDE files
```

---

## 🚀 Local Quickstart

### Prerequisites
* Python 3.10+ installed
* A running MongoDB instance or connection URI (configured by default to a remote database cluster).

### Setup & Launch

1. **Activate the Virtual Environment**:
   ```bash
   # On Windows (PowerShell):
   .venv\Scripts\Activate.ps1
   ```
   
2. **Start the Fraud Service (Port 5001)**:
   ```bash
   cd fraud_service
   python app.py
   ```
   
3. **Start the Banking Service (Port 5000)**:
   ```bash
   cd ../banking_service
   python app.py
   ```

Access the **Bank Portal** at `http://localhost:5000` and the **Fraud Portal** at `http://localhost:5001` (Default credentials: `admin@swiftai.com` / `admin123`).

---

## ☁️ Vercel Deployment

Both services are fully configured for serverless deployment using Vercel.

### Deployment Configuration

Because they are separate microservices with distinct API structures, they must be deployed as **two separate Vercel projects** linked to the same repository:

1. **Fraud Service (`swift-ai-fraud`)**:
   * **Root Directory**: `fraud_service`
   * **Framework Preset**: `Other`
   * **Environment Variables**:
     * `MONGO_URI`: `mongodb+srv://...`

2. **Banking Service (`swift-ai-bank`)**:
   * **Root Directory**: `banking_service`
   * **Framework Preset**: `Other`
   * **Environment Variables**:
     * `MONGO_URI`: `mongodb+srv://...`
     * `FRAUD_API_URL`: `https://[YOUR-FRAUD-SERVICE-URL].vercel.app/analyze`
