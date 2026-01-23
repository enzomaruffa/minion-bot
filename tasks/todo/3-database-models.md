# Database Models

Create SQLAlchemy models for all data entities.

## Acceptance Criteria
- [ ] Task model: id, title, description, status, priority, due_date, created_at, updated_at
- [ ] Attachment model: id, task_id, file_type, file_id, description
- [ ] Reminder model: id, task_id (optional), message, remind_at, delivered
- [ ] CalendarEvent model: id, google_event_id, title, start_time, end_time, synced_at
- [ ] Topic model: id, name, description (for memory/context)
- [ ] Database initialization function
