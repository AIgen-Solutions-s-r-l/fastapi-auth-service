from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from app.core.base_model import Base # Import from new location
from datetime import datetime, timezone

class ProcessedStripeEvent(Base):
    __tablename__ = "processed_stripe_events"

    stripe_event_id = Column(String(255), primary_key=True, index=True)
    processed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    event_type = Column(String(100), nullable=True)

    def __repr__(self):
        return f"<ProcessedStripeEvent(stripe_event_id='{self.stripe_event_id}', event_type='{self.event_type}')>"