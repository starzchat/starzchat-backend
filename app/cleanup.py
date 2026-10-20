"""Deletes expired messages. Saved copies live in a separate table, so they stay."""

from .extensions import db
from .models import Message, utcnow


def delete_expired_messages():
    deleted = Message.query.filter(Message.expires_at <= utcnow()).delete(
        synchronize_session=False
    )
    db.session.commit()
    return deleted


def start_scheduler(app):
    from apscheduler.schedulers.background import BackgroundScheduler

    def job():
        with app.app_context():
            count = delete_expired_messages()
            if count:
                app.logger.info("Cleanup removed %s expired messages", count)

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(job, "interval", seconds=app.config["CLEANUP_INTERVAL"])
    scheduler.start()
    return scheduler
