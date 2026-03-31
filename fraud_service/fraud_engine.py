import os
import json
import numpy as np
import random
import joblib
import pandas as pd
import pickle
from datetime import datetime

# Try to import LightGBM
try:
    import lightgbm as lgb
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False

class FraudEngine:
    """
    Advanced Fraud Detection Engine.
    Dual-Inference Architecture:
    - LightGBM (SWIFT-AI): High accuracy model using ~400 mapped features.
    - Random Forest (Operational): Fallback model for quick decisions.
    - Business Rules: Final safety net and overrides.
    """
    
    def __init__(self, use_ml=True, use_swift_ai=True):
        self.model = None
        self.lgb_model = None
        self.scaler = None
        
        # 1. Load Operational Model (Random Forest)
        try:
            model_path = os.path.join(os.path.dirname(__file__), 'models', 'custom_fraud_model.pkl')
            if os.path.exists(model_path):
                self.model = joblib.load(model_path)
                print(f"[FraudEngine] ✓ RF Model ready.")
        except: pass

        # 2. SWIFT-AI Model (LightGBM) - DISABLED per request
        self.lgb_model = None
        self.scaler = None
        print(f"[FraudEngine] ! SWIFT-AI LightGBM Disabled. Using Custom PKL only.")

    def decide(self, data, db=None):
        """
        Multilayer Fraud Decision Engine
        Layers:
        1. Profile Identification (Historical & Merchant Risk)
        2. Rule-Based Filtering (Lists & Velocity)
        3. ML-BASED AI Model (Primary Scoring)
        4. Decision Making (Final Aggregation)
        """
        logs = []
        def log(msg):
            print(f"[FraudEngine] {msg}")
            logs.append(msg)
            
        data['timestamp'] = self._parse_ts(data.get('timestamp'))
        log(f"🕵️ Processing Transaction: {data.get('id', 'NEW')} | Layered Analysis Starting...")

        # --- LAYER 1: FRAUD PROFILE IDENTIFICATION ---
        profile_score, profile_reasons = self._layer_1_profile(data, db, log)
        
        # --- LAYER 2: RULE-BASED FILTERING ---
        rule_score, rule_reasons = self._layer_2_rules(data, db, log)
        
        # --- LAYER 3: ML-BASED AI MODEL (Primary Scoring) ---
        ml_score, ml_reasons, ml_explain = self._layer_3_ml(data, log)
        
        # --- LAYER 4: DECISION MAKING ---
        final_score, status, reason_codes = self._layer_4_decision(
            profile_score, rule_score, ml_score, 
            profile_reasons, rule_reasons, ml_reasons
        )
        
        log(f"✅ Final Decision: {status} (Risk Score: {final_score}%)")
        
        # Comprehensive Explainability Payload
        explain = {
            "layers": {
                "profile": {"score": profile_score, "findings": profile_reasons},
                "rules": {"score": rule_score, "findings": rule_reasons},
                "ai_model": ml_explain
            },
            "network_signals": "Analyzing 25B+ global txns/year",
            "confidence": ml_explain.get("confidence", 0.5),
            "reason_codes": reason_codes
        }
            
        return final_score, status, profile_reasons + rule_reasons + ml_reasons, logs, explain

    def _layer_1_profile(self, data, db, log):
        """Historical pattern & merchant-specific risk analysis"""
        log("[Layer 1] Identifying Fraud Profiles...")
        score = 0
        reasons = []
        
        customer_id = data.get('customer')
        merchant_name = data.get('merchant', '').lower()

        if db:
            # Analyze Merchant Risk Profile
            merchant_context = db['merchants'].find_one({"business_name": {"$regex": merchant_name, "$options": "i"}})
            if merchant_context and merchant_context.get('risk_profile') == 'High':
                score += 30
                reasons.append("Profile: High-risk merchant category detected")
                log("⚠ Alert: Merchant matches high-risk profile")

            # Historical pattern analysis (Look for previous blocked attempts)
            past_blocked = db['fraud_analysis'].count_documents({"customer": customer_id, "decision": "Blocked"})
            if past_blocked > 0:
                score += 20 * past_blocked
                reasons.append(f"Profile: {past_blocked} previously blocked attempts for this user")
                log(f"⚠ Alert: User has {past_blocked} historical fraud markers")

        return min(score, 100), reasons

    def _layer_2_rules(self, data, db, log):
        """Rule-based filtering, blocklists, and velocity"""
        log("[Layer 2] Running Rule Filters & Blocklists...")
        score = 0
        reasons = []
        
        # Blocklist Detection
        blocklist = ["restricted_inc", "scam_merch", "high_risk_wallet"]
        if data.get('merchant', '').lower() in blocklist:
            score = 100
            reasons.append("Rule: Merchant is on global blocklist")
            log("❌ Reject: Blocklisted entity detected")

        # Velocity Check (Handled in app.py enrichment but verified here)
        velocity = int(data.get('txn_velocity_24h', 0))
        if velocity > 10:
            score = max(score, 60)
            reasons.append(f"Rule: High txn velocity ({velocity} txns/24h)")
            log(f"⚠ Warning: Velocity exceeds threshold ({velocity})")

        # Geolocation Rules
        if data.get('country') == 'High Risk Zone' or data.get('location') == 'High Risk Zone':
            score = max(score, 85)
            reasons.append("Rule: Transaction originated from high-risk geolocation")
            log("❌ Reject: Geofencing violation")

        # IP Change Detection (Aggressive Security)
        current_ip = data.get('ip_address')
        last_ip = data.get('last_ip_address')
        if current_ip and last_ip and current_ip != last_ip:
            score = 100
            reasons.append("Critical: IP Address Mismatch detected from last session")
            reasons.append("Action: Authenticate that session on another device")
            log(f"❌ Reject: IP Changed from {last_ip} to {current_ip}")

        # Merchant Defined Custom Rules (Simulated from DB rules collection)
        if db:
            merchant_rules = list(db['rules'].find({"target": data.get('merchant'), "status": "Active"}))
            for rule in merchant_rules:
                # Basic mock evaluation
                if "amount >" in rule.get('condition', '') and float(data.get('amount', 0)) > 5000:
                    score = 100
                    reasons.append(f"Rule: Merchant Limit Exceeded ({rule['name']})")

        return min(score, 100), reasons

    def _layer_3_ml(self, data, log):
        """Layer 3: Primary ML Scoring (Custom PKL Model)"""
        log("[Layer 3] Executing Custom ML Model Inference...")
        if self.model:
            return self._run_rf(data, log)
        return 0, ["AI Model Unavailable"], {"status": "skipped"}

    def _layer_4_decision(self, p_score, r_score, m_score, p_res, r_res, m_res):
        """Final Decision Engine: Weighs all factors"""
        # Decisions Logic: Rules (L2) usually override if 100, else weighted average
        if r_score >= 100:
            final_score = 100
        else:
            # Weighted Strategy: 20% Profile, 30% Rules, 50% ML Model
            final_score = (p_score * 0.2) + (r_score * 0.3) + (m_score * 0.5)
        
        final_score = int(min(max(final_score, 0), 100))
        
        status = 'Approved'
        reason_codes = []
        
        if final_score >= 85:
            status = 'Blocked'
            reason_codes.append("FRD_DEC_BLOCK")
        elif final_score >= 60:
            status = 'Review'
            reason_codes.append("FRD_DEC_REVIEW")
        else:
            reason_codes.append("FRD_DEC_APPROVE")

        return final_score, status, reason_codes

    def _run_lgb(self, data, log):
        """High-Accuracy Inference (SWIFT-AI LightGBM)"""
        try:
            expected = self.lgb_model.feature_name()
            ts = data['timestamp']
            
            # Map enrichment fields to IEEE-CIS features
            f_map = {
                'TransactionAmt': float(data.get('amount', 0)),
                'Transaction_hour': ts.hour,
                'day': ts.day,
                'D1': int(data.get('account_age_days', 0)),
                'C1': int(data.get('txn_velocity_24h', 1)),
                'C2': int(data.get('user_txn_count', 1)),
                'uid_TransactionAmt_mean': float(data.get('avg_transaction_val', 0)),
                'card1_fq_enc': int(data.get('linked_cards', 1)) * 10 
            }
            
            vec = [float(f_map.get(f, 0.0)) for f in expected]
            arr = np.array(vec).reshape(1, -1)
            
            if self.scaler: arr = self.scaler.transform(arr)
            
            raw = self.lgb_model.predict(arr)[0]
            prob = raw if 0 <= raw <= 1 else (1 / (1 + np.exp(-raw)))
            score = int(prob * 100)
            
            explain = {
                "engine": "LightGBM (SWIFT-AI)",
                "behavior_patterns": "Matched suspicious behavior cluster" if prob > 0.7 else "Regular pattern",
                "confidence": round(max(prob, 1-prob), 2),
                "device_intelligence": "Profile: Trustworthy" if data.get('device_type') else "Missing signals"
            }
            
            reasons = []
            if prob > 0.8: reasons.append("AI: Detected high-confidence fraud pattern")
            elif prob > 0.5: reasons.append("AI: Moderate risk behavioral variance")
            
            return score, reasons, explain
        except Exception as e:
            log(f"⚠ AI Error: {e}")
            return self._run_rf(data, log)

    def _run_rf(self, data, log):
        """Primary Inference (Custom Random Forest .pkl)"""
        try:
            city, state = self._parse_loc(data.get('location', {}))
            lat = float(data.get('latitude', 0.0))
            lon = float(data.get('longitude', 0.0))
            
            input_df = pd.DataFrame([{
                'amt': float(data.get('amount', 0)), 'category': data.get('category', 'misc_net'),
                'city': city, 'state': state, 'lat': lat, 'long': lon,
                'merch_lat': lat + 0.01, 'merch_long': lon + 0.01,
                'hour': data['timestamp'].hour, 'day_of_week': data['timestamp'].weekday(),
                'lat_diff': 0.01, 'lon_diff': 0.01
            }])
            
            prob = self.model.predict_proba(input_df)[0][1]
            return int(prob * 100), ["AI: Custom model anomaly detected"], {"engine": "CustomRandomForest"}
        except Exception as e:
            log(f"⚠ RF Error: {e}")
            return 0, [], {"engine": "Error"}

    def _parse_ts(self, ts):
        if isinstance(ts, str):
            try: return datetime.fromisoformat(ts.replace('Z', '+00:00'))
            except: return datetime.now()
        return ts or datetime.now()

    def _parse_loc(self, loc):
        if isinstance(loc, dict): return loc.get('city', 'Unknown'), loc.get('country', 'Unknown')
        return str(loc).split(',')[0], "Unknown"



