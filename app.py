import os
import requests
import time
from flask import Flask, render_template, request, redirect, url_for, flash, abort, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from flask_caching import Cache
from dotenv import load_dotenv
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///recipes.db'
app.secret_key = os.getenv("SECRET_KEY")
db = SQLAlchemy(app)
cache = Cache(app, config={"CACHE_TYPE": "SimpleCache"})

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

api_key = os.getenv("API_KEY")


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Favourite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    recipe_id = db.Column(db.String(50), nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class LoginForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[DataRequired(), Length(min=3, max=100)])

    password = PasswordField(
        "Password",
        validators=[DataRequired()])
    submit = SubmitField("Login")

class RegisterForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[DataRequired(), Length(min=3)])
    
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=6)])

    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match.")])
    submit = SubmitField("Register")




@app.route("/")
def home():
    query = request.args.get("query")
    mode = request.args.get("mode", "popular")
    disabled_until = session.get("api_disabled_until")
    if disabled_until and time.time() < disabled_until:
        recipes = []

    else:
        session.pop("api_disabled_until", None)
        if query:
            data = search_recipes(query)
            recipes = data.get("results", [])

        elif mode == "random":
            data = get_random_recipes()
            recipes = data.get("recipes", [])

        else:
            data = get_popular_recipes()
            recipes = data.get("results", [])
    return render_template("home.html", recipes = recipes, query = query, mode = mode)

@cache.memoize(timeout=300)
def search_recipes(query):
    url = "https://api.spoonacular.com/recipes/complexSearch"

    params = {
        "apiKey": api_key,
        "query": query,
        "number": 20,
        "addRecipeInformation": True
    }

    response = requests.get(url, params=params)
    if response.status_code != 200:
        abort(503)
    return response.json()

@cache.memoize(timeout=300)
def get_popular_recipes():
    url = "https://api.spoonacular.com/recipes/complexSearch"

    params = {
        "apiKey": api_key,
        "number": 20,
        "sort": "popularity",
        "type": "main course",
        "addRecipeInformation": True
    }

    response = requests.get(url, params=params)
    if response.status_code != 200:
        abort(503)
    return response.json()

def get_random_recipes():
    url = "https://api.spoonacular.com/recipes/random"

    params = {
        "apiKey": api_key,
        "number": 20,
    }

    response = requests.get(url, params=params)
    if response.status_code != 200:
        abort(503)
    return response.json()



@app.route("/favourites")
@login_required
def favourites():

    favourites = Favourite.query.filter_by(user_id=current_user.id).all()
    return render_template("favourites.html", favourites=favourites)

@app.route("/upload")
@login_required
def upload():
    return render_template("upload.html")


@app.route("/recipe/<int:recipe_id>")
def recipe(recipe_id):
    disabled_until = session.get("api_disabled_until")
    if disabled_until and time.time() < disabled_until:
        return redirect(url_for("home"))
    else:
        session.pop("api_disabled_until", None)
    recipe = get_recipe(recipe_id)
    return render_template("recipe.html", recipe=recipe,)


@cache.memoize(timeout=300)
def get_recipe(recipe_id):
    url = f"https://api.spoonacular.com/recipes/{recipe_id}/information"

    params = {
        "apiKey": api_key,
        "includeNutrition": False
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            abort(503)
        return response.json()
    except requests.exceptions.RequestException:
        abort(503)


@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(
            username=form.username.data).first()
        
        if user and check_password_hash(
            user.password,
            form.password.data):
            login_user(user)
            flash("Login successful!")
            return redirect(url_for("home"))
        else:
            flash("Invalid username or password")

    return render_template(
        "login.html",
        form=form
    )

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))

@app.route("/register", methods=["GET", "POST"])
def register():

    form = RegisterForm()
    if form.validate_on_submit():
        existing_user = User.query.filter_by(
            username=form.username.data
        ).first()
        if existing_user:
            flash("Username already exists")
            return redirect(url_for("register"))
        hashed_password = generate_password_hash(
            form.password.data)
        new_user = User(
            username=form.username.data,
            password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash("Account created successfully!")
        return redirect(url_for("login"))

    return render_template(
        "register.html",
        form=form)

@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(503)
def service_unavailable(error):
    session["api_disabled_until"] = time.time() + 600  # 10 minutes
    return render_template("503.html"), 503

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
