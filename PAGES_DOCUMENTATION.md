# Swift AI - Fraud Detection System
## Complete Page Structure & Sub-Pages

### 📊 **Main Pages (8 Pages)**

1. **dashboard.html** ✅
   - Real-time KPI cards
   - Interactive Chart.js graphs with options
   - Real Leaflet.js world map with fraud markers
   - Dark/Light mode toggle
   - Responsive Bootstrap 5 design

2. **live-monitoring.html** ✅
   - Live transaction stream table
   - Real-time statistics cards
   - Filter and search options
   - Status indicators

3. **fraud-alerts.html** ✅
   - Tabbed alert categories
   - Priority-based alert cards
   - Action buttons
   - Alert filtering

4. **transactions.html** ✅
   - Transaction list view
   - Risk score indicators
   - Search and filter options

5. **customers.html** ✅
   - Customer profile cards
   - Risk score display
   - Customer details

6. **analytics.html** ✅
   - Fraud trends charts
   - Category breakdown
   - Performance metrics
   - Model performance table

7. **models.html** ✅
   - ML model cards with performance metrics
   - Detection rules table
   - Model configuration options
   - Feature importance display

8. **settings.html** ✅
   - Alert thresholds configuration
   - SLA settings
   - Notification preferences
   - Data retention settings
   - System integrations status

---

### 📄 **Sub-Pages (Detail Pages) - 4 Pages**

#### 1. **transaction-detail.html** ✅
**Purpose:** Detailed view of individual transaction

**Features:**
- Complete transaction information
- Location & device details
- Risk score gauge (Chart.js)
- Fraud indicators with progress bars
- Interactive fraud indicator details (toggle)
- User transaction history chart
- Similar fraud patterns chart
- Action timeline
- **Graph Options:**
  - History chart with 7/30/90 days toggle
  - Real-time data updates

**Links to:**
- customer-detail.html (customer profile)

---

#### 2. **customer-detail.html** ✅
**Purpose:** Comprehensive customer profile

**Features:**
- Customer overview with avatar
- Contact information
- Account statistics
- Risk score and fraud alerts count
- Tabbed interface:
  - Overview tab
  - Behavior tab (with behavioral chart)
  - Devices tab (registered devices list)
  - Locations tab (geographic distribution chart)
- Recent transactions table
- Spending pattern doughnut chart
- **Graph Options:**
  - Behavioral patterns line chart
  - Location distribution bar chart
  - Spending categories doughnut chart

**Links to:**
- transaction-detail.html (from transaction table)

---

#### 3. **alert-detail.html** ✅
**Purpose:** Detailed fraud alert investigation

**Features:**
- Alert information header
- Quick action buttons:
  - Approve Transaction
  - Block & Refund
  - Escalate to Senior
  - Assign to Team
- Risk factors with confidence levels
- Real Leaflet.js map showing transaction location
- ML Model insights:
  - Feature importance chart
  - Similar cases list
- Activity timeline
- Investigation notes section
- **Graph Options:**
  - Feature importance horizontal bar chart
  - Interactive map with markers

**Links to:**
- transaction-detail.html
- customer-detail.html

---

#### 4. **analytics-advanced.html** ✅
**Purpose:** Advanced analytics with multiple visualization options

**Features:**
- Comprehensive filters:
  - Date range selector (7/30/90/365 days + custom)
  - Chart type selector (Line/Bar/Area/Scatter)
  - Category filter
  - Risk level filter
- KPI Cards (4 metrics)
- **7 Interactive Charts:**
  1. Fraud Trends Over Time (toggleable datasets)
  2. Fraud by Category (switchable doughnut/bar)
  3. Hourly Distribution (fraud vs legitimate toggle)
  4. Geographic Distribution (count vs amount toggle)
  5. Risk Score Distribution
  6. Detection Methods (pie chart)
  7. Response Time Analysis
- Export and print functionality
- **Graph Options:**
  - All charts have interactive options
  - Real-time filter updates
  - Chart type switching
  - Dataset toggling

---

### 🎨 **Design Features (All Pages)**

✅ **Dark/Light Mode Toggle**
- Persistent theme (localStorage)
- Smooth transitions
- All pages support both modes

✅ **Real Interactive Maps**
- Leaflet.js integration
- OpenStreetMap tiles
- Clickable markers with popups
- Zoom controls

✅ **Interactive Charts**
- Chart.js for all graphs
- Multiple chart types
- Toggle options
- Real-time updates

✅ **Improved Navigation**
- Centered navbar items
- Better spacing
- Active state indicators
- Responsive design

✅ **Enhanced CTA Buttons**
- Gradient backgrounds
- Box shadows
- Hover animations
- Better typography

---

### 📁 **File Structure**

```
DA/
├── dashboard.html                 # Main dashboard
├── live-monitoring.html          # Live transaction monitoring
├── fraud-alerts.html             # Fraud alerts list
├── transactions.html             # Transactions list
├── customers.html                # Customer profiles list
├── analytics.html                # Analytics & reports
├── models.html                   # ML models management
├── settings.html                 # System settings
│
├── Sub-Pages/
│   ├── transaction-detail.html   # Individual transaction details
│   ├── customer-detail.html      # Individual customer profile
│   ├── alert-detail.html         # Individual alert investigation
│   └── analytics-advanced.html   # Advanced analytics dashboard
│
├── styles/
│   └── new-style.css            # Main stylesheet with dark mode
│
└── Old Files (Previous Design):
    ├── index.html
    ├── js/main.js
    ├── js/pages.js
    ├── js/final-pages.js
    ├── styles/main.css
    ├── styles/components.css
    └── styles/pages.css
```

---

### 🔗 **Page Interconnections**

```
dashboard.html
    ↓
    ├→ live-monitoring.html → transaction-detail.html
    ├→ fraud-alerts.html → alert-detail.html → transaction-detail.html
    ├→ transactions.html → transaction-detail.html → customer-detail.html
    ├→ customers.html → customer-detail.html → transaction-detail.html
    ├→ analytics.html → analytics-advanced.html
    ├→ models.html
    └→ settings.html
```

---

### 📊 **Graph Options Summary**

| Page | Chart Type | Options Available |
|------|-----------|-------------------|
| **dashboard.html** | Line, Doughnut, Bar | Accepted/Refused/Review toggle, All/Credit/Debit toggle |
| **transaction-detail.html** | Gauge, Bar, Doughnut | 7/30/90 days history toggle |
| **customer-detail.html** | Line, Bar, Doughnut | Behavior/Devices/Locations tabs |
| **alert-detail.html** | Horizontal Bar, Map | Feature importance, Interactive map |
| **analytics.html** | Line, Doughnut, Table | Last 24 Hours dropdown |
| **analytics-advanced.html** | Line/Bar/Area/Scatter, Doughnut/Pie, Bar | Date range, Chart type, Category, Risk level filters, Dataset toggles, View switches |

---

### ✨ **Key Features Implemented**

1. ✅ **Dark/Light Mode** - All pages
2. ✅ **Real Interactive Maps** - Dashboard, Alert Detail
3. ✅ **Interactive Charts** - All pages with Chart.js
4. ✅ **Graph Options** - Filters, toggles, date ranges
5. ✅ **Responsive Design** - Bootstrap 5 grid
6. ✅ **Modern UI** - Clean white/dark themes
7. ✅ **Sub-Pages** - 4 detailed view pages
8. ✅ **Navigation** - Improved navbar with better spacing
9. ✅ **CTA Buttons** - Enhanced with gradients and animations
10. ✅ **Breadcrumbs** - On all sub-pages

---

### 🚀 **How to Use**

1. **Start with:** `dashboard.html`
2. **Navigate using:** Top navigation bar
3. **View details:** Click on any transaction/customer/alert
4. **Toggle theme:** Click moon/sun icon in navbar
5. **Filter data:** Use dropdown filters on each page
6. **Switch charts:** Use button groups on analytics pages

---

### 📝 **Total Pages Created**

- **Main Pages:** 8
- **Sub-Pages:** 4
- **Total:** 12 HTML pages
- **All with dark mode support** ✅
- **All with interactive charts** ✅
- **All with graph options** ✅

---

**Created by:** Swift AI Development Team
**Last Updated:** 2026-01-09
**Version:** 2.0 (Complete Redesign)
