# Real Button Functionality Implementation Guide

## Pages Updated with Real Backend Integration

### 1. **Models Page** (`models.html`) ✅
- **Create Rule Button**: Now creates actual rules in database via `/api/rules`
- **Script Added**: `js/actions.js`
- **Function**: `handleCreateRule()`

### 2. **Reports Page** (`reports.html`)
- **Generate Report Button**: Will call `/api/reports/generate`
- **Export PDF**: Will call `/api/reports/download/<id>`
- **Function**: `SwiftAI.generateReport()`

### 3. **Fraud Alerts Page** (`fraud-alerts.html`)
- **Create Alert Button**: Will call `/api/alerts/create`
- **Export Button**: Will call `/api/export/alerts`
- **Function**: `SwiftAI.createAlert()`, `SwiftAI.exportData()`

### 4. **Live Monitoring Page** (`live-monitoring.html`)
- **Pause/Resume Stream**: Real-time control
- **Export Button**: Will call `/api/export/transactions`
- **Function**: `SwiftAI.toggleStream()`, `SwiftAI.exportData()`

### 5. **Integrations Page** (`integrations.html`)
- **Add Integration Button**: Will call `/api/integrations`
- **Function**: `SwiftAI.addIntegration()`

### 6. **User Management Page** (`user-management.html`)
- **Create Profile**: Will call `/api/users`
- **Block User**: Will call `/api/users/<id>/block`
- **Send Message**: Will call `/api/users/<id>/message`
- **Functions**: `SwiftAI.createProfile()`, `SwiftAI.blockUser()`, `SwiftAI.sendMessage()`

### 7. **Customers Page** (`customers.html`)
- **Create Profile**: Will call `/api/customers/create`
- **Export**: Will call `/api/export/customers`
- **Function**: `SwiftAI.createProfile('customer')`

### 8. **Transaction Detail Page** (`transaction-detail.html`)
- **Export PDF**: Will call `/api/export/transaction`
- **Report Fraud**: Will call `/api/alerts/create`

### 9. **Analytics Page** (`analytics.html`)
- **Export Report**: Will call `/api/reports/generate`
- **Filter Buttons**: Real filtering logic

### 10. **Dashboard Page** (`dashboard.html`)
- **System Advices Buttons**: Already functional (filter by status)
- **Export**: Will call `/api/export/dashboard`

## Backend Endpoints Created

1. `POST /api/rules` - Create detection rule
2. `POST /api/reports/generate` - Generate PDF/Excel report
3. `GET /api/reports` - List all reports
4. `GET /api/reports/download/<id>` - Download report
5. `POST /api/integrations` - Add new integration
6. `POST /api/users` - Create user
7. `POST /api/users/<id>/block` - Block user
8. `POST /api/users/<id>/message` - Send message
9. `POST /api/customers/create` - Create customer profile
10. `POST /api/alerts/create` - Create manual alert
11. `POST /api/export/<type>` - Export data (CSV/PDF/Excel)

## Universal Functions Available (via `SwiftAI` global object)

```javascript
SwiftAI.createRule(formData)
SwiftAI.generateReport(formData)
SwiftAI.exportData(dataType, format, filters)
SwiftAI.createAlert(formData)
SwiftAI.addIntegration(formData)
SwiftAI.createProfile(formData, type)
SwiftAI.blockUser(userId)
SwiftAI.sendMessage(userId, subject, body)
SwiftAI.showActionModal(title, message, fields, onConfirm)
SwiftAI.toggleStream(fetchFunction, intervalMs)
SwiftAI.applyFilters(filterData, fetchFunction)
SwiftAI.showNotification(title, message, type)
```

## Next Steps

1. Add `<script src="js/actions.js"></script>` to all pages
2. Update button onclick handlers to use real functions
3. Test each feature end-to-end
4. Add loading states and error handling
