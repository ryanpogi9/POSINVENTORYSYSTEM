from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from decimal import Decimal
from sqlalchemy import text
import pymysql

# -----------------------------
# Flask Config
# -----------------------------
app = Flask(__name__)
app.secret_key = "pos_inventory_secret_key_2025"

# -----------------------------
# MySQL Config
# -----------------------------
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:2006@localhost:3306/pos_inventory_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


# -----------------------------
# Database Models
# -----------------------------
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum('Admin', 'Cashier'), nullable=False)
    status = db.Column(db.Enum('Pending', 'Approved', 'Rejected'), default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    cost = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    category = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Sale(db.Model):
    __tablename__ = 'sales'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    product_name = db.Column(db.String(150))
    quantity_sold = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    unit_cost = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    total_cost = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    sold_by = db.Column(db.String(100))
    date = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship('Product', backref='sales')


# -----------------------------
# Initial Setup & Demo Data
# -----------------------------
with app.app_context():
    db.create_all()

    # Best-effort ALTERs to add new columns if missing (MySQL 8+ supports IF NOT EXISTS)
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS cost DECIMAL(10,2) NOT NULL DEFAULT 0.00"))
            conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS unit_cost DECIMAL(10,2) NOT NULL DEFAULT 0.00"))
            conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS total_cost DECIMAL(10,2) NOT NULL DEFAULT 0.00"))
    except Exception:
        # If ALTER fails due to permissions or MySQL version, ignore here; run ALTER manually if needed.
        pass

    # Create admin if not present
    if not User.query.filter_by(username='admin').first():
        admin = User(
            username='admin',
            password=generate_password_hash('admin123'),
            role='Admin',
            status='Approved'
        )
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin account created: admin / admin123")

    # Seed demo products if empty (so Sales History and Reports show example data)
    if Product.query.count() == 0:
        demo_products = [
            Product(name='Soap Bar', price=Decimal('25.00'), cost=Decimal('10.00'), quantity=100, category='Toiletries'),
            Product(name='Notebook', price=Decimal('80.00'), cost=Decimal('40.00'), quantity=50, category='Stationery'),
            Product(name='Bottle Water', price=Decimal('20.00'), cost=Decimal('8.00'), quantity=200, category='Beverages'),
        ]
        db.session.bulk_save_objects(demo_products)
        db.session.commit()
        print("✅ Demo products created")

    # Seed demo sales if empty
    if Sale.query.count() == 0:
        products = {p.name: p for p in Product.query.all()}
        demo_sales = [
            {'product_name': 'Soap Bar', 'qty': 3, 'sold_by': 'cashier1'},
            {'product_name': 'Notebook', 'qty': 2, 'sold_by': 'cashier2'},
            {'product_name': 'Bottle Water', 'qty': 5, 'sold_by': 'cashier1'},
        ]
        for s in demo_sales:
            p = products.get(s['product_name'])
            if p and p.quantity >= s['qty']:
                sale = Sale(
                    product_id=p.id,
                    product_name=p.name,
                    quantity_sold=s['qty'],
                    unit_price=p.price,
                    unit_cost=p.cost,
                    total_amount=Decimal(p.price) * s['qty'],
                    total_cost=Decimal(p.cost) * s['qty'],
                    sold_by=s['sold_by']
                )
                db.session.add(sale)
                p.quantity = p.quantity - s['qty']
        db.session.commit()
        print("✅ Demo sales created and inventory adjusted")


# -----------------------------
# Helper Functions
# -----------------------------
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please login to access this page.", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please login to access this page.", "error")
            return redirect(url_for('login'))
        if session.get('role') != 'Admin':
            flash("Admin access required.", "error")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# -----------------------------
# Routes
# -----------------------------
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


# ----------- LOGIN -----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash("Please provide both username and password.", "error")
            return render_template('login.html')

        user = User.query.filter_by(username=username).first()

        if not user:
            flash("User not found.", "error")
        elif user.status == 'Pending':
            flash("Your account is pending approval.", "info")
        elif user.status == 'Rejected':
            flash("Your account was rejected. Contact admin.", "error")
        elif check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            flash(f"Welcome {user.username}!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid credentials.", "error")

    return render_template('login.html')


# ----------- REGISTER (DISABLED) -----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    flash("Public registration is disabled. Admin must create accounts.", "info")
    return redirect(url_for('login'))


# ----------- DASHBOARD -----------
@app.route('/dashboard')
@login_required
def dashboard():
    if session['role'] == 'Admin':
        total_users = User.query.count()
        pending_users = User.query.filter_by(status='Pending').count()
        total_products = Product.query.count()
        total_sales = db.session.query(db.func.sum(Sale.total_amount)).scalar() or Decimal('0.00')
        low_stock = Product.query.filter(Product.quantity < 10).count()
        recent_sales = Sale.query.order_by(Sale.date.desc()).limit(10).all()

        stats = {
            'total_users': total_users,
            'pending_users': pending_users,
            'total_products': total_products,
            'total_sales': float(total_sales),
            'low_stock': low_stock
        }

        return render_template('admin_dashboard.html', stats=stats, recent_sales=recent_sales)
    else:
        products = Product.query.filter(Product.quantity > 0).all()
        my_sales = Sale.query.filter_by(sold_by=session['username']).order_by(Sale.date.desc()).limit(10).all()
        my_total = db.session.query(db.func.sum(Sale.total_amount)).filter_by(sold_by=session['username']).scalar() or Decimal('0.00')

        return render_template('cashier_dashboard.html', products=products, my_sales=my_sales, my_total=float(my_total))


# ----------- USER MANAGEMENT -----------
@app.route('/users')
@admin_required
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template('users.html', users=all_users)


@app.route('/create_user', methods=['POST'])
@admin_required
def create_user():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'Cashier')

    if not username or not password:
        flash("Username and password are required.", "error")
        return redirect(url_for('users'))

    if User.query.filter_by(username=username).first():
        flash("Username already exists.", "error")
        return redirect(url_for('users'))

    new_user = User(
        username=username,
        password=generate_password_hash(password),
        role=role,
        status='Approved'  # admin-created accounts are immediately approved
    )
    db.session.add(new_user)
    db.session.commit()
    flash(f"User '{username}' created successfully.", "success")
    return redirect(url_for('users'))


@app.route('/approve_user/<int:user_id>')
@admin_required
def approve_user(user_id):
    user = User.query.get_or_404(user_id)
    user.status = 'Approved'
    db.session.commit()
    flash(f"{user.username} approved successfully.", "success")
    return redirect(url_for('users'))


@app.route('/reject_user/<int:user_id>')
@admin_required
def reject_user(user_id):
    user = User.query.get_or_404(user_id)
    user.status = 'Rejected'
    db.session.commit()
    flash(f"{user.username} rejected.", "error")
    return redirect(url_for('users'))


@app.route('/delete_user/<int:user_id>')
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == session.get('user_id'):
        flash("Cannot delete your own account.", "error")
    else:
        db.session.delete(user)
        db.session.commit()
        flash(f"User {user.username} deleted.", "info")
    return redirect(url_for('users'))


# ----------- INVENTORY MANAGEMENT (CRUD) -----------
@app.route('/inventory')
@admin_required
def inventory():
    products = Product.query.order_by(Product.name).all()
    return render_template('inventory.html', products=products)


@app.route('/add_product', methods=['POST'])
@admin_required
def add_product():
    name = request.form.get('name', '').strip()
    price = request.form.get('price')
    cost = request.form.get('cost', '0')
    quantity = request.form.get('quantity')
    category = request.form.get('category', '').strip()

    if not name or price is None or quantity is None:
        flash("Name, price, and quantity are required.", "error")
        return redirect(url_for('inventory'))

    try:
        new_product = Product(
            name=name,
            price=Decimal(price),
            cost=Decimal(cost or '0.00'),
            quantity=int(quantity),
            category=category
        )
        db.session.add(new_product)
        db.session.commit()
        flash(f"Product '{name}' added successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error adding product: {str(e)}", "error")

    return redirect(url_for('inventory'))


@app.route('/edit_product/<int:id>', methods=['POST'])
@admin_required
def edit_product(id):
    product = Product.query.get_or_404(id)
    try:
        product.name = request.form.get('name', '').strip()
        product.price = Decimal(request.form.get('price', '0'))
        product.cost = Decimal(request.form.get('cost', '0'))
        product.quantity = int(request.form.get('quantity', 0))
        product.category = request.form.get('category', '').strip()
        db.session.commit()
        flash(f"Product '{product.name}' updated successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating product: {str(e)}", "error")
    return redirect(url_for('inventory'))


@app.route('/delete_product/<int:id>')
@admin_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    product_name = product.name
    db.session.delete(product)
    db.session.commit()
    flash(f"Product '{product_name}' deleted successfully.", "info")
    return redirect(url_for('inventory'))


# ----------- SALES -----------
@app.route('/sales', methods=['GET', 'POST'])
@login_required
def sales():
    if session.get('role') != 'Cashier':
        flash("Cashier access required.", "error")
        return redirect(url_for('dashboard'))

    products = Product.query.filter(Product.quantity > 0).all()

    if request.method == 'POST':
        product_id = int(request.form.get('product_id', 0))
        quantity = int(request.form.get('quantity', 0))

        if not product_id or quantity <= 0:
            flash("Invalid product or quantity.", "error")
            return redirect(url_for('sales'))

        product = Product.query.get(product_id)

        if not product:
            flash("Product not found.", "error")
        elif product.quantity < quantity:
            flash(f"Insufficient stock. Only {product.quantity} available.", "error")
        else:
            total_amount = Decimal(product.price) * quantity
            total_cost = Decimal(product.cost) * quantity
            product.quantity -= quantity

            sale = Sale(
                product_id=product_id,
                product_name=product.name,
                quantity_sold=quantity,
                unit_price=product.price,
                unit_cost=product.cost,
                total_amount=total_amount,
                total_cost=total_cost,
                sold_by=session['username']
            )
            db.session.add(sale)
            db.session.commit()
            flash(f"Sold {quantity} {product.name}(s) for ₱{float(total_amount):,.2f}.", "success")

        return redirect(url_for('sales'))

    return render_template('sales.html', products=products)


# ----------- SALES HISTORY -----------
@app.route('/sales_history')
@admin_required
def sales_history():
    all_sales = Sale.query.order_by(Sale.date.desc()).all()
    total_revenue = db.session.query(db.func.sum(Sale.total_amount)).scalar() or Decimal('0.00')
    total_cost = db.session.query(db.func.sum(Sale.total_cost)).scalar() or Decimal('0.00')
    total_profit = (Decimal(total_revenue) - Decimal(total_cost))
    return render_template('sales_history.html',
                           sales=all_sales,
                           total_revenue=float(total_revenue),
                           total_cost=float(total_cost),
                           total_profit=float(total_profit))


# ----------- REPORTS -----------
@app.route('/reports')
@admin_required
def reports():
    # Product sales report with cost/profit/margin (group by product)
    product_sales_raw = db.session.query(
        Product.id,
        Product.name,
        db.func.coalesce(db.func.sum(Sale.quantity_sold), 0).label('total_sold'),
        db.func.coalesce(db.func.sum(Sale.total_amount), 0).label('revenue'),
        db.func.coalesce(db.func.sum(Sale.total_cost), 0).label('cost')
    ).join(Sale, Sale.product_id == Product.id).group_by(Product.id).order_by(db.desc('revenue')).all()

    product_sales = []
    for row in product_sales_raw:
        revenue = Decimal(row.revenue or 0)
        cost = Decimal(row.cost or 0)
        profit = revenue - cost
        margin = (profit / revenue * 100) if revenue > 0 else None
        product_sales.append({
            'id': row.id,
            'name': row.name,
            'total_sold': int(row.total_sold or 0),
            'revenue': float(revenue),
            'cost': float(cost),
            'profit': float(profit),
            'margin': float(margin) if margin is not None else None
        })

    # Cashier performance
    cashier_raw = db.session.query(
        Sale.sold_by,
        db.func.count(Sale.id).label('transactions'),
        db.func.coalesce(db.func.sum(Sale.total_amount), 0).label('revenue'),
        db.func.coalesce(db.func.sum(Sale.total_cost), 0).label('cost')
    ).join(Product, Product.id == Sale.product_id).group_by(Sale.sold_by).order_by(db.desc('revenue')).all()

    cashier_performance = []
    total_rev = Decimal('0.00')
    total_cost = Decimal('0.00')
    for row in cashier_raw:
        revenue = Decimal(row.revenue or 0)
        cost = Decimal(row.cost or 0)
        profit = revenue - cost
        cashier_performance.append({
            'sold_by': row.sold_by,
            'transactions': int(row.transactions or 0),
            'revenue': float(revenue),
            'profit': float(profit)
        })
        total_rev += revenue
        total_cost += cost

    overall_profit = float(total_rev - total_cost)

    return render_template('reports.html',
                           product_sales=product_sales,
                           cashier_performance=cashier_performance,
                           overall_revenue=float(total_rev),
                           overall_cost=float(total_cost),
                           overall_profit=overall_profit)


# ----------- LOGOUT -----------
@app.route('/logout')
def logout():
    username = session.get('username', 'User')
    session.clear()
    flash(f"Goodbye {username}! Logged out successfully.", "info")
    return redirect(url_for('login'))


# ----------- ERROR HANDLERS -----------
@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error="Page not found", code=404), 404


@app.errorhandler(500)
def internal_error(e):
    return render_template('error.html', error="Internal server error", code=500), 500


# -----------------------------
# Run Server
# -----------------------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)