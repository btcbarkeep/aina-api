# core/utils/sync_formatter.py

def format_sync_summary(summary: dict, start_time, end_time, duration, title="Manual Sync"):
    """Format unified sync summary for email output."""
    buildings = summary.get("buildings", {})
    events = summary.get("events", {})
    documents = summary.get("documents", {})

    return (
        f"📋 **Aina Protocol {title} Report**\n\n"
        f"🕒 **Summary**\n"
        f"• Start: {start_time}\n"
        f"• End: {end_time}\n"
        f"• Duration: {duration:.2f} seconds\n\n"
        f"🏢 **Buildings Sync**\n"
        f"• Local: {buildings.get('local_total', 'N/A')}\n"
        f"• Supabase: {buildings.get('supa_total', 'N/A')}\n"
        f"• Added → Supabase: {len(buildings.get('inserted_to_supabase', []))}\n"
        f"• Added → Local: {len(buildings.get('inserted_to_local', []))}\n\n"
        f"📅 **Events Sync**\n"
        f"• Local: {events.get('local_total', 'N/A')}\n"
        f"• Supabase: {events.get('supa_total', 'N/A')}\n"
        f"• Added → Supabase: {len(events.get('inserted_to_supabase', []))}\n"
        f"• Added → Local: {len(events.get('inserted_to_local', []))}\n\n"
        f"📄 **Documents Sync**\n"
        f"• Local: {documents.get('local_total', 'N/A')}\n"
        f"• Supabase: {documents.get('supa_total', 'N/A')}\n"
        f"• Added → Supabase: {len(documents.get('inserted_to_supabase', []))}\n"
        f"• Added → Local: {len(documents.get('inserted_to_local', []))}\n\n"
        f"💬 **Messages**\n"
        f"• Buildings: {buildings.get('message', 'No message returned')}\n"
        f"• Events: {events.get('message', 'No message returned')}\n"
        f"• Documents: {documents.get('message', 'No message returned')}\n"
    )
