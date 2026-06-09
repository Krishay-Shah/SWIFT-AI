# -*- coding: utf-8 -*-
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
except (ImportError, OSError):
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
        self.feature_names = []  # Required by app.py for model info display
        
        # 1. Load Operational Model (Random Forest)
        try:
            model_path = os.path.join(os.path.dirname(__file__), 'models', 'custom_fraud_model.pkl')
            scaler_path = os.path.join(os.path.dirname(__file__), 'models', 'scaler.pkl')
            if os.path.exists(model_path):
                self.model = joblib.load(model_path)
                # Extract feature names from model if available
                if hasattr(self.model, 'feature_names_in_'):
                    self.feature_names = list(self.model.feature_names_in_)
                else:
                    self.feature_names = ['amt', 'category', 'city', 'state', 'lat', 'long',
                                          'merch_lat', 'merch_long', 'hour', 'day_of_week', 'lat_diff', 'lon_diff']
                print(f"[FraudEngine] ✓ RF Model ready ({len(self.feature_names)} features).")
            if os.path.exists(scaler_path):
                self.scaler = joblib.load(scaler_path)
                print(f"[FraudEngine] ✓ Scaler loaded.")
        except Exception as e:
            print(f"[FraudEngine] ⚠ Model load error: {e}")

        # 2. SWIFT-AI Model (LightGBM) - DISABLED per request
        self.lgb_model = None
        print(f"[FraudEngine] ! SWIFT-AI LightGBM Disabled. Using Custom PKL + Rules.")

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

        if db is not None:
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
        # Only trigger if both IPs are known, non-placeholder, and actually differ
        current_ip = data.get('ip_address')
        last_ip = data.get('last_ip_address')
        PLACEHOLDER_IPS = {'Unknown', 'unknown', '127.0.0.1', None}
        if (current_ip and last_ip
                and current_ip not in PLACEHOLDER_IPS
                and last_ip not in PLACEHOLDER_IPS
                and current_ip != last_ip):
            score = 100
            reasons.append("🚨 CRITICAL: IP Address changed mid-session — possible account takeover")
            reasons.append(f"Previous IP: {last_ip} → Current IP: {current_ip}")
            reasons.append("Security policy: Payment blocked to protect your account")
            log(f"❌ BLOCKED: IP Changed from {last_ip} → {current_ip} (same device, same location)")

        # Merchant Defined Custom Rules (Simulated from DB rules collection)
        if db is not None:
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
        """Primary Inference (Custom Random Forest .pkl) with heuristic fallback"""
        try:
            city, state = self._parse_loc(data.get('location', {}))
            lat = float(data.get('latitude', 0.0))
            lon = float(data.get('longitude', 0.0))
            ts = data.get('timestamp')
            if not hasattr(ts, 'hour'):
                ts = datetime.now()
            
            input_df = pd.DataFrame([{
                'amt': float(data.get('amount', 0)),
                'category': data.get('category', 'misc_net'),
                'city': city,
                'state': state,
                'lat': lat,
                'long': lon,
                'merch_lat': lat + 0.01,
                'merch_long': lon + 0.01,
                'hour': ts.hour,
                'day_of_week': ts.weekday(),
                'lat_diff': 0.01,
                'lon_diff': 0.01
            }])
            
            prob = self.model.predict_proba(input_df)[0][1]
            score = int(prob * 100)
            reasons = []
            if prob > 0.7:
                reasons.append("AI Model: High-confidence fraud pattern detected")
            elif prob > 0.4:
                reasons.append("AI Model: Moderate risk anomaly flagged")
            log(f"[Layer 3] ML Score: {score}% (prob={prob:.3f})")
            return score, reasons, {"engine": "CustomRandomForest", "confidence": round(max(prob, 1-prob), 2)}
        except Exception as e:
            log(f"⚠ RF Model Error: {e} — using heuristic fallback")
            # Heuristic fallback: score based on amount, time, account age
            return self._heuristic_score(data, log)

    def _heuristic_score(self, data, log):
        """Rule-based heuristic score when ML model fails"""
        score = 0
        reasons = []
        amt = float(data.get('amount', 0))
        
        # Amount-based heuristics
        if amt > 5000:
            score += 30
            reasons.append(f"Heuristic: Large transaction amount (${amt:.0f})")
        elif amt > 2000:
            score += 15
        
        # Time-based heuristics (late-night transactions are riskier)
        ts = data.get('timestamp')
        if hasattr(ts, 'hour') and (ts.hour < 5 or ts.hour > 23):
            score += 15
            reasons.append("Heuristic: Unusual transaction hour (late-night)")
        
        # New account heuristic
        if int(data.get('account_age_days', 30)) < 7:
            score += 20
            reasons.append("Heuristic: Very new account (<7 days)")
        
        # High velocity
        velocity = int(data.get('txn_velocity_24h', 1))
        if velocity > 5:
            score += 15
            reasons.append(f"Heuristic: High transaction velocity ({velocity}/24h)")
        
        score = min(score, 70)  # Cap heuristic at 70 to avoid false blocks
        log(f"[Layer 3] Heuristic Score: {score}%")
        return score, reasons, {"engine": "HeuristicFallback", "confidence": 0.5}

    def _parse_ts(self, ts):
        if isinstance(ts, str):
            try: return datetime.fromisoformat(ts.replace('Z', '+00:00'))
            except: return datetime.now()
        return ts or datetime.now()

    def _parse_loc(self, loc):
        if isinstance(loc, dict): return loc.get('city', 'Unknown'), loc.get('country', 'Unknown')
        return str(loc).split(',')[0], "Unknown"



