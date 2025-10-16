from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import pymysql

# -----------------------------
# Flask Config
# -----------------------------
app = Flask(__name__)
app.secret_key = "pos_inventory_secret"

# -----------------------------
# MySQL Config
# -----------------------------
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:2006@localhost:3306/pos_inventory_db'    # edit your password if any
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

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

class Sale(db.Model):
    __tablename__ = 'sales'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity_sold = db.Column(db.Integer, nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    sold_by = db.Column(db.String(100))
    date = db.Column(db.DateTime, server_default=db.func.current_timestamp())

# -----------------------------
# Initial Setup (create tables and admin)
# -----------------------------
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password=generate_password_hash('admin123'), role='Admin', status='Approved')
        db.session.add(admin)
        db.session.commit()

# -----------------------------
# Routes
# -----------------------------

@app.route('/')
def home():
    return redirect(url_for('login'))

# ----------- LOGIN -----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
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

# ----------- REGISTER -----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        confirm = request.form['confirm'].strip()

        if password != confirm:
            flash("Passwords do not match.", "error")
        elif User.query.filter_by(username=username).first():
            flash("Username already exists.", "error")
        else:
            new_user = User(username=username,
                            password=generate_password_hash(password),
                            role='Cashier',
                            status='Pending')
            db.session.add(new_user)
            db.session.commit()
            flash("Registration submitted. Awaiting admin approval.", "info")
            return redirect(url_for('login'))
    return render_template('register.html')

# ----------- DASHBOARD -----------
@app.route('/dashboard')
def dashboard():
    if 'role' not in session:
        return redirect(url_for('login'))

    if session['role'] == 'Admin':
        users = User.query.all()
        return render_template('admin_dashboard.html', users=users)
    else:
        products = Product.query.all()
        return render_template('sales.html', products=products)

# ----------- APPROVE USER -----------
@app.route('/approve_user/<int:user_id>')
def approve_user(user_id):
    if session.get('role') != 'Admin':
        return redirect(url_for('login'))
    user = User.query.get_or_404(user_id)
    user.status = 'Approved'
    db.session.commit()
    flash(f"{user.username} approved.", "success")
    return redirect(url_for('dashboard'))

# ----------- REJECT USER -----------
@app.route('/reject_user/<int:user_id>')
def reject_user(user_id):
    if session.get('role') != 'Admin':
        return redirect(url_for('login'))
    user = User.query.get_or_404(user_id)
    user.status = 'Rejected'
    db.session.commit()
    flash(f"{user.username} rejected.", "error")
    return redirect(url_for('dashboard'))

# ----------- INVENTORY MANAGEMENT -----------
@app.route('/inventory')
def inventory():
    if session.get('role') != 'Admin':
        return redirect(url_for('login'))
    products = Product.query.all()
    return render_template('inventory.html', products=products)

@app.route('/add_product', methods=['POST'])
def add_product():
    if session.get('role') != 'Admin':
        return redirect(url_for('login'))
    name = request.form['name']
    price = request.form['price']
    quantity = request.form['quantity']
    new_product = Product(name=name, price=price, quantity=quantity)
    db.session.add(new_product)
    db.session.commit()
    flash("Product added successfully.", "success")
    return redirect(url_for('inventory'))

@app.route('/edit_product/<int:id>', methods=['POST'])
def edit_product(id):
    if session.get('role') != 'Admin':
        return redirect(url_for('login'))
    product = Product.query.get_or_404(id)
    product.name = request.form['name']
    product.price = request.form['price']
    product.quantity = request.form['quantity']
    db.session.commit()
    flash("Product updated successfully.", "success")
    return redirect(url_for('inventory'))

@app.route('/delete_product/<int:id>')
def delete_product(id):
    if session.get('role') != 'Admin':
        return redirect(url_for('login'))
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    flash("Product deleted successfully.", "info")
    return redirect(url_for('inventory'))

# ----------- SALES -----------
@app.route('/sales', methods=['GET', 'POST'])
def sales():
    if session.get('role') != 'Cashier':
        return redirect(url_for('login'))
    products = Product.query.all()

    if request.method == 'POST':
        product_id = int(request.form['product_id'])
        quantity = int(request.form['quantity'])
        product = Product.query.get(product_id)

        if not product or product.quantity < quantity:
            flash("Insufficient stock.", "error")
        else:
            total_amount = product.price * quantity
            product.quantity -= quantity
            sale = Sale(product_id=product_id, quantity_sold=quantity,
                        total_amount=total_amount, sold_by=session['username'])
            db.session.add(sale)
            db.session.commit()
            flash(f"Sold {quantity} {product.name}(s) for ₱{total_amount:.2f}.", "success")
        return redirect(url_for('sales'))
    return render_template('sales.html', products=products)

# ----------- LOGOUT -----------
@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for('login'))

# -----------------------------
# Run Server
# -----------------------------
if __name__ == '__main__':
    app.run(debug=True)
