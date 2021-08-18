from flask import Flask, render_template, redirect, url_for, flash, abort, request
from flask_bootstrap import Bootstrap
from flask_ckeditor import CKEditor
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user, login_required
from forms import LoginForm, RegisterForm
import os
import stripe

# This is your real test secret API key.
stripe.api_key = os.getenv('STRIPE_API')
YOUR_DOMAIN = 'http://localhost:5000'

app = Flask(__name__, instance_path='/instance')
app.config['SECRET_KEY'] = '8BYkEfBA6O6donzWlSihBXox7C0sKR6b'
ckeditor = CKEditor(app)
Bootstrap(app)

# CONNECT TO DB
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///eCommerce.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)


# CONFIGURE TABLE
class User(UserMixin, db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    name = db.Column(db.String(100))
    user_cart = relationship('Cart', backref='user', uselist=False)


class Cart(db.Model):
    __tablename__ = "cart"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True)
    products_in_cart = relationship("ProductsInCart", backref='cart')


class ProductsInCart(db.Model):
    __tablename__ = "productsincart"
    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.Integer, db.ForeignKey('cart.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), unique=True)
    quantity = db.Column(db.Integer, nullable=False)


class Products(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    description = db.Column(db.String(200))
    price = db.Column(db.FLOAT)
    img = db.Column(db.String(1000))
    product_stripe_id = db.Column(db.String(50), nullable=False)
    price_stripe_id = db.Column(db.String(50), nullable=False)
    product_in_cart = relationship("ProductsInCart", backref='products')


# db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.id != 1:
            return abort(403)
        return f(*args, **kwargs)

    return decorated_function


@app.route('/fetch_new_products_from_stripe', methods=['GET'])
@admin_only
def fetch_new_products_from_stripe():
    product_list = stripe.Product.list(active=True)['data']
    price_list = stripe.Price.list(active=True)['data']

    products_in_db = db.session.query(Products).all()
    # Creating variables for each product in product_list
    if product_list:
        for product_info in product_list:
            product_name = product_info.name
            product_description = product_info.description
            price = ''
            price_stripe_id = ''
            for price_info in price_list:
                if product_info.id == price_info.product:
                    raw_price = str(price_info.unit_amount)
                    price = float(f'{raw_price[:len(raw_price) - 2]}.{raw_price[-2:]}')
                if product_info.id == price_info.product:
                    price_stripe_id = price_info.id
            img = ''
            if product_info.images:
                img = product_info.images[0]
            product_stripe_id = product_info.id

            # If Products table is not empty, check if product already exist:
            if len(products_in_db) > 0:
                for product in products_in_db:
                    try:
                        if product_name == product.name:
                            pass
                    except Exception:
                        pass
                else:
                    try:
                        product_to_add = Products(name=product_name,
                                                  description=product_description,
                                                  price=price,
                                                  img=img,
                                                  price_stripe_id=price_stripe_id,
                                                  product_stripe_id=product_stripe_id)
                        db.session.add(product_to_add)
                        db.session.commit()
                    except Exception:
                        pass
            # If Products table is empty, insert every product.
            else:
                try:
                    product_to_add = Products(name=product_name,
                                              description=product_description,
                                              price=price,
                                              img=img,
                                              price_stripe_id=price_stripe_id,
                                              product_stripe_id=product_stripe_id)
                    db.session.add(product_to_add)
                    db.session.commit()
                except Exception:
                    pass
        flash('Successfully Fetched Products From Stripe')
        return redirect('/#message')
    else:
        flash('No Products In Stripe Site')
        flash('Add Some Products First')
        return redirect('/#message')


@app.route('/', methods=['GET', 'POST'])
def home():
    all_products = db.session.query(Products).all()

    return render_template("index.html", all_products=all_products, current_user=current_user)


@app.route("/add-to-cart/<int:product_id>", methods=["POST"])
def add_to_cart(product_id):
    if request.method == 'POST':
        # Check if user is authenticated
        if current_user.is_authenticated is False:
            flash("Please Login First, Or Register if You Do Not Have an Account")
            return redirect('/login')

        quantity = int(request.form["quantity"])
        # Check if product is already in cart

        products_in_cart = ProductsInCart.query.filter_by(cart_id=current_user.user_cart.id,
                                                          product_id=product_id).all()

        # Check if there are products in cart
        if len(products_in_cart) == 0:
            product_to_add = ProductsInCart(cart_id=current_user.user_cart.id,
                                            product_id=product_id,
                                            quantity=quantity)
            db.session.add(product_to_add)
            db.session.commit()
            flash("Item Added To Cart")
            return redirect("/#message")
        else:
            product_to_update = ProductsInCart.query.filter_by(product_id=product_id).first()
            if quantity != product_to_update.quantity:
                product_to_update.quantity = quantity
                db.session.commit()
                flash("Quantity of Item Has Been Updated")
                return redirect("/#message")
            else:
                flash("Product is already in cart with the same quantity.")
                return redirect("/#message")


@app.route('/delete-from-cart/<int:item_id>', methods=["POST"])
@login_required
def delete_from_cart(item_id):
    if request.method == 'POST':
        try:
            item_to_delete = ProductsInCart.query.get(item_id)
            db.session.delete(item_to_delete)
            db.session.commit()

        except Exception as e:
            return str(e)
        print(len(ProductsInCart.query.filter_by(cart_id=current_user.user_cart.id).all()))
        if len(ProductsInCart.query.filter_by(cart_id=current_user.user_cart.id).all()) == 0:
            flash('No Products In Cart')
            return redirect('/')
        else:
            return redirect('/cart#cart')


@app.route('/update-qty-from-cart', methods=["POST"])
@login_required
def update_qty_from_cart():
    if request.method == 'POST':
        form_args_list = request.form
        changes_made = 0
        for item in form_args_list.items():
            id_in_cart = int(item[0][7])
            qty = int(item[1])

            try:
                product_to_update = ProductsInCart.query.get(id_in_cart)
                if product_to_update.quantity != qty:
                    product_to_update.quantity = qty
                    db.session.commit()
                    changes_made += 1
            except Exception as e:
                return str(e)
        if changes_made > 0:
            flash('Cart Has Been Updated.')
            return redirect('/cart#cart')
        else:
            flash('No Changes Has Been Made.')
            return redirect('/cart#cart')

@app.route(f"/cart", methods=["GET"])
@login_required
def show_cart():
    if request.method == 'GET':
        users_cart = Cart.query.filter_by(user_id=current_user.id).first()
        products_in_cart = users_cart.products_in_cart
        if len(products_in_cart) > 0:
            sum_amount = 0
            for product in products_in_cart:
                sum_amount += product.quantity * product.products.price
            return render_template("cart.html", current_user=current_user,
                                   products_in_cart=products_in_cart,
                                   sum_amount=sum_amount)
        else:
            flash('No Products In Cart')
            return redirect('/#message')


@app.route("/add-product")
@admin_only
def add_product():
    return redirect('https://dashboard.stripe.com/test/products?active=true')


@app.route('/create-checkout-session', methods=['GET'])
def create_checkout_session():
    try:
        requested_cart = Cart.query.filter_by(user_id=current_user.id).first().products_in_cart
        line_items = []
        for item in requested_cart:
            line_items.append({"price": item.products.price_stripe_id, 'quantity': item.quantity})
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items,
            mode='payment',
            success_url=YOUR_DOMAIN + '/success#payment-successful',
            cancel_url=YOUR_DOMAIN + '/',
        )
    except Exception as e:
        return str(e)

    return redirect(checkout_session.url, code=303)


@app.route('/cancel')
def cancel():
    return 'Transaction Canceled'


@app.route('/success')
def success():
    # Clear the cart
    current_cart = User.query.get(current_user.id).user_cart.products_in_cart
    for item in current_cart:
        db.session.delete(item)
        db.session.commit()
    return render_template('success.html')


@app.route('/register', methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():

        if User.query.filter_by(email=form.email.data).first():
            # User already exists
            flash("You've already signed up with that email, log in instead!")
            return redirect(url_for('login'))

        hash_and_salted_password = generate_password_hash(
            form.password.data,
            method='pbkdf2:sha256',
            salt_length=8
        )
        new_user = User(
            email=form.email.data,
            name=form.name.data,
            password=hash_and_salted_password,
        )
        cart = Cart(user=new_user)
        db.session.add(new_user, cart)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for("home"))

    return render_template("register.html", form=form, current_user=current_user)


@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data

        user = User.query.filter_by(email=email).first()
        # Email doesn't exist or password incorrect.
        if not user:
            flash("That email does not exist, please try again.")
            return redirect(url_for('login'))
        elif not check_password_hash(user.password, password):
            flash('Password incorrect, please try again.')
            return redirect(url_for('login'))
        else:
            login_user(user)
            return redirect(url_for('home'))
    return render_template("login.html", form=form, current_user=current_user)


@app.route("/about")
def about():
    return render_template("about.html", current_user=current_user)


@app.route("/contact")
def contact():
    return render_template("contact.html", current_user=current_user)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
