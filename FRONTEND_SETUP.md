# Frontend Setup Guide

This guide provides everything you need to integrate with the Aina Protocol API from your frontend application.

## Table of Contents
1. [Base Configuration](#base-configuration)
2. [Authentication](#authentication)
3. [API Endpoints](#api-endpoints)
4. [Data Models](#data-models)
5. [Error Handling](#error-handling)
6. [Permission System](#permission-system)
7. [Role-Based Features](#role-based-features)
8. [Frontend Implementation Recommendations](#frontend-implementation-recommendations)

---

## Base Configuration

### API Base URL
```
Production: https://app.ainaprotocol.com
Development: (Use your local/development URL)
```

### Content Type
All requests should use:
```
Content-Type: application/json
Accept: application/json
```

### Authentication Header
All authenticated requests require:
```
Authorization: Bearer <access_token>
```

---

## Authentication

### 1. Login
**Endpoint:** `POST /auth/login`

**Request:**
```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

**Usage:**
- Store the `access_token` in localStorage/sessionStorage
- Include it in all subsequent requests as `Authorization: Bearer <token>`
- Token expires based on Supabase JWT settings (typically 1 hour)

### 2. Get Current User
**Endpoint:** `GET /auth/me`

**Response:**
```json
{
  "id": "user-uuid",
  "auth_user_id": "user-uuid",
  "email": "user@example.com",
  "role": "property_manager",
  "full_name": "John Doe",
  "phone": "+1234567890",
  "contractor_id": null,
  "aoao_organization_id": null,
  "pm_company_id": "pm-company-uuid",
  "organization_name": "ABC Property Management",
  "permissions": ["events:read", "events:write", ...]
}
```

**Use this to:**
- Display user info in UI
- Determine available features based on role
- Check organization associations

### 3. Update Profile (Self-Service)
**Endpoint:** `PATCH /auth/me`

**Request:**
```json
{
  "full_name": "John Doe Updated",
  "phone": "+1234567890"
}
```

**Response:** Updated `CurrentUser` object

**Note:** Users can only update `full_name` and `phone`. Other fields require admin access.

### 4. Password Reset
**Endpoint:** `POST /auth/initiate-password-setup`

**Request:**
```json
{
  "email": "user@example.com"
}
```

**Response:**
```json
{
  "success": true,
  "message": "If an account exists with this email, a password reset link has been sent."
}
```

---

## API Endpoints

### Buildings

#### List Buildings
**Endpoint:** `GET /buildings`
- **Query Params:** `limit` (1-1000, default: 100), `name`, `city`, `offset`
- **Permissions:** `buildings:read`
- **Response:** Array of building objects

#### Get Building
**Endpoint:** `GET /buildings/{building_id}`
- **Permissions:** `buildings:read` + building access check
- **Response:** Single building object

#### Create Building
**Endpoint:** `POST /buildings`
- **Permissions:** `buildings:write`
- **Request Body:** See `BuildingCreate` model
- **Response:** Created building object

#### Update Building
**Endpoint:** `PUT /buildings/{building_id}`
- **Permissions:** `buildings:write` + building access check
- **Request Body:** See `BuildingUpdate` model
- **Response:** Updated building object

#### Delete Building
**Endpoint:** `DELETE /buildings/{building_id}`
- **Permissions:** `buildings:write` (admin only)
- **Response:** `{"status": "deleted"}`

#### Get Building Events
**Endpoint:** `GET /buildings/{building_id}/events`
- **Query Params:** `unit_id`, `event_type`, `severity`, `status`, `limit`
- **Permissions:** `buildings:read` + building access check
- **Response:** Array of event objects

#### Get Building Contractors
**Endpoint:** `GET /buildings/{building_id}/contractors`
- **Permissions:** `buildings:read` + building access check
- **Response:** Array of contractor objects with event counts

---

### Units

#### List Units
**Endpoint:** `GET /units`
- **Query Params:** `building_id`, `limit` (1-1000, default: 100), `offset`
- **Permissions:** `buildings:read` (filters by user access)
- **Response:** Array of unit objects

#### Get Units for Building
**Endpoint:** `GET /units/building/{building_id}`
- **Query Params:** `limit` (1-1000, default: 100)
- **Permissions:** `buildings:read` + building access check
- **Response:** Array of unit objects

#### Get Unit
**Endpoint:** `GET /units/{unit_id}`
- **Permissions:** `buildings:read` + unit access check
- **Response:** Single unit object

#### Create Unit
**Endpoint:** `POST /units`
- **Permissions:** `buildings:write`
- **Request Body:** See `UnitCreate` model
- **Response:** Created unit object

#### Update Unit
**Endpoint:** `PUT /units/{unit_id}`
- **Permissions:** `buildings:write` + unit access check
- **Request Body:** See `UnitUpdate` model
- **Response:** Updated unit object

#### Delete Unit
**Endpoint:** `DELETE /units/{unit_id}`
- **Permissions:** `buildings:write` (admin only)
- **Response:** `{"status": "deleted"}`

#### Get Unit Events
**Endpoint:** `GET /units/{unit_id}/events`
- **Query Params:** `limit` (1-1000, default: 100)
- **Permissions:** `buildings:read` + unit access check
- **Response:** Array of event objects

#### Get Unit Documents
**Endpoint:** `GET /units/{unit_id}/documents`
- **Query Params:** `limit` (1-1000, default: 100)
- **Permissions:** `buildings:read` + unit access check
- **Response:** Array of document objects

---

### Events

#### List Events
**Endpoint:** `GET /events`
- **Query Params:** `building_id`, `unit_id`, `event_type`, `severity`, `status`, `limit`, `offset`
- **Permissions:** `events:read` (filters by user access)
- **Response:** Array of event objects

#### Get Event
**Endpoint:** `GET /events/{event_id}`
- **Permissions:** `events:read` + event access check
- **Response:** Single event object

#### Create Event
**Endpoint:** `POST /events`
- **Permissions:** `events:write`
- **Request Body:** See `EventCreate` model
- **Response:** Created event object

#### Update Event
**Endpoint:** `PUT /events/{event_id}`
- **Permissions:** `events:write` + event access check
- **Request Body:** See `EventUpdate` model
- **Response:** Updated event object

#### Delete Event
**Endpoint:** `DELETE /events/{event_id}`
- **Permissions:** `events:write` + event access check
- **Response:** `{"status": "deleted"}`

#### Event Comments

**List Comments:** `GET /events/{event_id}/comments`
- **Response:** Array of comment objects

**Add Comment:** `POST /events/{event_id}/comments`
- **Request:** `{"comment": "Comment text"}`
- **Response:** Created comment object

**Update Comment:** `PUT /events/{event_id}/comments/{comment_id}`
- **Request:** `{"comment": "Updated text"}`
- **Response:** Updated comment object

**Delete Comment:** `DELETE /events/{event_id}/comments/{comment_id}`
- **Response:** `{"status": "deleted"}`

---

### Documents

#### List Documents
**Endpoint:** `GET /documents`
- **Query Params:** `building_id`, `unit_id`, `event_id`, `contractor_id`, `is_public`, `limit`, `offset`
- **Permissions:** `documents:read` (filters by user access)
- **Response:** Array of document objects

#### Get Document
**Endpoint:** `GET /documents/{document_id}`
- **Permissions:** `documents:read` + document access check
- **Response:** Single document object

#### Create Document
**Endpoint:** `POST /documents`
- **Permissions:** `documents:write`
- **Request Body:** See `DocumentCreate` model
- **Response:** Created document object

#### Update Document
**Endpoint:** `PUT /documents/{document_id}`
- **Permissions:** `documents:write` + document access check
- **Request Body:** See `DocumentUpdate` model
- **Response:** Updated document object

#### Delete Document
**Endpoint:** `DELETE /documents/{document_id}`
- **Permissions:** `documents:write` + document access check
- **Response:** `{"status": "deleted"}`

#### Upload Document (File Upload)
**Endpoint:** `POST /uploads/documents`
- **Content-Type:** `multipart/form-data`
- **Form Fields:**
  - `file`: File (required)
  - `title`: string (required) - Document title
  - `building_id`: string (optional)
  - `event_id`: string (optional)
  - `unit_ids`: string (optional, comma-separated)
  - `contractor_ids`: string (optional, comma-separated)
  - `category_id`: string (optional, UUID)
  - `subcategory_id`: string (optional, UUID)
  - `is_public`: boolean (optional, default: true)
- **Response:** Created document object with S3 URL

#### Get Document Download URL
**Endpoint:** `GET /uploads/documents/{document_id}/download`
- **Permissions:** `documents:read` + document access check
- **Response:** `{"download_url": "https://...", "expires_in": 3600}`

#### Bulk Upload Documents
**Endpoint:** `POST /documents/bulk`
- **Content-Type:** `multipart/form-data`
- **Form Fields:**
  - `file`: File (required, Excel/CSV)
  - `building_id`: string (optional) - Assign to all documents
  - `source`: string (optional) - Source text for all documents
- **Required Columns:** `document_url` (or alternatives: "document url", "document link", "download_link", "download_url")
- **Optional Columns:** `title`, `project_name`, `description`, `tmk`, `permit_number`, `permit_type`, `document_type`
- **Response:** `{"success": true, "total": 10, "created": 8, "errors": [...]}`
- **Note:** All bulk upload documents are automatically set to `is_public=true`

#### Manual PDF Redaction
**Endpoint:** `POST /documents/redact-manual`
- **Content-Type:** `multipart/form-data`
- **Permissions:** `upload:write`
- **Form Fields:**
  - `file`: PDF file (required)
  - `redaction_boxes`: JSON string (required) - Array of redaction box coordinates
- **Redaction Box Format:**
  ```json
  [
    {
      "page": 1,
      "x": 100.5,
      "y": 200.3,
      "width": 150.0,
      "height": 30.0
    }
  ]
  ```
- **Response:**
  ```json
  {
    "document_url": "https://s3.../redacted.pdf",
    "s3_key": "documents/redacted-uuid.pdf",
    "message": "Redactions applied successfully"
  }
  ```
- **Note:** 
  - Coordinates are in PDF coordinate system (backend converts from canvas coordinates)
  - Page numbers are 1-indexed
  - Requires PyMuPDF (fitz) on backend
  - Returns presigned S3 URL valid for 1 day

#### Send Documents via Email
**Endpoint:** `POST /documents/send-email`
- **Permissions:**
  - Admin/Super Admin: Can always send
  - AOAO, Property Manager, Owner, Contractor: Must have active paid subscription (or active trial)
- **Request:**
  ```json
  {
    "document_ids": ["uuid1", "uuid2", "uuid3"],  // Max 5 documents
    "recipient_emails": ["email1@example.com", "email2@example.com"],
    "subject": "Optional custom subject",
    "message": "Optional custom message"
  }
  ```
- **Response:**
  ```json
  {
    "success": true,
    "message": "Documents sent successfully",
    "recipient_count": 2,
    "document_count": 3
  }
  ```
- **Features:**
  - Sends documents as email attachments (if S3 files) or download links
  - Generates presigned URLs valid for 7 days
  - Sends receipt/confirmation email to sender (with HST timestamp)
  - Logs each send in `document_email_logs` table

#### List Document Email Logs
**Endpoint:** `GET /documents/email-logs`
- **Query Params:** `limit` (default: 100), `offset`, `document_id`, `sent_by`
- **Permissions:** Admin/Super Admin only
- **Response:** Array of email log objects

#### Get Document Email Log
**Endpoint:** `GET /documents/email-logs/{log_id}`
- **Permissions:** Admin/Super Admin only
- **Response:** Single email log object with full details

---

### Contractors

#### List Contractors
**Endpoint:** `GET /contractors`
- **Query Params:** `limit` (1-1000, default: 100), `role`, `building_id`, `unit_id`, `search`, `offset`
- **Permissions:** `contractors:read`
- **Response:** Array of contractor objects

#### Get Contractor
**Endpoint:** `GET /contractors/{contractor_id}`
- **Permissions:** `contractors:read`
- **Response:** Single contractor object

#### Create Contractor
**Endpoint:** `POST /contractors`
- **Permissions:** `contractors:write`
- **Request Body:** See `ContractorCreate` model
- **Response:** Created contractor object

#### Update Contractor
**Endpoint:** `PUT /contractors/{contractor_id}`
- **Permissions:** `contractors:write`
- **Request Body:** See `ContractorUpdate` model
- **Response:** Updated contractor object

#### Delete Contractor
**Endpoint:** `DELETE /contractors/{contractor_id}`
- **Permissions:** `contractors:write` (admin only)
- **Response:** `{"status": "deleted"}`

#### Upload Contractor Logo
**Endpoint:** `POST /contractors/{contractor_id}/logo`
- **Content-Type:** `multipart/form-data`
- **Form Fields:** `file`: Image file (required)
- **Response:** Updated contractor object with logo URL

#### Get Contractor Events
**Endpoint:** `GET /contractors/{contractor_id}/events`
- **Query Params:** `building_id`, `unit_id`, `event_type`, `status`, `limit`
- **Permissions:** `contractors:read`
- **Response:** Array of event objects

#### Sync Contractor Subscription
**Endpoint:** `POST /contractors/{contractor_id}/sync-subscription`
- **Permissions:** `contractors:write` (admin only)
- **Response:** Updated contractor subscription info

---

### AOAO Organizations

#### List AOAO Organizations
**Endpoint:** `GET /aoao-organizations`
- **Query Params:** `limit`, `offset`, `search`
- **Permissions:** `buildings:read` (admin) or organization member
- **Response:** Array of AOAO organization objects

#### Get AOAO Organization
**Endpoint:** `GET /aoao-organizations/{organization_id}`
- **Permissions:** `buildings:read` (admin) or organization member
- **Response:** Single AOAO organization object

#### Create AOAO Organization
**Endpoint:** `POST /aoao-organizations`
- **Permissions:** `buildings:write` (admin only)
- **Request Body:** See `AOAOOrganizationCreate` model
- **Response:** Created organization object

#### Update AOAO Organization
**Endpoint:** `PUT /aoao-organizations/{organization_id}`
- **Permissions:** `buildings:write` (admin) or organization member
- **Request Body:** See `AOAOOrganizationUpdate` model
- **Response:** Updated organization object

#### Delete AOAO Organization
**Endpoint:** `DELETE /aoao-organizations/{organization_id}`
- **Permissions:** `buildings:write` (admin only)
- **Response:** `{"status": "deleted"}`

#### Upload AOAO Logo
**Endpoint:** `POST /aoao-organizations/{organization_id}/logo`
- **Content-Type:** `multipart/form-data`
- **Form Fields:** `file`: Image file (required)
- **Response:** Updated organization object with logo URL

#### Sync AOAO Subscription
**Endpoint:** `POST /aoao-organizations/{organization_id}/sync-subscription`
- **Permissions:** `buildings:write` (admin only)
- **Response:** Updated organization subscription info

---

### Property Management Companies

#### List PM Companies
**Endpoint:** `GET /pm-companies`
- **Query Params:** `limit`, `offset`, `search`
- **Permissions:** `buildings:read` (admin) or company member
- **Response:** Array of PM company objects

#### Get PM Company
**Endpoint:** `GET /pm-companies/{company_id}`
- **Permissions:** `buildings:read` (admin) or company member
- **Response:** Single PM company object

#### Create PM Company
**Endpoint:** `POST /pm-companies`
- **Permissions:** `buildings:write` (admin only)
- **Request Body:** See `PMCompanyCreate` model
- **Response:** Created company object

#### Update PM Company
**Endpoint:** `PUT /pm-companies/{company_id}`
- **Permissions:** `buildings:write` (admin) or company member
- **Request Body:** See `PMCompanyUpdate` model
- **Response:** Updated company object

#### Delete PM Company
**Endpoint:** `DELETE /pm-companies/{company_id}`
- **Permissions:** `buildings:write` (admin only)
- **Response:** `{"status": "deleted"}`

#### Upload PM Logo
**Endpoint:** `POST /pm-companies/{company_id}/logo`
- **Content-Type:** `multipart/form-data`
- **Form Fields:** `file`: Image file (required)
- **Response:** Updated company object with logo URL

#### Sync PM Subscription
**Endpoint:** `POST /pm-companies/{company_id}/sync-subscription`
- **Permissions:** `buildings:write` (admin only)
- **Response:** Updated company subscription info

---

### User Access Management

#### List Building Access
**Endpoint:** `GET /user-access/buildings`
- **Permissions:** `user_access:read`
- **Response:** Array of `{user_id, building_id, access_type}` objects
- **Note:** Includes direct access and inherited organization access

#### List Unit Access
**Endpoint:** `GET /user-access/units`
- **Permissions:** `user_access:read`
- **Response:** Array of `{user_id, unit_id, access_type}` objects
- **Note:** Includes direct access and inherited organization access

#### List All Access
**Endpoint:** `GET /user-access/`
- **Permissions:** `user_access:read`
- **Response:** `{buildings: [...], units: [...]}`

#### Organization Building Access

**PM Companies:**
- `GET /user-access/pm-companies/{company_id}/buildings` - List buildings
- `POST /user-access/pm-companies/{company_id}/buildings` - Grant building access
- `DELETE /user-access/pm-companies/{company_id}/buildings/{building_id}` - Remove access

**AOAO Organizations:**
- `GET /user-access/aoao-organizations/{organization_id}/buildings` - List buildings
- `POST /user-access/aoao-organizations/{organization_id}/buildings` - Grant building access
- `DELETE /user-access/aoao-organizations/{organization_id}/buildings/{building_id}` - Remove access

#### Organization Unit Access

**PM Companies:**
- `GET /user-access/pm-companies/{company_id}/units` - List units (includes units from buildings)
- `POST /user-access/pm-companies/{company_id}/units` - Grant direct unit access
- `DELETE /user-access/pm-companies/{company_id}/units/{unit_id}` - Remove access

**AOAO Organizations:**
- `GET /user-access/aoao-organizations/{organization_id}/units` - List units (includes units from buildings)
- `POST /user-access/aoao-organizations/{organization_id}/units` - Grant direct unit access
- `DELETE /user-access/aoao-organizations/{organization_id}/units/{unit_id}` - Remove access

**Important:** When an organization has building access, they automatically have access to ALL units in that building. The unit access endpoints reflect this.

---

### Messages

#### Send Message
**Endpoint:** `POST /messages/`
- **Request:**
  ```json
  {
    "to_user_id": "user-uuid" | null,  // null = send to admins
    "subject": "Message subject",
    "body": "Message body"
  }
  ```
- **Response:** Created message object
- **Permissions:**
  - Admin/Super Admin: Can message any user
  - Regular users: Can only message admins (to_user_id must be null or an admin user ID)
- **Reply Restrictions:**
  - Regular admin messages: Any user can reply
  - Bulk announcements: Only admins can reply (replies_disabled=true)

#### List Messages
**Endpoint:** `GET /messages/`
- **Query Params:** `unread_only` (boolean, default: false)
- **Response:** Array of message objects (received + sent to admins)

#### List Sent Messages
**Endpoint:** `GET /messages/sent`
- **Response:** Array of messages sent by current user

#### List Admin Messages (Admin Only)
**Endpoint:** `GET /messages/admin`
- **Query Params:** `unread_only` (boolean, default: false)
- **Permissions:** Admin/Super Admin only
- **Response:** Array of all messages sent to admins

#### Get Eligible Recipients
**Endpoint:** `GET /messages/eligible-recipients`
- **Response:**
  ```json
  {
    "eligible_recipients": [
      {
        "id": "user-uuid",
        "email": "user@example.com",
        "full_name": "John Doe",
        "role": "admin"
      }
    ],
    "count": 5
  }
  ```
- **Permissions:**
  - Admin/Super Admin: See all users (except themselves)
  - Regular users: See only admins/super_admins

#### Get Message
**Endpoint:** `GET /messages/{message_id}`
- **Response:** Single message object

#### Mark Message as Read
**Endpoint:** `PATCH /messages/{message_id}/read`
- **Response:** Updated message object with `is_read: true`

#### Delete Message
**Endpoint:** `DELETE /messages/{message_id}`
- **Permissions:** Only sender can delete
- **Response:** `{"status": "deleted", "message_id": "..."}`

#### Send Bulk Message
**Endpoint:** `POST /messages/bulk`
- **Permissions:** AOAO users and Admin/Super Admin only
- **Request:**
  ```json
  {
    "recipient_types": ["contractors", "property_managers", "owners", "aoao"],
    "subject": "Bulk announcement",
    "body": "Message content",
    "building_id": "uuid",  // Optional: Filter by building (or null/omit)
    "unit_id": "uuid"       // Optional: Filter by unit (takes precedence over building_id, or null/omit)
  }
  ```
- **Recipient Types:**
  - `"contractors"`: Users associated with contractors
  - `"property_managers"`: Users associated with PM companies
  - `"owners"`: Users with role 'owner'
  - `"aoao"`: Users with role 'aoao' (**Admin/Super Admin only** - AOAO users cannot include this)
  - Can include multiple types (e.g., `["contractors", "owners", "aoao"]`)
  - **Important:** `recipient_types` must be an array of separate strings: `["property_managers", "owners"]` (not `["property_managers, owners"]`)
- **Filtering:**
  - `building_id`: Optional. Filter recipients to those with access to this building. Set to `null` or omit to send to all.
  - `unit_id`: Optional. Filter recipients to those with access to this unit. Set to `null` or omit to send to all.
  - If no filters provided:
    - AOAO: Uses all buildings/units their organization has access to
    - Admin: Sends to all users matching recipient types (no building/unit filtering)
- **Response:**
  ```json
  {
    "success": true,
    "message": "Bulk message sent to 25 recipients",
    "recipient_count": 25,
    "recipient_types": ["contractors", "owners"],
    "errors": null
  }
  ```
- **Notes:**
  - Replies are disabled for bulk messages (only admins can reply)
  - All bulk messages are automatically marked with `is_bulk: true` for UI display
  - Placeholder values like `"string"` for `building_id`/`unit_id` are automatically converted to `null`

---

### Access Requests

#### Create Access Request
**Endpoint:** `POST /requests/`
- **Request:**
  ```json
  {
    "request_type": "building" | "unit",
    "building_id": "uuid",  // Required for building requests
    "unit_id": "uuid",      // Required for unit requests
    "organization_type": "pm_company" | "aoao_organization",  // Optional
    "organization_id": "uuid",  // Optional
    "notes": "Optional justification"
  }
  ```
- **Response:** Created request object
- **Notes:**
  - Organization info is automatically included if user is linked to PM/AOAO
  - Individual users (owners) can request access to their units (no organization needed)
  - If `organization_type` and `organization_id` are provided, they override user's organization
  - Placeholder values like "string" are automatically cleaned (set to null)

#### List Access Requests
**Endpoint:** `GET /requests/`
- **Query Params:** `status` (pending/approved/rejected), `request_type` (building/unit)
- **Response:** 
  - Regular users: Only their own requests
  - Admins: All requests
- **Response:** Array of request objects

#### Get Access Request
**Endpoint:** `GET /requests/{request_id}`
- **Response:** Single request object

#### Update Access Request (Admin Only)
**Endpoint:** `PATCH /requests/{request_id}`
- **Permissions:** Admin/Super Admin only
- **Request:**
  ```json
  {
    "status": "approved" | "rejected" | "pending",
    "admin_notes": "Optional admin notes"
  }
  ```
- **Response:** Updated request object
- **Note:** When approved, access is automatically granted to the organization

#### Delete Access Request
**Endpoint:** `DELETE /requests/{request_id}`
- **Permissions:** Requester or admin
- **Response:** `{"status": "deleted", "request_id": "..."}`

---

### Subscriptions

#### Get My Subscription
**Endpoint:** `GET /subscriptions/me`
- **Response:** Current user's subscription for their role

#### Sync My Subscription
**Endpoint:** `POST /subscriptions/me/sync`
- **Response:** Updated subscription after syncing with Stripe

#### Start Trial (Self-Service)
**Endpoint:** `POST /subscriptions/me/start-trial`
- **Query Params:** `trial_days` (optional, 1-14 days, default: 14)
- **Response:** Created/updated subscription with trial
- **Note:** Users can only start one trial per role

#### List All Subscriptions (Admin Only)
**Endpoint:** `GET /subscriptions/all`
- **Query Params:** `subscription_tier` (free/paid), `subscription_status`, `subscription_type` (user/contractor/aoao_organization/pm_company)
- **Permissions:** Admin/Super Admin only
- **Response:** `{success: true, total: 15, subscriptions: [...]}`

#### Admin: Grant Trial to User
**Endpoint:** `POST /subscriptions/users/{user_id}/start-trial`
- **Query Params:** `role` (optional), `trial_days` (optional, 1-180 days, default: 180)
- **Permissions:** Admin/Super Admin only
- **Response:** Created/updated subscription

#### Admin: Grant Trial to Contractor
**Endpoint:** `POST /subscriptions/contractors/{contractor_id}/start-trial`
- **Query Params:** `trial_days` (optional, 1-180 days, default: 180)
- **Permissions:** Admin/Super Admin only
- **Response:** `{success: true, contractor_id: "...", subscription_status: "trialing", ...}`

#### Admin: Grant Trial to AOAO Organization
**Endpoint:** `POST /subscriptions/aoao-organizations/{organization_id}/start-trial`
- **Query Params:** `trial_days` (optional, 1-180 days, default: 180)
- **Permissions:** Admin/Super Admin only
- **Response:** `{success: true, organization_id: "...", subscription_status: "trialing", ...}`

#### Admin: Grant Trial to PM Company
**Endpoint:** `POST /subscriptions/pm-companies/{company_id}/start-trial`
- **Query Params:** `trial_days` (optional, 1-180 days, default: 180)
- **Permissions:** Admin/Super Admin only
- **Response:** `{success: true, company_id: "...", subscription_status: "trialing", ...}`

---

### Financials (Super Admin Only)

#### Get Revenue Summary
**Endpoint:** `GET /financials/revenue`
- **Query Params:** `start_date` (ISO format), `end_date` (ISO format)
- **Permissions:** Super Admin only
- **Response:**
  ```json
  {
    "period": {
      "start_date": "2025-12-01T00:00:00+00:00",
      "end_date": "2025-12-31T23:59:59+00:00"
    },
    "subscriptions": {
      "user_subscriptions": {"total": 10, "active_paid": 5, "trials": 2},
      "contractors": {"total": 5, "active_paid": 3, "trials": 1},
      "aoao_organizations": {"total": 3, "active_paid": 2, "trials": 0},
      "pm_companies": {"total": 4, "active_paid": 2, "trials": 1}
    },
    "premium_reports": {
      "total_revenue_cents": 50000,
      "total_revenue_decimal": 500.00,
      "purchase_count": 25,
      "currency": "usd"
    },
    "summary": {
      "total_subscriptions": 22,
      "total_active_paid": 12,
      "total_trials": 4,
      "total_revenue_cents": 50000,
      "total_revenue_decimal": 500.00
    }
  }
  ```
- **Note:** `active_paid` excludes trials (only counts `subscription_tier="paid"` AND `subscription_status="active"`)

#### Get Subscription Breakdown
**Endpoint:** `GET /financials/subscriptions/breakdown`
- **Query Params:** `start_date`, `end_date`, `subscription_type` (user/contractor/aoao_organization/pm_company)
- **Permissions:** Super Admin only
- **Response:** Detailed breakdown of subscriptions with revenue data from Stripe

#### Get Premium Reports Breakdown
**Endpoint:** `GET /financials/premium-reports/breakdown`
- **Query Params:** `start_date`, `end_date`, `report_type` (building/unit/contractor/custom), `payment_status` (pending/paid/failed/refunded)
- **Permissions:** Super Admin only
- **Response:** Array of premium report purchase records with customer details, amounts, and payment status

---

### Reports

#### Public Building Report
**Endpoint:** `GET /reports/public/building/{building_id}`
- **Query Params:** `format` (json/pdf, default: json)
- **No Auth Required**
- **Response:** Building report with sanitized data (public documents only)

#### Dashboard Building Report
**Endpoint:** `GET /reports/dashboard/building/{building_id}`
- **Query Params:** `format` (json/pdf, default: json)
- **Permissions:** `buildings:read` + building access check
- **Response:** Full building report with AOAO/PM data, role-based visibility

#### Public Unit Report
**Endpoint:** `GET /reports/public/unit/{unit_id}`
- **Query Params:** `format` (json/pdf, default: json)
- **No Auth Required**
- **Response:** Unit report with sanitized data

#### Dashboard Unit Report
**Endpoint:** `GET /reports/dashboard/unit/{unit_id}`
- **Query Params:** `format` (json/pdf, default: json)
- **Permissions:** `buildings:read` + unit access check
- **Response:** Full unit report with PM data, role-based visibility

#### Contractor Report
**Endpoint:** `GET /reports/dashboard/contractor/{contractor_id}`
- **Query Params:** `format` (json/pdf, default: json)
- **Permissions:** `contractors:read`
- **Response:** Contractor activity report

#### Custom Report
**Endpoint:** `POST /reports/dashboard/custom`
- **Request:**
  ```json
  {
    "building_id": "uuid",
    "unit_ids": ["uuid1", "uuid2"],
    "contractor_ids": ["uuid1"],
    "start_date": "2025-01-01T00:00:00Z",
    "end_date": "2025-12-31T23:59:59Z",
    "include_documents": true,
    "format": "json"
  }
  ```
- **Permissions:** Based on requested resources
- **Response:** Custom report data

---

### Admin Endpoints

#### List Users
**Endpoint:** `GET /admin/users`
- **Query Params:** `role` (optional)
- **Permissions:** Admin/Super Admin only
- **Response:** Array of user objects

#### Get User
**Endpoint:** `GET /admin/users/{user_id}`
- **Permissions:** Admin/Super Admin only
- **Response:** Single user object with full details

#### Create User
**Endpoint:** `POST /admin/users`
- **Permissions:** Admin/Super Admin only
- **Request Body:** See `AdminCreateUser` model
- **Response:** Created user object

#### Update User
**Endpoint:** `PUT /admin/users/{user_id}`
- **Permissions:** Admin/Super Admin only
- **Request Body:** See `AdminUpdateUser` model
- **Response:** Updated user object

#### Delete User
**Endpoint:** `DELETE /admin/users/{user_id}`
- **Permissions:** Admin/Super Admin only
- **Response:** `{"status": "deleted"}`

---

## Data Models

### Building
```typescript
interface Building {
  id: string;
  name: string;
  address?: string;
  city?: string;
  state?: string;
  zip?: string;
  tmk: number;
  zoning?: string;
  year_built?: number;
  description?: string;
  floors?: number;
  units?: number;
  created_at?: string;
  updated_at?: string;
}
```

### Unit
```typescript
interface Unit {
  id: string;
  building_id: string;
  unit_number: string;
  floor?: string;
  bedrooms?: number;
  bathrooms?: number;
  square_feet?: number;
  owner_name?: string;
  parcel_number?: string;
  created_at?: string;
  updated_at?: string;
}
```

### Event
```typescript
interface Event {
  id: string;
  building_id: string;
  unit_id?: string;
  event_type: "maintenance" | "notice" | "assessment" | "plumbing" | "electrical" | "general" | "Warning";
  severity: "low" | "medium" | "high" | "urgent";
  status: "open" | "in_progress" | "resolved" | "closed";
  title: string;
  body: string;
  occurred_at: string;
  created_by?: string;
  created_at?: string;
  updated_at?: string;
}
```

### Document
```typescript
interface Document {
  id: string;
  building_id: string;
  event_id?: string;
  title: string;  // Required
  filename?: string;  // Auto-generated, may be null
  s3_key?: string;
  document_url?: string;  // For external links
  size_bytes?: number;
  is_redacted?: boolean;
  is_public?: boolean;
  category_id?: string;
  subcategory_id?: string;
  uploaded_by?: string;  // User ID who uploaded
  uploaded_by_role?: string;  // Role of uploader (admin, aoao, property_manager, etc.)
  uploaded_by_name?: string;  // Full name of uploader
  created_at?: string;
  updated_at?: string;
  units?: Unit[];  // Associated units
  contractors?: Contractor[];  // Associated contractors
}
```

### Contractor
```typescript
interface Contractor {
  id: string;
  company_name: string;
  subscription_tier: "free" | "paid";
  subscription_status?: "active" | "canceled" | "past_due" | "trialing" | ...;
  stripe_customer_id?: string;
  stripe_subscription_id?: string;
  logo_url?: string;
  // ... other fields
}
```

### Message
```typescript
interface Message {
  id: string;
  from_user_id: string;
  to_user_id?: string;  // null = admin message
  subject: string;
  body: string;
  is_read: boolean;
  read_at?: string;
  replies_disabled: boolean;  // If true, only admins can reply (bulk announcements)
  is_bulk: boolean;  // If true, this is a bulk message/announcement (use for UI announcement bar)
  created_at: string;
  updated_at: string;
}
```

### Document Email Log
```typescript
interface DocumentEmailLog {
  id: string;
  sent_by: string;  // User ID
  document_ids: string[];  // Array of document IDs sent
  recipient_emails: string[];  // Array of recipient email addresses
  subject?: string;  // Custom subject if provided
  message?: string;  // Custom message if provided
  sent_at: string;
  created_at: string;
  updated_at: string;
}
```

### Access Request
```typescript
interface AccessRequest {
  id: string;
  requester_user_id: string;  // Automatically set from authenticated user
  request_type: "building" | "unit";
  building_id?: string;  // Required for building requests
  unit_id?: string;  // Required for unit requests
  organization_type?: "pm_company" | "aoao_organization";  // Optional, auto-filled if user is linked
  organization_id?: string;  // Optional, auto-filled if user is linked
  status: "pending" | "approved" | "rejected";
  notes?: string;
  admin_notes?: string;
  reviewed_by?: string;
  reviewed_at?: string;
  created_at: string;
  updated_at: string;
}
```

### Subscription
```typescript
interface Subscription {
  id: string;
  subscription_type: "user" | "contractor" | "aoao_organization" | "pm_company";
  // User subscription fields
  user_id?: string;
  user_email?: string;
  user_name?: string;
  role?: string;
  // Organization fields
  company_name?: string;
  organization_name?: string;
  // Common fields
  subscription_tier: "free" | "paid";
  subscription_status?: string;
  stripe_customer_id?: string;
  stripe_subscription_id?: string;
  is_trial: boolean;
  trial_started_at?: string;
  trial_ends_at?: string;
  created_at: string;
  updated_at: string;
}
```

---

## Error Handling

### Standard Error Response
All errors follow this format:
```json
{
  "detail": "Error message here"
}
```

### Common HTTP Status Codes
- `200` - Success
- `201` - Created
- `400` - Bad Request (validation error, invalid input)
- `401` - Unauthorized (missing/invalid token)
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found
- `422` - Unprocessable Entity (validation error with details)
- `429` - Too Many Requests (rate limited)
- `500` - Internal Server Error

### Error Examples

**401 Unauthorized:**
```json
{
  "detail": "Invalid or expired authentication token"
}
```

**403 Forbidden:**
```json
{
  "detail": "Insufficient permissions: 'buildings:write' required"
}
```

**404 Not Found:**
```json
{
  "detail": "Building not found"
}
```

**422 Validation Error:**
```json
{
  "detail": [
    {
      "loc": ["body", "name"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## Permission System

### Role-Based Permissions

The API uses a role-based permission system. Each role has specific permissions:

**Super Admin:** `*` (all permissions)

**Admin:** 
- `users:read`, `users:write`, `users:create`, `users:update`, `users:delete`
- `buildings:read`, `buildings:write`
- `events:read`, `events:write`
- `documents:read`, `documents:write`
- `user_access:read`, `user_access:write`
- `contractors:read`, `contractors:write`
- `requests:approve`

**Property Manager:**
- `buildings:read`
- `events:read`, `events:write`
- `documents:read`, `documents:write`
- `contractors:read`
- `user_access:read`, `user_access:write`

**AOAO:**
- `buildings:read`
- `events:read`, `events:write`
- `documents:read`, `documents:write`
- `contractors:read`

**Contractor:**
- `events:read`, `events:write`
- `documents:read`, `documents:write`
- `contractors:read`

**Owner:**
- `events:read`
- `documents:read`
- `buildings:read`

### Checking Permissions

1. **Get current user:** `GET /auth/me` returns user with `role` and `permissions`
2. **Check role:** Use `user.role` to determine available features
3. **Check permissions:** Use `user.permissions` array (admin can grant custom permissions)

### Access Control

Beyond permissions, the API enforces:
- **Building Access:** Users can only access buildings they have explicit or inherited access to
- **Unit Access:** Users can only access units they have explicit or inherited access to
- **Organization Inheritance:** Users inherit building/unit access from their PM company or AOAO organization

---

## Role-Based Features

### Super Admin / Admin
- Full access to all endpoints
- User management (`/admin/users`)
- Financial data (`/financials/revenue`)
- Approve/reject access requests
- Grant trials to any user/organization
- View all subscriptions (`/subscriptions/all`)

### AOAO
- Edit buildings they have access to
- Edit units in their buildings
- Add events to their buildings
- Update status and comment on all events for their buildings
- Add contractors
- Add owners (via admin endpoints)
- Upload documents
- View reports for their buildings
- Send messages to admins
- Request access to new buildings/units

### Property Manager
- Add events to buildings/units they manage
- Comment/update status on events for their managed properties
- Request to manage new buildings/units (`/requests/`)
- Add contractors
- Add owners (via admin endpoints)
- Upload documents
- View reports
- Send messages to admins
- Edit their PM company profile

### Contractor
- Add events to any property
- Comment/update status on their own events only
- View their contractor page
- Edit their contractor account (if they own it)
- Send messages to admins

### Owner
- Edit their unit(s)
- Post/comment/update status on events for their unit only
- View documents for their unit
- Send messages to admins

---

## Dashboard Templates & Features

This section outlines the required features and capabilities for each role's dashboard. Use this as a template when building the frontend dashboards.

### Super Admin / Admin Dashboard

**Note:** Admin is basically the same as Super Admin, but Super Admin has additional access to:
- Financials (`/financials/revenue`, `/financials/subscriptions/breakdown`, `/financials/premium-reports/breakdown`)
- Creating admins/super admins (user management with role assignment)

**Core Features:**
- ✅ Full access to everything else
- ✅ Send announcement to all users (`POST /messages/bulk`)
  - Can filter by `building_id`, `unit_id`, or send to all
  - Can target specific recipient types: `["contractors", "property_managers", "owners"]`
- ✅ User management (`/admin/users`)
- ✅ Approve/reject access requests (`PATCH /requests/{request_id}`)
- ✅ Grant trials to any user/organization (`POST /subscriptions/users/{user_id}/start-trial`, etc.)
- ✅ View all subscriptions (`GET /subscriptions/all`)
- ✅ Financial data (Super Admin only: `/financials/*`)
- ✅ All building/unit/document/event management
- ✅ Reports (all types)

**API Endpoints:**
- `POST /messages/bulk` - Send announcements (no filters = all users)
- `GET /admin/users` - List all users
- `POST /admin/create-account` - Create new users
- `PUT /admin/users/{user_id}` - Update users (including role assignment)
- `GET /financials/revenue` - Revenue summary (Super Admin only)
- `GET /financials/subscriptions/breakdown` - Subscription details (Super Admin only)
- `GET /financials/premium-reports/breakdown` - Premium report purchases (Super Admin only)

---

### AOAO Dashboard

**Core Features:**
- ✅ **Edit Building** - Update building details (`PUT /buildings/{building_id}`)
- ✅ **Edit Units** - Add units (`POST /units`) or request access (`POST /requests/`)
- ✅ **Add Event** - Create events for their buildings (`POST /events`)
- ✅ **Update Event Status** - Update status and comment on all events for their building (`PUT /events/{event_id}`, `POST /events/{event_id}/comments`)
- ✅ **Add Contractor** - Create contractors (`POST /contractors`)
- ✅ **Add Owner** - Via admin endpoints (`POST /admin/create-account` with role="owner")
- ✅ **Upload Documents** - Upload to S3 or create records (`POST /uploads/documents`, `POST /documents`)
- ✅ **Activity Feed** - Aggregate from events and documents (frontend implementation)
- ✅ **Reports** - Building and unit reports (`GET /reports/dashboard/building/{building_id}`, etc.)
- ✅ **Send Document Feature** - Email documents (`POST /documents/send-email`)
  - Requires active paid subscription (or active trial)
  - Can send up to 5 documents
- ✅ **Send Admin a Message** - Message admins (`POST /messages/` with `to_user_id=null` or admin ID)
- ✅ **AOAO Page/Popup** - Edit their organization account (`PUT /aoao-organizations/{organization_id}`)
- ✅ **Send Announcement** - Bulk messaging (`POST /messages/bulk`)
  - Can send to one group or all groups: `["contractors", "property_managers", "owners"]`
  - Automatically filters to users with access to AOAO's buildings/units
  - Can filter by `building_id` or `unit_id` for targeted announcements
- ✅ **Edit/Signup Subscriptions** - Manage organization subscription (`GET /subscriptions/all`, `POST /aoao-organizations/{organization_id}/sync-subscription`)

**API Endpoints:**
- `PUT /buildings/{building_id}` - Edit building
- `POST /units` - Add new unit
- `POST /requests/` - Request access to new buildings/units
- `POST /events` - Create event
- `PUT /events/{event_id}` - Update event status
- `POST /events/{event_id}/comments` - Add comment
- `POST /contractors` - Create contractor
- `POST /uploads/documents` - Upload document file
- `POST /documents` - Create document record
- `GET /documents?building_id={id}` - List documents for activity feed
- `GET /events?building_id={id}` - List events for activity feed
- `GET /reports/dashboard/building/{building_id}` - Building report
- `POST /documents/send-email` - Send documents via email
- `POST /messages/` - Send message to admin
- `PUT /aoao-organizations/{organization_id}` - Edit organization
- `POST /messages/bulk` - Send bulk announcement
- `GET /subscriptions/all?subscription_type=aoao_organization` - View subscription
- `POST /aoao-organizations/{organization_id}/sync-subscription` - Sync with Stripe

---

### Property Manager Dashboard

**Core Features:**
- ✅ **Add Event** - Create events for units/buildings they manage (`POST /events`)
- ✅ **Comment/Update Status** - On events for their managed properties (`PUT /events/{event_id}`, `POST /events/{event_id}/comments`)
- ✅ **Request to Manage** - Request access to new unit or building (`POST /requests/`)
- ✅ **Add Contractor** - Create contractors (`POST /contractors`)
- ✅ **Add Owner** - Via admin endpoints (`POST /admin/create-account` with role="owner")
- ✅ **Upload Documents** - Upload documents (`POST /uploads/documents`, `POST /documents`)
- ✅ **Activity Feed** - Aggregate from events and documents (frontend implementation)
- ✅ **Reports** - Building and unit reports (`GET /reports/dashboard/building/{building_id}`, etc.)
- ✅ **Send Document** - Email documents they have access to (`POST /documents/send-email`)
  - Requires active paid subscription (or active trial)
  - Can send up to 5 documents
- ✅ **Send Admin a Message** - Message admins (`POST /messages/` with `to_user_id=null` or admin ID)
- ✅ **Property Manager Page/Popup** - Edit PM company profile (`PUT /pm-companies/{company_id}`)
- ✅ **Paid Features** - Boost visibility, referrals, badge (frontend display based on subscription tier)
- ✅ **Edit Account** - Self-service profile editing (`PATCH /auth/me`)
- ✅ **Edit/Signup Subscriptions** - Manage company subscription (`GET /subscriptions/all`, `POST /pm-companies/{company_id}/sync-subscription`)

**API Endpoints:**
- `POST /events` - Create event
- `PUT /events/{event_id}` - Update event status
- `POST /events/{event_id}/comments` - Add comment
- `POST /requests/` - Request access to new buildings/units
- `POST /contractors` - Create contractor
- `POST /uploads/documents` - Upload document
- `GET /documents?building_id={id}` - List documents for activity feed
- `GET /events?building_id={id}` - List events for activity feed
- `GET /reports/dashboard/building/{building_id}` - Building report
- `POST /documents/send-email` - Send documents via email
- `POST /messages/` - Send message to admin
- `PUT /pm-companies/{company_id}` - Edit PM company
- `PATCH /auth/me` - Edit own profile (full_name, phone)
- `GET /subscriptions/all?subscription_type=pm_company` - View subscription
- `POST /pm-companies/{company_id}/sync-subscription` - Sync with Stripe

---

### Contractor Dashboard

**Core Features:**
- ✅ **Add Event** - Create events for any property (`POST /events`)
- ✅ **Comment/Update Status** - On their own events only (`PUT /events/{event_id}`, `POST /events/{event_id}/comments`)
  - Can only update events they created (`created_by` matches their user ID)
- ✅ **Contractor Page/Popup** - View and edit contractor profile (`GET /contractors/{contractor_id}`, `PUT /contractors/{contractor_id}`)
- ✅ **Premium Paid Features** - Display premium features based on subscription tier
  - Check `subscription_tier` and `subscription_status` from contractor record
- ✅ **Edit Account** - Upload logo (`POST /contractors/{contractor_id}/logo`), edit profile
- ✅ **Send Admin a Message** - Message admins (`POST /messages/` with `to_user_id=null` or admin ID)
- ✅ **Edit/Signup Subscriptions** - Manage contractor subscription (`GET /subscriptions/all`, `POST /contractors/{contractor_id}/sync-subscription`)

**API Endpoints:**
- `POST /events` - Create event
- `PUT /events/{event_id}` - Update own events only
- `POST /events/{event_id}/comments` - Comment on own events
- `GET /contractors/{contractor_id}` - View contractor profile
- `PUT /contractors/{contractor_id}` - Edit contractor profile
- `POST /contractors/{contractor_id}/logo` - Upload logo
- `POST /messages/` - Send message to admin
- `GET /subscriptions/all?subscription_type=contractor` - View subscription
- `POST /contractors/{contractor_id}/sync-subscription` - Sync with Stripe

**Subscription Check:**
- Contractors have access to all buildings/units by default
- Premium features are UI-based (display based on `subscription_tier === "paid"`)

---

### Owner Dashboard

**Core Features:**
- ✅ **Edit Unit(s)** - Update unit details (`PUT /units/{unit_id}`)
  - Can only edit units they own (check `owner_name` or unit access)
- ✅ **Request Unit Permission** - Request access to their unit (`POST /requests/`)
  - Set `request_type: "unit"` and `unit_id`
  - No organization needed (individual user request)
- ✅ **Post/Comment/Update Status** - On events for their unit only (`POST /events`, `PUT /events/{event_id}`, `POST /events/{event_id}/comments`)
  - Can only interact with events for units they have access to
- ✅ **Message Admin** - Send messages to admins (`POST /messages/` with `to_user_id=null` or admin ID)
- ✅ **Send Documents** - Email documents listed for their unit (`POST /documents/send-email`)
  - Requires active paid subscription (or active trial)
  - Can send up to 5 documents
  - Can only send documents they have access to (unit access check)
- ✅ **Edit/Signup Subscriptions** - Manage user subscription (`GET /subscriptions/me`, `POST /subscriptions/me/start-trial`)

**API Endpoints:**
- `PUT /units/{unit_id}` - Edit unit
- `POST /requests/` - Request unit access
- `POST /events` - Create event (for their unit)
- `PUT /events/{event_id}` - Update event status (for their unit's events)
- `POST /events/{event_id}/comments` - Comment on events (for their unit's events)
- `GET /documents?unit_id={id}` - List documents for their unit
- `POST /documents/send-email` - Send documents via email
- `POST /messages/` - Send message to admin
- `GET /subscriptions/me` - View own subscription
- `POST /subscriptions/me/start-trial` - Start self-service trial (1-14 days)
- `PATCH /auth/me` - Edit own profile (full_name, phone)

**Access Control:**
- Owners can only access units they own or have been granted access to
- Events and documents are filtered by unit access automatically

---

## Dashboard Implementation Checklist

### Common Features Across All Dashboards:
- [ ] Activity Feed (aggregate events + documents, frontend implementation)
- [ ] Messages/Notifications (`GET /messages/`, `GET /messages/eligible-recipients`)
- [ ] Subscription Management (role-specific endpoints)
- [ ] Profile Editing (`PATCH /auth/me` for users, organization-specific endpoints for orgs)

### Role-Specific Features:
- [ ] **Super Admin:** Financials dashboard, user management, bulk messaging
- [ ] **Admin:** Same as Super Admin (except financials)
- [ ] **AOAO:** Building/unit management, bulk messaging to contractors/PMs/owners
- [ ] **Property Manager:** Request management, PM company profile
- [ ] **Contractor:** Contractor profile, logo upload, premium features display
- [ ] **Owner:** Unit editing, document sending, access requests

### Frontend-Only Features (No Backend Endpoint):
- [ ] Activity Feed aggregation (combine `GET /events` and `GET /documents`)
- [ ] Premium features UI display (based on `subscription_tier` and `subscription_status`)
- [ ] Badge/visibility boost UI (contractor premium features)
- [ ] Dashboard widgets and charts (use data from existing endpoints)

---

## Frontend Implementation Recommendations

### 1. Authentication Flow

```typescript
// Login
const login = async (email: string, password: string) => {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  });
  const data = await response.json();
  localStorage.setItem('access_token', data.access_token);
  return data;
};

// Get current user
const getCurrentUser = async () => {
  const token = localStorage.getItem('access_token');
  const response = await fetch(`${API_BASE_URL}/auth/me`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return response.json();
};
```

### 2. API Client Setup

```typescript
class APIClient {
  private baseURL: string;
  private token: string | null;

  constructor(baseURL: string) {
    this.baseURL = baseURL;
    this.token = localStorage.getItem('access_token');
  }

  private async request(endpoint: string, options: RequestInit = {}) {
    const url = `${this.baseURL}${endpoint}`;
    const headers = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      ...(this.token && { 'Authorization': `Bearer ${this.token}` }),
      ...options.headers,
    };

    const response = await fetch(url, { ...options, headers });
    
    if (response.status === 401) {
      // Token expired, redirect to login
      localStorage.removeItem('access_token');
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Request failed');
    }

    return response.json();
  }

  // Example methods
  async getBuildings(params?: any) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/buildings?${query}`);
  }

  async createEvent(data: any) {
    return this.request('/events', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }
}
```

### 3. Activity Feed (Frontend Aggregation)

Since there's no dedicated activity feed endpoint, aggregate from existing endpoints:

```typescript
const getActivityFeed = async (buildingId: string) => {
  const [events, documents] = await Promise.all([
    apiClient.getEvents({ building_id: buildingId, limit: 20 }),
    apiClient.getDocuments({ building_id: buildingId, limit: 20 })
  ]);

  // Combine and sort by date
  const activities = [
    ...events.map(e => ({ type: 'event', ...e, date: e.created_at })),
    ...documents.map(d => ({ type: 'document', ...d, date: d.created_at }))
  ].sort((a, b) => new Date(b.date) - new Date(a.date));

  return activities;
};
```

### 4. Permission Checking

```typescript
const hasPermission = (user: CurrentUser, permission: string): boolean => {
  if (user.role === 'super_admin') return true;
  if (user.permissions?.includes('*')) return true;
  return user.permissions?.includes(permission) || false;
};

// Usage
if (hasPermission(currentUser, 'buildings:write')) {
  // Show edit button
}
```

### 5. Subscription Tier Checking

```typescript
const hasPaidSubscription = (user: CurrentUser): boolean => {
  // Check user subscription
  if (user.subscription_tier === 'paid' && 
      user.subscription_status === 'active') {
    return true;
  }
  
  // Check organization subscription (if applicable)
  // This would require fetching organization subscription
  // or checking it server-side
  
  return false;
};
```

### 6. File Uploads

```typescript
const uploadDocument = async (file: File, metadata: any) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('title', metadata.title);
  if (metadata.building_id) formData.append('building_id', metadata.building_id);
  // ... other fields

  const response = await fetch(`${API_BASE_URL}/uploads/documents`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${localStorage.getItem('access_token')}`
      // Don't set Content-Type, browser will set it with boundary
    },
    body: formData
  });

  return response.json();
};
```

### 7. Manual PDF Redaction Integration

**Reference Implementation:** See `/Users/barryware/Desktop/frontend/` for complete component examples (`RedactionTool.jsx` and `redact.js`).

**Setup:**
```bash
npm install pdfjs-dist
```

**Component Usage:**
```typescript
import RedactionTool from '@/components/RedactionTool';

function RedactPage() {
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  
  const handleRedactionComplete = (result: any) => {
    console.log('Redacted PDF URL:', result.document_url);
    // Redirect or update UI
    router.push('/documents?redactionComplete=true');
  };
  
  return (
    <RedactionTool 
      pdfFile={pdfFile} 
      onRedactionComplete={handleRedactionComplete} 
    />
  );
}
```

**API Integration:**
```typescript
interface RedactionBox {
  page: number;      // 1-indexed page number
  x: number;         // X coordinate (left)
  y: number;         // Y coordinate (top)
  width: number;     // Width of box
  height: number;    // Height of box
}

const applyRedactions = async (file: File, boxes: RedactionBox[]) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('redaction_boxes', JSON.stringify(boxes));
  
  // IMPORTANT: Use full API URL, no /api prefix
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'https://app.ainaprotocol.com';
  const response = await fetch(`${apiUrl}/documents/redact-manual`, {
    method: 'POST',
    headers: {
      // IMPORTANT: Use 'access_token' not 'token'
      'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
      // Don't set Content-Type - browser will set it with boundary for FormData
    },
    body: formData,
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to apply redactions');
  }
  
  return response.json(); // { document_url, s3_key, message }
};
```

**Important Integration Notes:**
1. **API Base URL:** 
   - ❌ Don't use: `/api/documents/redact-manual`
   - ✅ Use: `https://app.ainaprotocol.com/documents/redact-manual` or `${NEXT_PUBLIC_API_URL}/documents/redact-manual`
   - The backend doesn't use `/api` prefix

2. **Authentication Token:**
   - ❌ Don't use: `localStorage.getItem('token')`
   - ✅ Use: `localStorage.getItem('access_token')` (from `/auth/login` response)

3. **Temp File Endpoint:**
   - The `/uploads/temp/{fileId}` endpoint **does not exist** in the backend
   - **Options:**
     - Store file in React state/localStorage temporarily
     - Use `GET /uploads/documents/{document_id}/download` for existing documents
     - Upload file directly without temp storage

4. **Coordinate System:**
   - Frontend uses canvas coordinates (top-left origin)
   - Backend converts to PDF coordinates (bottom-left origin) automatically
   - Page numbers are 1-indexed

5. **File Handling Flow:**
   ```typescript
   // Option 1: Direct upload
   const file = e.target.files[0];
   setPdfFile(file);
   
   // Option 2: Load from existing document
   const loadDocument = async (documentId: string) => {
     const response = await fetch(
       `${API_BASE_URL}/uploads/documents/${documentId}/download`,
       { headers: { 'Authorization': `Bearer ${token}` } }
     );
     const blob = await response.blob();
     const file = new File([blob], 'document.pdf', { type: 'application/pdf' });
     setPdfFile(file);
   };
   ```

**Example Complete Flow:**
```typescript
// 1. User uploads PDF or selects existing document
const [pdfFile, setPdfFile] = useState<File | null>(null);
const [redactions, setRedactions] = useState<RedactionBox[]>([]);

// 2. PDF rendered using pdf.js (see RedactionTool.jsx for implementation)

// 3. User draws boxes on canvas overlay
// Boxes stored in state: [{ page: 1, x: 100, y: 200, width: 150, height: 30 }, ...]

// 4. On submit, send to backend
const handleSubmit = async () => {
  const result = await applyRedactions(pdfFile!, redactions);
  // result: { document_url: "...", s3_key: "...", message: "..." }
  
  // 5. Redirect or update UI
  router.push(`/documents?redactionComplete=true&url=${result.document_url}`);
};
```

### 7. Error Handling

```typescript
const handleAPIError = (error: any) => {
  if (error.status === 401) {
    // Redirect to login
    router.push('/login');
  } else if (error.status === 403) {
    // Show permission denied message
    toast.error('You do not have permission to perform this action');
  } else if (error.status === 404) {
    // Show not found message
    toast.error('Resource not found');
  } else {
    // Show generic error
    toast.error(error.message || 'An error occurred');
  }
};
```

### 8. Real-time Updates (Optional)

For real-time features, consider:
- Polling: Set up intervals to refresh data
- WebSockets: If you add WebSocket support to the backend
- Event-driven: Use browser events to trigger refreshes

---

## Environment Variables

Your frontend should use these environment variables:

```env
VITE_API_BASE_URL=https://app.ainaprotocol.com
# or
REACT_APP_API_BASE_URL=https://app.ainaprotocol.com
# or
NEXT_PUBLIC_API_BASE_URL=https://app.ainaprotocol.com
```

---

## Testing

### Swagger UI
Visit `https://app.ainaprotocol.com/docs` for interactive API documentation.

### Example Requests

**List Buildings:**
```bash
curl -X GET "https://app.ainaprotocol.com/buildings?limit=10" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Create Event:**
```bash
curl -X POST "https://app.ainaprotocol.com/events" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "building_id": "building-uuid",
    "event_type": "maintenance",
    "severity": "medium",
    "status": "open",
    "title": "Plumbing repair needed",
    "body": "Leak in unit 101",
    "occurred_at": "2025-12-07T10:00:00Z"
  }'
```

---

## Document Categories (Frontend Implementation Required)

**Important:** The `categories` router was removed from the backend. The frontend must query the database tables directly or implement a simple endpoint to fetch categories.

### Database Tables

**document_categories:**
- `id` (UUID, primary key)
- `name` (string)

**document_subcategories:**
- `id` (UUID, primary key)
- `name` (string)
- `category_id` (UUID, foreign key to document_categories)

### Frontend Implementation Options

**Option 1: Direct Database Query (Recommended)**
If using Supabase client in frontend:
```typescript
// Fetch categories
const categories = await supabase
  .from('document_categories')
  .select('*');

// Fetch subcategories for a category
const subcategories = await supabase
  .from('document_subcategories')
  .select('*')
  .eq('category_id', categoryId);
```

**Option 2: Create Simple Endpoint**
Add a minimal endpoint in the backend:
```python
@router.get("/categories")
def get_categories():
    # Return categories and subcategories
    # This is a simple read-only endpoint
```

**Option 3: Cache in Frontend**
Fetch categories once on app load and cache them (they rarely change).

### Usage in Document Uploads

When uploading documents, use `category_id` and `subcategory_id` from these tables:
- `POST /uploads/documents` accepts `category_id` and `subcategory_id` (optional)
- `POST /documents` accepts `category_id` and `subcategory_id` (optional)
- Bulk uploads automatically use the "public_documents" category (UUID: `f5ae850f-cc31-44ff-b5bc-ee7d708a0c31`)

---

## Additional Notes

### Subscription Inheritance
- Company subscriptions feed down to users automatically
- Check `check_user_has_active_subscription()` logic in backend
- Users inherit access if their company has a paid subscription

### Building/Unit Access Inheritance
- Users inherit building access from their PM company or AOAO organization
- Users inherit unit access from:
  1. Direct unit access
  2. Units in buildings their organization has access to
- Contractors have access to ALL buildings and units by default

### Trial Limits
- Self-service trials: 1-14 days (default: 14)
- Admin-granted trials: 1-180 days (default: 180)
- Users can only start one self-service trial per role

### Document Uploads
- Use `title` field (required) - `filename` is auto-generated
- For bulk uploads, `filename` can be null (not stored in S3)
- Documents can be linked via `document_url` (external links) or uploaded to S3
- `uploaded_by_role` is automatically set based on user's role (normalized: "admin" for both admin and super_admin)
- `uploaded_by_name` is fetched from user metadata for display purposes

### Reports
- Public reports: No auth required, sanitized data only
- Dashboard reports: Auth required, full data with role-based filtering
- Reports include AOAO organizations and PM companies assigned to buildings/units

### Messaging
- **Regular users** can message admins (set `to_user_id` to admin ID or `null` for all admins)
- **Regular users** can reply to regular admin messages
- **Regular users** cannot reply to bulk announcements (replies_disabled=true)
- **Admins** can message any user
- **AOAO users and Admins** can send bulk messages
- **Admins/Super Admins** can include `"aoao"` in `recipient_types` for bulk messages (AOAO users cannot)
- Bulk messages can be filtered by `building_id` or `unit_id` to target specific recipients
- All bulk messages have `is_bulk: true` - use this to display an "ANNOUNCEMENT" bar in your UI
- Use `GET /messages/eligible-recipients` to show users the current user can message

### Document Email
- **Permissions:** Admin/Super Admin can always send. Other roles require active paid subscription (or active trial)
- **Limits:** Maximum 5 documents per email
- **Features:** Sends as attachments (S3 files) or download links, generates 7-day presigned URLs
- **Receipt:** Sender receives confirmation email with HST timestamp
- **Logging:** All sends are logged in `document_email_logs` table (admin viewable)

### Premium Reports
- Purchases are tracked in `premium_report_purchases` table
- Revenue is included in financials dashboard
- Tracked via Stripe webhooks from ainaprotocol.com

### Manual PDF Redaction
- **Backend Endpoint:** `POST /documents/redact-manual`
- **Frontend Components:** See `/Users/barryware/Desktop/frontend/` for reference implementation
- **Dependencies:** `pdfjs-dist` for PDF rendering
- **Integration Notes:**
  - Use correct API base URL (no `/api` prefix): `https://app.ainaprotocol.com` or `process.env.NEXT_PUBLIC_API_URL`
  - Use `access_token` from login (not `token`): `localStorage.getItem('access_token')`
  - Temp file endpoint (`/uploads/temp/{fileId}`) does not exist - use direct file upload or document download endpoint instead
  - Coordinates are converted from canvas (top-left origin) to PDF (bottom-left origin) in backend
  - Redaction boxes are drawn on canvas overlay, then sent as JSON array

---

## Support

For API issues or questions:
1. Check Swagger UI documentation at `/docs`
2. Review error messages in API responses
3. Check server logs for detailed error information

---

---

## Removed Backend Features (Frontend Implementation Required)

The following features were removed from the backend and need to be implemented in the frontend:

### 1. Document Categories Router (`routers/categories.py`)
- **Status:** Removed from backend
- **Action Required:** Frontend must query `document_categories` and `document_subcategories` tables directly
- **See:** [Document Categories (Frontend Implementation Required)](#document-categories-frontend-implementation-required) section above

### 2. User Access Organization Router (`routers/user_access_org.py`)
- **Status:** Removed from backend
- **Action Required:** Use the unified `/user-access/` endpoints instead:
  - `GET /user-access/pm-companies/{company_id}/buildings`
  - `POST /user-access/pm-companies/{company_id}/buildings`
  - `GET /user-access/aoao-organizations/{organization_id}/buildings`
  - `POST /user-access/aoao-organizations/{organization_id}/buildings`
  - Similar endpoints for units
- **Note:** Organization-level access is now part of the main user-access router

### 3. Contractor Building Access (`migrations/add_contractor_building_access.sql`)
- **Status:** Removed (migration not applied)
- **Action Required:** None - Contractors have access to ALL buildings/units by default
- **Note:** No explicit access management needed for contractors

---

## Recent Updates (December 2025)

### New Features Added

1. **Bulk Message Announcement Flag (`is_bulk`)**
   - **Migration Required:** `migrations/add_is_bulk_to_messages.sql`
   - **Purpose:** Marks bulk messages/announcements for UI display
   - **Usage:** Check `message.is_bulk === true` to display an "ANNOUNCEMENT" bar in your UI
   - **Details:** All messages sent via `POST /messages/bulk` automatically have `is_bulk: true`

2. **AOAO Recipient Type for Bulk Messages**
   - **Feature:** Admins/Super Admins can now include `"aoao"` in `recipient_types` when sending bulk messages
   - **Restriction:** AOAO users themselves cannot include `"aoao"` as a recipient type
   - **Usage:** `{"recipient_types": ["contractors", "property_managers", "owners", "aoao"]}`

3. **Placeholder Value Handling**
   - **Improvement:** Bulk message endpoint now automatically converts placeholder `"string"` values for `building_id`/`unit_id` to `null`
   - **Impact:** Frontend can send `null` or omit these fields instead of placeholder strings

---

**Last Updated:** December 2025
**API Version:** 1.0.0

