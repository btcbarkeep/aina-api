# N+1 Query Optimization Fixes

## Summary
Fixed all identified N+1 query problems by implementing batch query helpers that fetch related data in a single query instead of making individual queries in loops.

## Issues Fixed

### 1. Contractor Role Enrichment (N+1)
**Problem:** `enrich_contractor_with_roles()` was called in loops, making one database query per contractor.

**Locations:**
- `routers/contractors.py:383` - List contractors endpoint
- `routers/buildings.py:326` - Building contractors endpoint
- `routers/events.py:252` - Event contractors helper
- `routers/documents.py:220` - Document contractors helper
- `routers/uploads.py:447` - Upload document endpoint
- `services/report_generator.py:523, 705` - Report generation

**Solution:**
- Created `batch_enrich_contractors_with_roles()` in `core/contractor_helpers.py`
- Batch fetches all contractor roles in a single query using `.in_("contractor_id", contractor_ids)`
- Updated all list endpoints to use batch function

**Performance Impact:**
- Before: N queries for N contractors
- After: 1 query for all contractors
- Example: 100 contractors = 100 queries → 1 query (100x improvement)

---

### 2. Document Relations Enrichment (N+1)
**Problem:** `enrich_document_with_relations()` was called in loops, making 2 queries per document (units + contractors).

**Locations:**
- `routers/documents.py:430` - List documents endpoint

**Solution:**
- Created `batch_enrich_documents_with_relations()` in `core/batch_helpers.py`
- Batch fetches all document_units and document_contractors in single queries
- Uses `.in_("document_id", document_ids)` for batch fetching

**Performance Impact:**
- Before: 2N queries for N documents (N for units, N for contractors)
- After: 2 queries total (1 for all units, 1 for all contractors)
- Example: 100 documents = 200 queries → 2 queries (100x improvement)

---

### 3. Event Relations Enrichment (N+1)
**Problem:** `enrich_event_with_relations()` was called in loops, making 2 queries per event (units + contractors).

**Locations:**
- `routers/events.py:462` - List events endpoint

**Solution:**
- Created `batch_enrich_events_with_relations()` in `core/batch_helpers.py`
- Batch fetches all event_units and event_contractors in single queries
- Uses `.in_("event_id", event_ids)` for batch fetching

**Performance Impact:**
- Before: 2N queries for N events (N for units, N for contractors)
- After: 2 queries total (1 for all units, 1 for all contractors)
- Example: 100 events = 200 queries → 2 queries (100x improvement)

---

### 4. Document Unit Filtering (N+1)
**Problem:** Document unit access filtering queried `document_units` table for each document in a loop.

**Locations:**
- `routers/documents.py:410-415` - Permission-based filtering
- `services/report_generator.py:477-482` - Report document filtering

**Solution:**
- Batch fetch all `document_units` before the filtering loop
- Build a map of `document_id -> [unit_ids]`
- Use the map during filtering instead of querying

**Performance Impact:**
- Before: N queries for N documents
- After: 1 query for all documents
- Example: 100 documents = 100 queries → 1 query (100x improvement)

---

## Files Created

1. **`core/batch_helpers.py`** - New module with batch enrichment functions:
   - `batch_get_document_relations()` - Batch fetch document units/contractors
   - `batch_get_event_relations()` - Batch fetch event units/contractors
   - `batch_enrich_documents_with_relations()` - Batch enrich documents
   - `batch_enrich_events_with_relations()` - Batch enrich events

2. **Updated `core/contractor_helpers.py`**:
   - Added `batch_get_contractor_roles()` - Batch fetch contractor roles
   - Added `batch_enrich_contractors_with_roles()` - Batch enrich contractors

## Files Modified

1. **`routers/contractors.py`** - Use batch enrichment for list endpoint
2. **`routers/buildings.py`** - Use batch enrichment for contractors
3. **`routers/documents.py`** - Use batch enrichment and batch filtering
4. **`routers/events.py`** - Use batch enrichment for list endpoint
5. **`services/report_generator.py`** - Use batch enrichment and batch filtering

## Performance Improvements

### Example Scenario: List 100 Documents
**Before:**
- 1 query to fetch documents
- 100 queries to fetch document_units (in filtering loop)
- 100 queries to fetch document_units (in enrichment)
- 100 queries to fetch document_contractors
- 100 queries to fetch contractor roles (for each contractor)
- **Total: ~400+ queries**

**After:**
- 1 query to fetch documents
- 1 query to fetch all document_units (for filtering)
- 1 query to fetch all document_units (for enrichment)
- 1 query to fetch all document_contractors
- 1 query to fetch all contractor roles
- **Total: ~5 queries**

**Improvement: 80x reduction in database queries**

---

## Testing Recommendations

1. **Load Testing:** Test list endpoints with large datasets (100+ items)
2. **Query Monitoring:** Monitor database query counts before/after
3. **Response Time:** Measure response times for list endpoints
4. **Memory Usage:** Verify batch operations don't cause memory issues

---

## Notes

- Single-item endpoints (GET by ID, CREATE, UPDATE) still use individual enrichment functions, which is appropriate
- Batch functions handle empty lists gracefully
- All batch functions maintain backward compatibility with existing data structures
- The optimization maintains the same API response format

---

**Status:** ✅ **COMPLETE** - All identified N+1 query issues have been resolved.

