from app import db, app
from datetime import datetime

# Define the same User model structure your app expects
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

    # Check if admin user exists
    admin = User.query.filter_by(email="admin@sitemanager.local").first()
    if not admin:
        new_user = User(email="admin@sitemanager.local", password_hash="kwetutech002")
        db.session.add(new_user)
        db.session.commit()
        print("✅ Database created and admin user added successfully.")
    else:
        print("ℹ️ Admin user already exists.")
