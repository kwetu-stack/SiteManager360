from app import db, User, app
from werkzeug.security import generate_password_hash

print("🔄 Creating admin user...")

with app.app_context():
    db.create_all()
    admin_email = "admin@sitemanager.com"
    existing = User.query.filter_by(email=admin_email).first()
    if not existing:
        admin = User(
            name="Admin",
            email=admin_email,
            password_hash=generate_password_hash("admin123"),
        )
        db.session.add(admin)
        db.session.commit()
        print(f"✅ Admin user created: {admin_email} / admin123")
    else:
        print(f"ℹ️ Admin already exists: {admin_email}")
