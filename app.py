import os
from datetime import datetime, date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, abort, session, Response
from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.session import Session as FlaskSQLAlchemySession
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

DEMO_MODE = True
DEMO_WRITE_BYPASS = False


def is_demo():
    return DEMO_MODE


def demo_persistence_enabled():
    return not is_demo() or DEMO_WRITE_BYPASS


class DemoSession(FlaskSQLAlchemySession):
    def commit(self):
        if demo_persistence_enabled():
            super().commit()


class DemoSQLAlchemy(SQLAlchemy):
    def __init__(self, *args, **kwargs):
        session_options = dict(kwargs.pop("session_options", {}))
        session_options.setdefault("class_", DemoSession)
        super().__init__(*args, session_options=session_options, **kwargs)


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
app.url_map.strict_slashes = False

# -------------------- DATABASE CONFIG (Windows-safe) --------------------
database_url = os.getenv("DATABASE_URL", "").strip()
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

if database_url:
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    base_dir = os.path.abspath(os.path.dirname(__file__))
    win_local = os.environ.get("LOCALAPPDATA")
    if win_local:
        data_dir = os.path.join(win_local, "SiteManager360", "data")
    else:
        data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    sqlite_path = os.path.join(data_dir, "sitemanager360.db").replace("\\", "/")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{sqlite_path}"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["DEBUG"] = False

db = DemoSQLAlchemy(app)

# -------------------- MODELS --------------------
class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    contact_person = db.Column(db.String(120))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))
    address = db.Column(db.String(250))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    projects = db.relationship("Project", backref="client", lazy=True)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    location = db.Column(db.String(150))
    client_id = db.Column(db.Integer, db.ForeignKey("client.id"), nullable=False)
    budget = db.Column(db.Float, default=0.0)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    status = db.Column(db.String(50), default="Active")
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sites = db.relationship("Site", backref="project", lazy=True)

class Worker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(120))
    phone = db.Column(db.String(50))
    assigned_site_id = db.Column(db.Integer, db.ForeignKey("site.id"), nullable=True)
    hired_date = db.Column(db.Date)
    status = db.Column(db.String(50), default="Active")

class Site(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    type = db.Column(db.String(50), default="Block")
    location = db.Column(db.String(150))
    manager_id = db.Column(db.Integer, db.ForeignKey("worker.id"), nullable=True)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    status = db.Column(db.String(50), default="Active")
    manager = db.relationship("Worker", foreign_keys=[manager_id], uselist=False)

class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))
    category = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    materials = db.relationship("Material", backref="supplier", lazy=True)

class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("supplier.id"), nullable=True)
    name = db.Column(db.String(150), nullable=False)
    unit = db.Column(db.String(50), default="pcs")
    current_stock = db.Column(db.Float, default=0.0)
    reorder_level = db.Column(db.Float)
    cost_per_unit = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SiteMaterial(db.Model):  # Deliveries
    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey("site.id"), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey("material.id"), nullable=False)
    unit = db.Column(db.String(50))
    quantity = db.Column(db.Float, default=0.0)
    delivery_date = db.Column(db.Date)
    supplier_name = db.Column(db.String(150))
    notes = db.Column(db.String(250))
    site = db.relationship("Site", backref="deliveries", lazy=True)
    material = db.relationship("Material", backref="deliveries", lazy=True)

class Equipment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    type = db.Column(db.String(120))
    purchase_date = db.Column(db.Date)
    status = db.Column(db.String(50), default="Available")
    assigned_site_id = db.Column(db.Integer, db.ForeignKey("site.id"), nullable=True)
    assigned_site = db.relationship("Site", foreign_keys=[assigned_site_id], uselist=False)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey("site.id"), nullable=False)
    name = db.Column(db.String(250), nullable=False)
    status = db.Column(db.String(50), default="Pending")
    assigned_to = db.Column(db.Integer, db.ForeignKey("worker.id"), nullable=True)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    site = db.relationship("Site", backref="tasks", lazy=True)
    worker = db.relationship("Worker", foreign_keys=[assigned_to], uselist=False)

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey("site.id"), nullable=False)
    type = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Float, default=0.0)
    date = db.Column(db.Date, default=date.today)
    description = db.Column(db.String(250))
    site = db.relationship("Site", backref="expenses", lazy=True)

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey("site.id"), nullable=True)
    file_path = db.Column(db.String(500))
    date = db.Column(db.Date, default=date.today)
    site = db.relationship("Site", backref="documents", lazy=True)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def set_password(pw):
    import hashlib, os, binascii
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, 100000)
    return binascii.hexlify(salt).decode() + ":" + binascii.hexlify(dk).decode()

def check_password(hashval, pw):
    import binascii, hashlib
    salt_hex, dk_hex = hashval.split(":")
    salt = binascii.unhexlify(salt_hex.encode())
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, 100000)
    return binascii.hexlify(dk).decode() == dk_hex

# -------------------- HELPERS --------------------
def parse_date(field):
    val = request.form.get(field) or ""
    try:
        return datetime.strptime(val, "%Y-%m-%d").date() if val else None
    except ValueError:
        return None

def commit_session():
    if demo_persistence_enabled():
        db.session.commit()

def seed_data():
    global DEMO_WRITE_BYPASS
    previous_bypass = DEMO_WRITE_BYPASS
    DEMO_WRITE_BYPASS = True
    try:
        # Seed admin user
        if not User.query.filter(db.func.lower(User.email)=="user.admin@sitemanager.local").first():
            admin = User(email="user.admin@sitemanager.local", password_hash=set_password("kwetutech002"))
            db.session.add(admin)

        if Client.query.first():
            commit_session()
            return

        # Clients
        c1 = Client(name="Nairobi Properties Ltd", contact_person="Jane W.", phone="+254700111222",
                    email="jane@npl.co.ke", address="Kilimani, Nairobi")
        c2 = Client(name="Eastlands Developers", contact_person="Peter K.", phone="+254700222333",
                    email="peter@edl.co.ke", address="Industrial Area, Nairobi")
        db.session.add_all([c1, c2]); db.session.flush()

        # Workers
        w1 = Worker(name="Eric Kimani", role="Site Manager", phone="+254711000111", hired_date=date(2023,1,12), status="Active")
        w2 = Worker(name="Lydia W.", role="Engineer", phone="+254722000222", hired_date=date(2023,3,5), status="Active")
        w3 = Worker(name="Joseph N.", role="Foreman", phone="+254733000333", hired_date=date(2024,5,1), status="Active")
        db.session.add_all([w1, w2, w3]); db.session.flush()

        # Projects
        p1 = Project(name="Westlands Office Complex", client_id=c1.id,
                     location="Westlands, Nairobi", budget=120000000.0,
                     start_date=date(2024,1,15), end_date=date(2025,12,30), status="Active",
                     description="Commercial office development with integrated parking and two towers.")
        p2 = Project(name="Kilimani Heights Apartments", client_id=c2.id,
                     location="Kilimani, Nairobi", budget=98000000.0,
                     start_date=date(2024,2,1), end_date=date(2025,11,15), status="Active",
                     description="Residential towers with rooftop amenities and basement parking.")
        db.session.add_all([p1, p2]); db.session.flush()

        # Sites for Westlands Office Complex
        s1 = Site(project_id=p1.id, name="Tower A", type="Block", location="Westlands, Nairobi",
                  manager_id=w1.id, start_date=date(2024,1,20), status="Active")
        s2 = Site(project_id=p1.id, name="Tower B", type="Block", location="Westlands, Nairobi",
                  manager_id=w2.id, start_date=date(2024,2,10), status="Active")
        s3 = Site(project_id=p1.id, name="Parking Area", type="Parking", location="Westlands, Nairobi",
                  manager_id=w3.id, start_date=date(2024,2,25), status="Active")

        # Sites for Kilimani Heights Apartments
        s4 = Site(project_id=p2.id, name="Block A", type="Block", location="Kilimani, Nairobi",
                  manager_id=w1.id, start_date=date(2024,2,15), status="Active")
        s5 = Site(project_id=p2.id, name="Block B", type="Block", location="Kilimani, Nairobi",
                  manager_id=w2.id, start_date=date(2024,3,1), status="Active")
        s6 = Site(project_id=p2.id, name="Basement Parking", type="Parking", location="Kilimani, Nairobi",
                  manager_id=w3.id, start_date=date(2024,3,5), status="Active")
        s7 = Site(project_id=p2.id, name="Rooftop", type="Rooftop", location="Kilimani, Nairobi",
                  manager_id=w1.id, start_date=date(2024,3,10), status="Active")
        db.session.add_all([s1, s2, s3, s4, s5, s6, s7]); db.session.flush()

        # Suppliers & Materials
        sup1 = Supplier(name="BuildMart Ltd", phone="+254701111111", email="sales@buildmart.co.ke", category="Cement & Steel")
        sup2 = Supplier(name="MegaTools KE", phone="+254702222222", email="info@megatools.co.ke", category="Tools & Equipment")
        db.session.add_all([sup1, sup2]); db.session.flush()

        m1 = Material(supplier_id=sup1.id, name="Cement (Bamburi)", unit="Bags", current_stock=200, reorder_level=100, cost_per_unit=850.0)
        m2 = Material(supplier_id=sup1.id, name="Steel Bars (Y10)", unit="Pieces", current_stock=50, reorder_level=30, cost_per_unit=120.0)
        m3 = Material(supplier_id=sup1.id, name="Steel Bars (Y12)", unit="Pieces", current_stock=40, reorder_level=30, cost_per_unit=130.0)
        m4 = Material(supplier_id=sup1.id, name="Sand", unit="Tons", current_stock=3, reorder_level=2, cost_per_unit=3000.0)
        m5 = Material(supplier_id=sup1.id, name="Ballast", unit="Tons", current_stock=1, reorder_level=1, cost_per_unit=3200.0)
        m6 = Material(supplier_id=sup2.id, name="Paint (Crown)", unit="Litres", current_stock=20, reorder_level=10, cost_per_unit=550.0)
        db.session.add_all([m1, m2, m3, m4, m5, m6]); db.session.flush()

        # Deliveries
        d1 = SiteMaterial(site_id=s4.id, material_id=m1.id, unit=m1.unit, quantity=200, delivery_date=date(2024,3,20), supplier_name="BuildMart Ltd", notes="Initial cement delivery")
        d2 = SiteMaterial(site_id=s5.id, material_id=m4.id, unit=m4.unit, quantity=3, delivery_date=date(2024,3,22), supplier_name="BuildMart Ltd", notes="Sand for slab works")
        d3 = SiteMaterial(site_id=s6.id, material_id=m5.id, unit=m5.unit, quantity=1, delivery_date=date(2024,3,24), supplier_name="BuildMart Ltd", notes="Ballast delivery")
        d4 = SiteMaterial(site_id=s4.id, material_id=m2.id, unit=m2.unit, quantity=50, delivery_date=date(2024,3,25), supplier_name="BuildMart Ltd", notes="Steel bars for reinforcement")
        db.session.add_all([d1, d2, d3, d4])

        # Equipment
        e1 = Equipment(name="CAT 320D Excavator", type="Excavator", purchase_date=date(2022,9,15), status="In Use", assigned_site_id=s1.id)
        e2 = Equipment(name="JCB Backhoe", type="Backhoe", purchase_date=date(2021,5,18), status="Available")
        db.session.add_all([e1, e2])

        # Tasks
        t1 = Task(site_id=s1.id, name="Excavation for foundation", status="In_Progress", assigned_to=w3.id, start_date=date(2024,3,1), end_date=date(2024,3,15))
        t2 = Task(site_id=s2.id, name="Install temporary fencing", status="Open", assigned_to=w2.id, start_date=date(2024,3,1), end_date=date(2024,3,10))
        db.session.add_all([t1, t2])

        # Expenses
        ex1 = Expense(site_id=s1.id, type="Transport", amount=45000.0, date=date(2024,2,14), description="Excavator fuel")
        ex2 = Expense(site_id=s1.id, type="Material", amount=170000.0, date=date(2024,2,12), description="Cement & steel")
        db.session.add_all([ex1, ex2])

        # Docs
        doc1 = Document(name="Delivery Note - Cement", type="Delivery Note", site_id=s4.id, date=date(2024,3,20))
        doc2 = Document(name="Invoice - Steel Supply", type="Invoice", site_id=s5.id, date=date(2024,3,25))
        doc3 = Document(name="Building Permit", type="Permit", site_id=None, date=date(2024,1,15))  # Project level
        doc4 = Document(name="Receipt - Transport", type="Receipt", site_id=s6.id, date=date(2024,2,14))
        db.session.add_all([doc1, doc2, doc3, doc4])

        commit_session()
    finally:
        DEMO_WRITE_BYPASS = previous_bypass

# -------------------- AUTH --------------------
def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if is_demo():
            demo_user = User.query.order_by(User.id.asc()).first()
            if demo_user:
                session["user_id"] = demo_user.id
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return view_func(*args, **kwargs)
    return wrapped

@app.context_processor
def inject_demo_mode():
    return {"demo_mode": is_demo()}

@app.before_request
def block_post_in_demo():
    if is_demo():
        demo_user = User.query.order_by(User.id.asc()).first()
        if demo_user and request.endpoint != "static":
            session["user_id"] = demo_user.id
        if request.method == "POST":
            flash("Demo Mode: Action simulated successfully.", "info")
            return redirect(request.referrer or url_for("dashboard"))

@app.route("/login", methods=["GET","POST"])
def login():
    if is_demo():
        demo_user = User.query.order_by(User.id.asc()).first()
        if demo_user:
            session["user_id"] = demo_user.id
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = User.query.filter(db.func.lower(User.email)==email).first()
        if user and check_password(user.password_hash, password):
            session["user_id"] = user.id
            flash("Welcome back.", "success")
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Invalid credentials.", "warning")
    return render_template("login.html")

@app.route("/logout")
def logout():
    if is_demo():
        flash("Demo Mode stays signed in for showcase access.", "info")
        return redirect(url_for("dashboard"))
    session.pop("user_id", None)
    flash("Signed out.", "info")
    return redirect(url_for("login"))

# -------------------- BASIC --------------------
@app.route("/health")
def health():
    return "OK", 200

@app.route("/")
@login_required
def dashboard():
    active_projects = db.session.scalar(db.select(db.func.count(Project.id)).where(Project.status == "Active")) or 0
    active_sites = db.session.scalar(db.select(db.func.count(Site.id)).where(Site.status == "Active")) or 0
    
    # Safe materials_stock query (handles missing column gracefully)
    try:
        materials_stock = db.session.scalar(db.select(db.func.sum(Material.current_stock))) or 0
    except:
        materials_stock = 0
    
    total_expenses = db.session.scalar(db.select(db.func.sum(Expense.amount))) or 0
    return render_template("dashboard.html",
                           active_projects=active_projects,
                           active_sites=active_sites,
                           materials_stock=materials_stock,
                           total_expenses=total_expenses)

# Alias route for templates/links that use /dashboard
@app.route("/dashboard")
@login_required
def dashboard_alias():
    return dashboard()

# -------------------- CLIENTS --------------------
@app.route("/clients")
@login_required
def clients():
    items = Client.query.order_by(Client.created_at.desc()).all()
    return render_template("clients_list.html", items=items)

@app.route("/clients/new", methods=["GET","POST"])
@login_required
def clients_new():
    if request.method == "POST":
        c = Client(
            name=request.form["name"],
            contact_person=request.form.get("contact_person"),
            phone=request.form.get("phone"),
            email=request.form.get("email"),
            address=request.form.get("address"),
        )
        db.session.add(c); commit_session()
        flash("Client created", "success")
        return redirect(url_for("clients"))
    return render_template("clients_form.html", item=None)

@app.route("/clients/<int:id>/edit", methods=["GET","POST"])
@login_required
def clients_edit(id):
    item = Client.query.get_or_404(id)
    if request.method == "POST":
        item.name = request.form["name"]
        item.contact_person = request.form.get("contact_person")
        item.phone = request.form.get("phone")
        item.email = request.form.get("email")
        item.address = request.form.get("address")
        commit_session()
        flash("Client updated", "success")
        return redirect(url_for("clients"))
    return render_template("clients_form.html", item=item)

@app.route("/clients/<int:id>/delete", methods=["POST"])
@login_required
def clients_delete(id):
    item = Client.query.get_or_404(id)
    db.session.delete(item); commit_session()
    flash("Client deleted", "info")
    return redirect(url_for("clients"))

# -------------------- PROJECTS --------------------
@app.route("/projects")
@login_required
def projects():
    items = Project.query.order_by(Project.created_at.desc()).all()
    return render_template("projects_list.html", items=items, clients=Client.query.all())

@app.route("/projects/new", methods=["GET","POST"])
@login_required
def projects_new():
    clients = Client.query.all()
    if request.method == "POST":
        p = Project(
            name=request.form["name"],
            location=request.form.get("location"),
            client_id=int(request.form["client_id"]),
            budget=float(request.form.get("budget") or 0),
            start_date=parse_date("start_date"),
            end_date=parse_date("end_date"),
            status=request.form.get("status") or "Active",
            description=request.form.get("description")
        )
        db.session.add(p); commit_session()
        flash("Project created", "success")
        return redirect(url_for("projects"))
    return render_template("projects_form.html", item=None, clients=clients)

@app.route("/projects/<int:id>/edit", methods=["GET","POST"])
@login_required
def projects_edit(id):
    item = Project.query.get_or_404(id)
    clients = Client.query.all()
    if request.method == "POST":
        item.name = request.form["name"]
        item.location = request.form.get("location")
        item.client_id = int(request.form["client_id"])
        item.budget = float(request.form.get("budget") or 0)
        item.start_date = parse_date("start_date")
        item.end_date = parse_date("end_date")
        item.status = request.form.get("status") or "Active"
        item.description = request.form.get("description")
        commit_session()
        flash("Project updated", "success")
        return redirect(url_for("projects"))
    return render_template("projects_form.html", item=item, clients=clients)

@app.route("/projects/<int:id>/delete", methods=["POST"])
@login_required
def projects_delete(id):
    item = Project.query.get_or_404(id)
    db.session.delete(item); commit_session()
    flash("Project deleted", "info")
    return redirect(url_for("projects"))

# -------------------- SITES --------------------
@app.route("/sites")
@login_required
def sites():
    project_id = request.args.get("project_id", type=int)
    query = Site.query.order_by(Site.id.desc())
    if project_id:
        query = query.filter_by(project_id=project_id)
    items = query.all()
    return render_template("sites_list.html", items=items, projects=Project.query.all(), workers=Worker.query.all(), selected_project_id=project_id)

@app.route("/sites/new", methods=["GET","POST"])
@login_required
def sites_new():
    projects = Project.query.all()
    workers = Worker.query.all()
    if request.method == "POST":
        s = Site(
            project_id=int(request.form["project_id"]),
            name=request.form["name"],
            type=request.form.get("type") or "Block",
            location=request.form.get("location"),
            manager_id=int(request.form["manager_id"]) if request.form.get("manager_id") else None,
            start_date=parse_date("start_date"),
            end_date=parse_date("end_date"),
            status=request.form.get("status") or "Active",
        )
        db.session.add(s); commit_session()
        flash("Site created", "success")
        return redirect(url_for("sites"))
    return render_template("sites_form.html", item=None, projects=projects, workers=workers)

@app.route("/sites/<int:id>/edit", methods=["GET","POST"])
@login_required
def sites_edit(id):
    item = Site.query.get_or_404(id)
    projects = Project.query.all()
    workers = Worker.query.all()
    if request.method == "POST":
        item.project_id = int(request.form["project_id"])
        item.name = request.form["name"]
        item.type = request.form.get("type") or "Block"
        item.location = request.form.get("location")
        item.manager_id = int(request.form["manager_id"]) if request.form.get("manager_id") else None
        item.start_date = parse_date("start_date")
        item.end_date = parse_date("end_date")
        item.status = request.form.get("status") or "Active"
        commit_session()
        flash("Site updated", "success")
        return redirect(url_for("sites"))
    return render_template("sites_form.html", item=item, projects=projects, workers=workers)

@app.route("/sites/<int:id>/delete", methods=["POST"])
@login_required
def sites_delete(id):
    item = Site.query.get_or_404(id)
    db.session.delete(item); commit_session()
    flash("Site deleted", "info")
    return redirect(url_for("sites"))

# -------------------- SUPPLIERS --------------------
@app.route("/suppliers")
@login_required
def suppliers():
    items = Supplier.query.order_by(Supplier.created_at.desc()).all()
    return render_template("suppliers_list.html", items=items)

@app.route("/suppliers/new", methods=["GET","POST"])
@login_required
def suppliers_new():
    if request.method == "POST":
        s = Supplier(
            name=request.form["name"],
            phone=request.form.get("phone"),
            email=request.form.get("email"),
            category=request.form.get("category"),
        )
        db.session.add(s); commit_session()
        flash("Supplier created", "success")
        return redirect(url_for("suppliers"))
    return render_template("suppliers_form.html", item=None)

@app.route("/suppliers/<int:id>/edit", methods=["GET","POST"])
@login_required
def suppliers_edit(id):
    item = Supplier.query.get_or_404(id)
    if request.method == "POST":
        item.name = request.form["name"]
        item.phone = request.form.get("phone")
        item.email = request.form.get("email")
        item.category = request.form.get("category")
        commit_session()
        flash("Supplier updated", "success")
        return redirect(url_for("suppliers"))
    return render_template("suppliers_form.html", item=item)

@app.route("/suppliers/<int:id>/delete", methods=["POST"])
@login_required
def suppliers_delete(id):
    item = Supplier.query.get_or_404(id)
    db.session.delete(item); commit_session()
    flash("Supplier deleted", "info")
    return redirect(url_for("suppliers"))

# -------------------- MATERIALS --------------------
@app.route("/materials")
@login_required
def materials():
    items = Material.query.order_by(Material.created_at.desc()).all()
    return render_template("materials_list.html", items=items, suppliers=Supplier.query.all())

@app.route("/materials/new", methods=["GET","POST"])
@login_required
def materials_new():
    suppliers = Supplier.query.all()
    if request.method == "POST":
        supplier_value = request.form.get("supplier_id")
        m = Material(
            supplier_id=int(supplier_value) if supplier_value else None,
            name=request.form["name"],
            unit=request.form.get("unit") or "pcs",
            current_stock=float(request.form.get("current_stock") or 0),
            reorder_level=float(request.form.get("reorder_level") or 0) if request.form.get("reorder_level") else None,
            cost_per_unit=float(request.form.get("cost_per_unit") or 0),
        )
        db.session.add(m); commit_session()
        flash("Material created", "success")
        return redirect(url_for("materials"))
    return render_template("materials_form.html", item=None, suppliers=suppliers)

@app.route("/materials/<int:id>/edit", methods=["GET","POST"])
@login_required
def materials_edit(id):
    item = Material.query.get_or_404(id)
    suppliers = Supplier.query.all()
    if request.method == "POST":
        supplier_value = request.form.get("supplier_id")
        item.supplier_id = int(supplier_value) if supplier_value else None
        item.name = request.form["name"]
        item.unit = request.form.get("unit") or "pcs"
        item.current_stock = float(request.form.get("current_stock") or 0)
        item.reorder_level = float(request.form.get("reorder_level") or 0) if request.form.get("reorder_level") else None
        item.cost_per_unit = float(request.form.get("cost_per_unit") or 0)
        commit_session()
        flash("Material updated", "success")
        return redirect(url_for("materials"))
    return render_template("materials_form.html", item=item, suppliers=suppliers)

@app.route("/materials/<int:id>/delete", methods=["POST"])
@login_required
def materials_delete(id):
    item = Material.query.get_or_404(id)
    db.session.delete(item); commit_session()
    flash("Material deleted", "info")
    return redirect(url_for("materials"))

# -------------------- DELIVERIES --------------------
@app.route("/deliveries")
@login_required
def deliveries():
    items = SiteMaterial.query.order_by(SiteMaterial.delivery_date.desc().nullslast()).all()
    return render_template("deliveries_list.html", items=items, sites=Site.query.all(), materials=Material.query.all())

@app.route("/deliveries/new", methods=["GET","POST"])
@login_required
def deliveries_new():
    sites = Site.query.all()
    materials = Material.query.all()
    if request.method == "POST":
        material = Material.query.get_or_404(int(request.form["material_id"]))
        quantity = float(request.form.get("quantity") or 0)
        d = SiteMaterial(
            site_id=int(request.form["site_id"]),
            material_id=material.id,
            unit=material.unit,
            quantity=quantity,
            delivery_date=parse_date("delivery_date"),
            supplier_name=request.form.get("supplier_name"),
            notes=request.form.get("notes")
        )
        material.current_stock = (material.current_stock or 0) + quantity
        db.session.add(d); commit_session()
        flash("Delivery recorded", "success")
        return redirect(url_for("deliveries"))
    return render_template("deliveries_form.html", item=None, sites=sites, materials=materials)

@app.route("/deliveries/<int:id>/edit", methods=["GET","POST"])
@login_required
def deliveries_edit(id):
    item = SiteMaterial.query.get_or_404(id)
    sites = Site.query.all()
    materials = Material.query.all()
    if request.method == "POST":
        new_material = Material.query.get_or_404(int(request.form["material_id"]))
        new_quantity = float(request.form.get("quantity") or 0)
        old_material = item.material
        old_quantity = item.quantity or 0
        if old_material and old_material.id != new_material.id:
            old_material.current_stock = (old_material.current_stock or 0) - old_quantity
            new_material.current_stock = (new_material.current_stock or 0) + new_quantity
        else:
            new_material.current_stock = (new_material.current_stock or 0) + (new_quantity - old_quantity)
        item.site_id = int(request.form["site_id"])
        item.material_id = new_material.id
        item.unit = new_material.unit
        item.quantity = new_quantity
        item.delivery_date = parse_date("delivery_date")
        item.supplier_name = request.form.get("supplier_name")
        item.notes = request.form.get("notes")
        commit_session()
        flash("Delivery updated", "success")
        return redirect(url_for("deliveries"))
    return render_template("deliveries_form.html", item=item, sites=sites, materials=materials)

@app.route("/deliveries/<int:id>/delete", methods=["POST"])
@login_required
def deliveries_delete(id):
    item = SiteMaterial.query.get_or_404(id)
    if item.material:
        item.material.current_stock = (item.material.current_stock or 0) - item.quantity
    db.session.delete(item); commit_session()
    flash("Delivery deleted", "info")
    return redirect(url_for("deliveries"))

# -------------------- EQUIPMENT --------------------
@app.route("/equipment")
@login_required
def equipment():
    items = Equipment.query.order_by(Equipment.id.desc()).all()
    return render_template("equipment_list.html", items=items, sites=Site.query.all())

@app.route("/equipment/new", methods=["GET","POST"])
@login_required
def equipment_new():
    sites = Site.query.all()
    if request.method == "POST":
        e = Equipment(
            name=request.form["name"],
            type=request.form.get("type"),
            purchase_date=parse_date("purchase_date"),
            status=request.form.get("status") or "Available",
            assigned_site_id=int(request.form["assigned_site_id"]) if request.form.get("assigned_site_id") else None
        )
        db.session.add(e); commit_session()
        flash("Equipment created", "success")
        return redirect(url_for("equipment"))
    return render_template("equipment_form.html", item=None, sites=sites)

@app.route("/equipment/<int:id>/edit", methods=["GET","POST"])
@login_required
def equipment_edit(id):
    item = Equipment.query.get_or_404(id)
    sites = Site.query.all()
    if request.method == "POST":
        item.name = request.form["name"]
        item.type = request.form.get("type")
        item.purchase_date = parse_date("purchase_date")
        item.status = request.form.get("status") or "Available"
        item.assigned_site_id = int(request.form["assigned_site_id"]) if request.form.get("assigned_site_id") else None
        commit_session()
        flash("Equipment updated", "success")
        return redirect(url_for("equipment"))
    return render_template("equipment_form.html", item=item, sites=sites)

@app.route("/equipment/<int:id>/delete", methods=["POST"])
@login_required
def equipment_delete(id):
    item = Equipment.query.get_or_404(id)
    db.session.delete(item); commit_session()
    flash("Equipment deleted", "info")
    return redirect(url_for("equipment"))

# -------------------- WORKFORCE --------------------
@app.route("/workforce")
@login_required
def workforce():
    items = Worker.query.order_by(Worker.id.desc()).all()
    return render_template("workforce_list.html", items=items, sites=Site.query.all())

@app.route("/workforce/new", methods=["GET","POST"])
@login_required
def workforce_new():
    sites = Site.query.all()
    if request.method == "POST":
        w = Worker(
            name=request.form["name"],
            role=request.form.get("role"),
            phone=request.form.get("phone"),
            assigned_site_id=int(request.form["assigned_site_id"]) if request.form.get("assigned_site_id") else None,
            hired_date=parse_date("hired_date"),
            status=request.form.get("status") or "Active"
        )
        db.session.add(w); commit_session()
        flash("Worker added", "success")
        return redirect(url_for("workforce"))
    return render_template("workforce_form.html", item=None, sites=sites)

@app.route("/workforce/<int:id>/edit", methods=["GET","POST"])
@login_required
def workforce_edit(id):
    item = Worker.query.get_or_404(id)
    sites = Site.query.all()
    if request.method == "POST":
        item.name = request.form["name"]
        item.role = request.form.get("role")
        item.phone = request.form.get("phone")
        item.assigned_site_id = int(request.form["assigned_site_id"]) if request.form.get("assigned_site_id") else None
        item.hired_date = parse_date("hired_date")
        item.status = request.form.get("status") or "Active"
        commit_session()
        flash("Worker updated", "success")
        return redirect(url_for("workforce"))
    return render_template("workforce_form.html", item=item, sites=sites)

@app.route("/workforce/<int:id>/delete", methods=["POST"])
@login_required
def workforce_delete(id):
    item = Worker.query.get_or_404(id)
    db.session.delete(item); commit_session()
    flash("Worker deleted", "info")
    return redirect(url_for("workforce"))

# -------------------- TASKS --------------------
@app.route("/tasks")
@login_required
def tasks():
    items = Task.query.order_by(Task.created_at.desc()).all()
    return render_template("tasks_list.html", items=items, sites=Site.query.all(), workers=Worker.query.all())

@app.route("/tasks/new", methods=["GET","POST"])
@login_required
def tasks_new():
    sites = Site.query.all()
    workers = Worker.query.all()
    if request.method == "POST":
        t = Task(
            site_id=int(request.form["site_id"]),
            name=request.form["name"],
            status=request.form.get("status") or "Pending",
            assigned_to=int(request.form["assigned_to"]) if request.form.get("assigned_to") else None,
            start_date=parse_date("start_date"),
            end_date=parse_date("end_date")
        )
        db.session.add(t); commit_session()
        flash("Task created", "success")
        return redirect(url_for("tasks"))
    return render_template("tasks_form.html", item=None, sites=sites, workers=workers)

@app.route("/tasks/<int:id>/edit", methods=["GET","POST"])
@login_required
def tasks_edit(id):
    item = Task.query.get_or_404(id)
    sites = Site.query.all()
    workers = Worker.query.all()
    if request.method == "POST":
        item.site_id = int(request.form["site_id"])
        item.name = request.form["name"]
        item.status = request.form.get("status") or "Pending"
        item.assigned_to = int(request.form["assigned_to"]) if request.form.get("assigned_to") else None
        item.start_date = parse_date("start_date")
        item.end_date = parse_date("end_date")
        commit_session()
        flash("Task updated", "success")
        return redirect(url_for("tasks"))
    return render_template("tasks_form.html", item=item, sites=sites, workers=workers)

@app.route("/tasks/<int:id>/delete", methods=["POST"])
@login_required
def tasks_delete(id):
    item = Task.query.get_or_404(id)
    db.session.delete(item); commit_session()
    flash("Task deleted", "info")
    return redirect(url_for("tasks"))

# -------------------- EXPENSES --------------------
@app.route("/expenses")
@login_required
def expenses():
    items = Expense.query.order_by(Expense.date.desc()).all()
    return render_template("expenses_list.html", items=items, sites=Site.query.all())

@app.route("/expenses/new", methods=["GET","POST"])
@login_required
def expenses_new():
    sites = Site.query.all()
    if request.method == "POST":
        ex = Expense(
            site_id=int(request.form["site_id"]),
            type=request.form["type"],
            amount=float(request.form.get("amount") or 0),
            date=parse_date("date") or date.today(),
            description=request.form.get("description")
        )
        db.session.add(ex); commit_session()
        flash("Expense recorded", "success")
        return redirect(url_for("expenses"))
    return render_template("expenses_form.html", item=None, sites=sites)

@app.route("/expenses/<int:id>/edit", methods=["GET","POST"])
@login_required
def expenses_edit(id):
    item = Expense.query.get_or_404(id)
    sites = Site.query.all()
    if request.method == "POST":
        item.site_id = int(request.form["site_id"])
        item.type = request.form["type"]
        item.amount = float(request.form.get("amount") or 0)
        item.date = parse_date("date") or date.today()
        item.description = request.form.get("description")
        commit_session()
        flash("Expense updated", "success")
        return redirect(url_for("expenses"))
    return render_template("expenses_form.html", item=item, sites=sites)

@app.route("/expenses/<int:id>/delete", methods=["POST"])
@login_required
def expenses_delete(id):
    item = Expense.query.get_or_404(id)
    db.session.delete(item); commit_session()
    flash("Expense deleted", "info")
    return redirect(url_for("expenses"))

# -------------------- DOCS & REPORTS --------------------
@app.route("/documents")
@login_required
def documents():
    return render_template("documents.html")

@app.route("/documents/new", methods=["GET","POST"])
@login_required
def documents_new():
    sites = Site.query.all()
    if request.method == "POST":
        doc = Document(
            name=request.form["name"],
            type=request.form["type"],
            site_id=int(request.form["site_id"]) if request.form.get("site_id") else None,
            file_path=request.form.get("file_path"),
            date=parse_date("date") or date.today()
        )
        db.session.add(doc); commit_session()
        flash("Document added", "success")
        return redirect(url_for("documents"))
    return render_template("documents_form.html", item=None, sites=sites)

@app.route("/documents/<int:id>/edit", methods=["GET","POST"])
@login_required
def documents_edit(id):
    item = Document.query.get_or_404(id)
    sites = Site.query.all()
    if request.method == "POST":
        item.name = request.form["name"]
        item.type = request.form["type"]
        item.site_id = int(request.form["site_id"]) if request.form.get("site_id") else None
        item.file_path = request.form.get("file_path")
        item.date = parse_date("date") or date.today()
        commit_session()
        flash("Document updated", "success")
        return redirect(url_for("documents"))
    return render_template("documents_form.html", item=item, sites=sites)

@app.route("/documents/<int:id>/delete", methods=["POST"])
@login_required
def documents_delete(id):
    item = Document.query.get_or_404(id)
    db.session.delete(item); commit_session()
    flash("Document deleted", "info")
    return redirect(url_for("documents"))

@app.route("/reports")
@login_required
def reports():
    # Get summary data
    sites = Site.query.all()
    summaries = []
    for site in sites:
        materials_count = sum(d.quantity for d in site.deliveries)
        expenses_total = sum(e.amount for e in site.expenses)
        workers_count = Worker.query.filter_by(assigned_site_id=site.id).count()
        summaries.append({
            'site': site,
            'materials_delivered': materials_count,
            'expenses_total': expenses_total,
            'workers_count': workers_count
        })
    return render_template("reports.html", summaries=summaries)

# -------------------- SUPPORT FILES --------------------
@app.route("/favicon.ico")
def favicon():
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
        '<rect width="16" height="16" fill="#0f766e"/>'
        '<text x="8" y="11" font-family="Arial, sans-serif" font-size="10" fill="#ffffff" text-anchor="middle">S</text>'
        '</svg>'
    )
    return Response(svg, mimetype="image/svg+xml")

@app.route("/.well-known/appspecific/com.chrome.devtools.json")
def chrome_devtools_manifest():
    return {}, 200

# -------------------- ERROR HANDLER --------------------
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def internal_error(e):
    # Ensure Railway/Gunicorn logs include the traceback for debugging.
    import traceback
    traceback.print_exc()
    return (
        "Internal Server Error. Check server logs for the exception traceback.",
        500,
    )

with app.app_context():
    db.create_all()

    def safe_add_column(query):
        # Railway often runs multiple Gunicorn workers; on SQLite this can cause
        # "database is locked" during startup migrations. Retry a few times so
        # the schema converges instead of silently skipping forever.
        import time
        last_err = None
        for attempt in range(6):
            try:
                with db.engine.connect() as conn:
                    conn.execute(text(query))
                    conn.commit()
                print("Migration applied:", query)
                return
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                if "database is locked" in msg or "locked" in msg:
                    time.sleep(0.25 * (attempt + 1))
                    continue
                break
        print("Migration skipped:", last_err)

    # FIXES / STARTUP MIGRATIONS
    # These keep older Railway SQLite DBs aligned with current models by
    # adding missing columns. (SQLite supports ADD COLUMN; failures are ignored.)

    # CLIENT TABLE
    safe_add_column("ALTER TABLE client ADD COLUMN contact_person TEXT")
    safe_add_column("ALTER TABLE client ADD COLUMN phone TEXT")
    safe_add_column("ALTER TABLE client ADD COLUMN email TEXT")
    safe_add_column("ALTER TABLE client ADD COLUMN address TEXT")
    safe_add_column("ALTER TABLE client ADD COLUMN created_at DATETIME")

    # PROJECT TABLE
    safe_add_column("ALTER TABLE project ADD COLUMN location TEXT")
    safe_add_column("ALTER TABLE project ADD COLUMN budget FLOAT DEFAULT 0")
    safe_add_column("ALTER TABLE project ADD COLUMN start_date DATE")
    safe_add_column("ALTER TABLE project ADD COLUMN end_date DATE")
    safe_add_column("ALTER TABLE project ADD COLUMN status TEXT")
    safe_add_column("ALTER TABLE project ADD COLUMN description TEXT")
    safe_add_column("ALTER TABLE project ADD COLUMN created_at DATETIME")

    # SITE TABLE
    safe_add_column("ALTER TABLE site ADD COLUMN project_id INTEGER")
    safe_add_column("ALTER TABLE site ADD COLUMN name TEXT")
    safe_add_column("ALTER TABLE site ADD COLUMN type TEXT DEFAULT 'Block'")
    safe_add_column("ALTER TABLE site ADD COLUMN location TEXT")
    safe_add_column("ALTER TABLE site ADD COLUMN manager_id INTEGER")
    safe_add_column("ALTER TABLE site ADD COLUMN start_date DATE")
    safe_add_column("ALTER TABLE site ADD COLUMN end_date DATE")
    safe_add_column("ALTER TABLE site ADD COLUMN status TEXT")

    # SUPPLIER TABLE
    safe_add_column("ALTER TABLE supplier ADD COLUMN phone TEXT")
    safe_add_column("ALTER TABLE supplier ADD COLUMN email TEXT")
    safe_add_column("ALTER TABLE supplier ADD COLUMN category TEXT")
    safe_add_column("ALTER TABLE supplier ADD COLUMN created_at DATETIME")

    # MATERIAL TABLE
    safe_add_column("ALTER TABLE material ADD COLUMN supplier_id INTEGER")
    safe_add_column("ALTER TABLE material ADD COLUMN unit TEXT")
    safe_add_column("ALTER TABLE material ADD COLUMN current_stock FLOAT DEFAULT 0")
    safe_add_column("ALTER TABLE material ADD COLUMN reorder_level FLOAT")
    safe_add_column("ALTER TABLE material ADD COLUMN cost_per_unit FLOAT DEFAULT 0")
    safe_add_column("ALTER TABLE material ADD COLUMN created_at DATETIME")

    # DELIVERIES TABLE (Model: SiteMaterial => table: site_material)
    safe_add_column("ALTER TABLE site_material ADD COLUMN site_id INTEGER")
    safe_add_column("ALTER TABLE site_material ADD COLUMN material_id INTEGER")
    safe_add_column("ALTER TABLE site_material ADD COLUMN unit TEXT")
    safe_add_column("ALTER TABLE site_material ADD COLUMN quantity FLOAT DEFAULT 0")
    safe_add_column("ALTER TABLE site_material ADD COLUMN delivery_date DATE")
    safe_add_column("ALTER TABLE site_material ADD COLUMN supplier_name TEXT")
    safe_add_column("ALTER TABLE site_material ADD COLUMN notes TEXT")

    # EQUIPMENT TABLE
    safe_add_column("ALTER TABLE equipment ADD COLUMN type TEXT")
    safe_add_column("ALTER TABLE equipment ADD COLUMN purchase_date DATE")
    safe_add_column("ALTER TABLE equipment ADD COLUMN status TEXT")
    safe_add_column("ALTER TABLE equipment ADD COLUMN assigned_site_id INTEGER")

    # WORKER TABLE
    safe_add_column("ALTER TABLE worker ADD COLUMN role TEXT")
    safe_add_column("ALTER TABLE worker ADD COLUMN phone TEXT")
    safe_add_column("ALTER TABLE worker ADD COLUMN assigned_site_id INTEGER")
    safe_add_column("ALTER TABLE worker ADD COLUMN hired_date DATE")
    safe_add_column("ALTER TABLE worker ADD COLUMN status TEXT DEFAULT 'Active'")

    # TASK TABLE
    safe_add_column("ALTER TABLE task ADD COLUMN site_id INTEGER")
    safe_add_column("ALTER TABLE task ADD COLUMN status TEXT")
    safe_add_column("ALTER TABLE task ADD COLUMN assigned_to INTEGER")
    safe_add_column("ALTER TABLE task ADD COLUMN start_date DATE")
    safe_add_column("ALTER TABLE task ADD COLUMN end_date DATE")
    safe_add_column("ALTER TABLE task ADD COLUMN created_at DATETIME")

    # EXPENSE TABLE
    safe_add_column("ALTER TABLE expense ADD COLUMN site_id INTEGER")
    safe_add_column("ALTER TABLE expense ADD COLUMN type TEXT")
    safe_add_column("ALTER TABLE expense ADD COLUMN amount FLOAT DEFAULT 0")
    safe_add_column("ALTER TABLE expense ADD COLUMN date DATE")
    safe_add_column("ALTER TABLE expense ADD COLUMN description TEXT")

    # DOCUMENT TABLE
    safe_add_column("ALTER TABLE document ADD COLUMN site_id INTEGER")
    safe_add_column("ALTER TABLE document ADD COLUMN file_path TEXT")
    safe_add_column("ALTER TABLE document ADD COLUMN date DATE")

    seed_data()

# ------------------ RUN APP ------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=app.config["DEBUG"])
