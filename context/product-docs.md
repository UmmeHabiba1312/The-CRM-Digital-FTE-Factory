# NovaFlow Product Documentation

## Getting Started

### How to create your first workflow
1. Log in to your NovaFlow dashboard at app.novasaas.io
2. Click **"New Workflow"** in the top-right corner
3. Choose a trigger (e.g., "New row in Google Sheets", "Webhook received",
   "New email in Gmail")
4. Add action steps by clicking the **"+"** button
5. Configure each step with the required fields
6. Click **"Test Workflow"** to run a test with sample data
7. Click **"Activate"** to go live

### Supported Triggers
- Webhook (HTTP POST to your unique URL)
- Schedule (every X minutes, daily, weekly, cron)
- Email received (Gmail, Outlook)
- Form submission (Typeform, Google Forms)
- Database row (Airtable, Notion, Google Sheets)
- App events (Stripe payment, HubSpot contact created, Salesforce lead)

---

## Integrations

### Connecting an Integration
1. Go to **Settings → Integrations**
2. Find the app you want to connect
3. Click **"Connect"**
4. Authorize NovaFlow in the OAuth popup
5. The integration will appear as **"Connected"** (green dot)

### Salesforce Integration
- Supports: Contacts, Leads, Opportunities, Accounts, Custom Objects
- Auth method: OAuth 2.0
- Common issue: If "Connected" but not syncing, re-authorize via Settings →
  Integrations → Salesforce → Reconnect
- Field mapping: Use the **"Map Fields"** tab after connecting

### HubSpot Integration
- Supports: Contacts, Companies, Deals, Tickets, Emails
- Auth method: OAuth 2.0
- Webhook triggers available for real-time sync

### Slack Integration
- Supports: Send message, Create channel, Invite user
- Auth method: OAuth 2.0 (Workspace Admin required)
- Common issue: Bot must be invited to the channel before it can post

### Stripe Integration
- Supports: Payment intents, Customers, Subscriptions, Invoices
- Auth method: API Key (Restricted Key recommended)
- Test mode: Use Stripe test keys to build workflows without real charges

### Gmail Integration
- Supports: Send email, Read email, Create draft, Add label
- Auth method: Google OAuth (individual account)
- For team inboxes, use the Workspace Admin account

---

## Workflow Builder

### Conditional Logic (Branches)
- Add a **"Branch"** step after any trigger or action
- Define conditions using the field selector (e.g., `{{trigger.amount}} > 100`)
- Each branch can have its own sequence of actions
- AI Branch: Describe the condition in plain English — NovaFlow interprets it

### Error Handling
- Each step has an **"On Error"** tab
- Options: Stop workflow, Continue, Retry (1–5 times), Send alert
- View error details in **Execution Logs** (left sidebar → Logs)

### Execution Logs
- Access via the left sidebar → **"Logs"**
- Filter by: Status (Success/Error/Running), Date range, Workflow
- Click any execution to see step-by-step trace with inputs/outputs
- Logs are retained for 30 days (Starter), 90 days (Growth+)

---

## Account & Billing

### Changing your plan
1. Go to **Settings → Billing**
2. Click **"Change Plan"**
3. Select the new plan
4. Changes take effect immediately; billing is prorated

### Cancelling your subscription
- Go to **Settings → Billing → Cancel Subscription**
- Data is retained for 30 days after cancellation
- Export your workflows before cancelling via Settings → Export

### Adding team members
1. Go to **Settings → Team**
2. Click **"Invite Member"**
3. Enter their email address
4. They'll receive an invitation email
- Note: Starter plan supports max 3 users; upgrade to Growth for more

### Resetting your password
1. Go to app.novasaas.io/login
2. Click **"Forgot Password"**
3. Enter your email address
4. Check your inbox for the reset link (expires in 1 hour)
5. If no email received, check spam or contact support

---

## API & Webhooks

### API Access (Growth+ plans)
- Base URL: `https://api.novasaas.io/v1`
- Auth: Bearer token (generate in Settings → API Keys)
- Rate limit: 1,000 requests/hour (Growth), 10,000/hour (Business+)
- Full API reference: docs.novasaas.io/api

### Incoming Webhooks
- Each workflow has a unique webhook URL
- Method: POST
- Content-Type: application/json
- Response: 200 OK with `{"execution_id": "..."}`
- Test with: `curl -X POST <webhook_url> -H "Content-Type: application/json"
  -d '{"test": true}'`

### Outgoing Webhooks
- Add an **"HTTP Request"** step to call external APIs
- Supports: GET, POST, PUT, PATCH, DELETE
- Headers, query params, and body configurable

---

## Troubleshooting Common Issues

### Workflow not triggering
1. Check workflow is **Activated** (green status)
2. Verify trigger conditions match your data
3. Check Execution Logs for attempted (but failed) runs
4. For webhook triggers: ensure the correct URL is used
5. For schedule triggers: check timezone settings

### Integration showing "Disconnected"
1. Go to Settings → Integrations → [App] → Reconnect
2. Re-authorize in the OAuth popup
3. If issue persists, revoke access in the third-party app and reconnect

### Data not mapping correctly
1. Open the workflow step and click **"Refresh Fields"**
2. Ensure the source field is not empty in your trigger data
3. Use the **"Test with sample data"** feature to verify mapping

### Workflow stuck in "Running"
1. Check Execution Logs for the stuck execution
2. If running > 5 minutes, it's likely hung — click **"Cancel Execution"**
3. Common cause: HTTP Request step waiting for a slow external API
4. Fix: Add timeout in the HTTP Request step (recommended: 30s)

---

## Security & Compliance

### SOC 2 Type II
NovaFlow is SOC 2 Type II certified. Certificate available on request.

### Data Residency
- Default: US (AWS us-east-1)
- EU residency available on Enterprise plan (GDPR compliant)

### SSO (Enterprise)
- Supports SAML 2.0 (Okta, Azure AD, Google Workspace)
- Contact your CSM to enable

### 2FA
- Enable via Settings → Security → Two-Factor Authentication
- Supported: Authenticator app (TOTP), SMS
