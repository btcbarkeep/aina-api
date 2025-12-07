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
    "notes": "Optional justification"
  }
  ```
- **Response:** Created request object
- **Note:** Organization info is automatically included if user is linked to PM/AOAO

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
    "summary": {
      "total_subscriptions": 22,
      "total_active_paid": 12,
      "total_trials": 4
    }
  }
  ```

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
  created_at?: string;
  updated_at?: string;
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
  created_at: string;
  updated_at: string;
}
```

### Access Request
```typescript
interface AccessRequest {
  id: string;
  requester_user_id: string;
  request_type: "building" | "unit";
  building_id?: string;
  unit_id?: string;
  organization_type?: "pm_company" | "aoao_organization";
  organization_id?: string;
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

### Reports
- Public reports: No auth required, sanitized data only
- Dashboard reports: Auth required, full data with role-based filtering
- Reports include AOAO organizations and PM companies assigned to buildings/units

---

## Support

For API issues or questions:
1. Check Swagger UI documentation at `/docs`
2. Review error messages in API responses
3. Check server logs for detailed error information

---

**Last Updated:** December 2025
**API Version:** 1.0.0

