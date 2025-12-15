# Pool Cue - Production TODO Items

This document tracks integration work needed before production deployment.

## 🔴 High Priority (Required for Launch)

### 1. Stripe Integration
**Status:** Stub functions in place, needs real implementation

**Files to update:**
- `app/marketer_system.py` - Lines 171, 616-653
- `app/routes_market.py` - Lines 457-466
- `app/database.py` - Line 3385

**Steps:**
1. Create Stripe account at https://stripe.com
2. Get API keys from Stripe Dashboard
3. Add to `.env`:
   ```
   STRIPE_PUBLIC_KEY=pk_live_xxxxx
   STRIPE_SECRET_KEY=sk_live_xxxxx
   STRIPE_WEBHOOK_SECRET=whsec_xxxxx
   ```
4. Implement `create_checkout_session()` in marketer_system.py
5. Add Stripe webhook handler at `/webhook/stripe`
6. Test with Stripe test keys first

**Pricing to implement:**
- Advertiser campaign credits ($X per 1000 impressions)
- Premium bar features (optional)

---

### 2. SMS/Twilio Integration  
**Status:** Stub functions in place, needs real implementation

**Files to update:**
- `app/database.py` - Line 2182
- `app/routes_twilio.py` - Webhook handlers

**Steps:**
1. Create Twilio account at https://twilio.com
2. Get Account SID, Auth Token, and Phone Number
3. Add to `.env`:
   ```
   TWILIO_ACCOUNT_SID=ACxxxxx
   TWILIO_AUTH_TOKEN=xxxxx
   TWILIO_PHONE_NUMBER=+1234567890
   ```
4. Implement `send_sms_notification()` in database.py
5. Test with Twilio test credentials first

**SMS features to enable:**
- Phone verification codes
- Queue position notifications
- Game reminders

---

## 🟡 Medium Priority (Nice to Have)

### 3. Bar Staff Authentication
**File:** `app/routes_board.py` - Line 59

**Current:** Anyone can access shot caller board
**Needed:** Verify user is bar staff before allowing game result entry

**Implementation:**
- Check if logged-in user has `venue_staff` role for this bar
- Or use a simple PIN code per bar

---

### 4. Pool Night Integration
**File:** `app/routes_board.py` - Line 367

**Current:** Pool nights created but not linked to queue
**Needed:** Show active pool night info on board display

---

## 🟢 Low Priority (Future Features)

### 5. Push Notifications
- iOS push via APNs
- Requires Apple Developer account setup

### 6. Email Service
- Currently using stubs
- Integrate with SendGrid or AWS SES

---

## ✅ Completed Security Items

- [x] SECRET_KEY configured
- [x] Beta backdoors removed  
- [x] Password hashing upgraded to scrypt
- [x] DEBUG=False by default
- [x] Rate limiting installed (flask-limiter)
- [x] CSRF protection installed (flask-wtf)
- [x] Print statements converted to logging
- [x] Bare except blocks fixed

---

*Last updated: December 15, 2025*
