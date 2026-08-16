"""
Database models and repository implementations.

Responsibility
    SQLAlchemy ORM models and EventRepository implementation.
    Connection pooling, migrations, schema management.

Must not
    Be imported by domain/, ports/, or used outside of services/.
    Implement business logic — model mapping only.

Pattern
    persistence.models.Event (ORM model)
    adapters.repository.postgres_event_repository.PostgresEventRepository (implements ports.event_repository.EventRepository)
"""
