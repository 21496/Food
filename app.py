"""Recipe website built with Flask and Spoonacular API"""
import os
import time

import requests
from flask import Flask, render_template, request, redirect, url_for, flash, abort, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, login_required, logout_user, current_user
)
from flask_wtf import FlaskForm
from flask_caching import Cache
from dotenv import load_dotenv
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.exceptions import HTTPException

# Loads in SECRET_KEY and API_KEY from the .env file
load_dotenv()


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///recipes.db'

# Only these image types can be uploaded
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024


app.secret_key = os.getenv("SECRET_KEY")
db = SQLAlchemy(app)

# Cache API responses in memmory to save on daily request limit
cache = Cache(app, config={"CACHE_TYPE": "SimpleCache"})

login_manager = LoginManager()
login_manager.init_app(app)
# logged out users who try to open a protected page are sent to the login page
login_manager.login_view = "login"

api_key = os.getenv("API_KEY")


class User(db.Model, UserMixin):
    """A registered user. Passwords are hashed"""

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)


class Favourite(db.Model):
    """A Spoonacular recipe that the user has saved to favourites"""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    recipe_id = db.Column(db.String(50), nullable=False)
    # Stops users favouriting the same recipe twice
    __table_args__ = (db.UniqueConstraint("user_id", "recipe_id", name="unique_user_recipe"),)


class UserRecipe(db.Model):
    """The users uploaded recipe"""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    cuisine = db.Column(db.String(50), nullable=False)
    cook_time = db.Column(db.String(50), nullable=False)
    image = db.Column(db.String(300))
    ingredients = db.Column(db.Text, nullable=False)
    method = db.Column(db.Text, nullable=False)


@login_manager.user_loader
def load_user(user_id):
    """Load a user from the database by id so flask login can track who is logged in"""
    return User.query.get(int(user_id))


class LoginForm(FlaskForm):
    """Form to login with user and password"""

    username = StringField(
        "Username",
        validators=[DataRequired(), Length(min=3, max=100)])

    password = PasswordField(
        "Password",
        validators=[DataRequired()])
    submit = SubmitField("Login")


class RegisterForm(FlaskForm):
    """Form creating an account"""
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
    """Show the home page with search results, random recipes or popular"""
    query = request.args.get("query")
    mode = request.args.get("mode", "popular")

    # If the API limit was hit recently, skip API calls and show no recipes
    disabled_until = session.get("api_disabled_until")
    if disabled_until and time.time() < disabled_until:
        recipes = []

    else:
        # the request limit is clear, clear it and use that API again
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
    """Search the Spoonacular for recipes matching the query and return the JSON, 
    Results are cached for 5 minutes so repeat searches don't use up API requests"""
    url = "https://api.spoonacular.com/recipes/complexSearch"

    params = {
        "apiKey": api_key,
        "query": query,
        "number": 20,
        "addRecipeInformation": True
    }

    response = requests.get(url, params=params, timeout=10)
    # Any failed responses (daily limit) triggers the 503 page
    if response.status_code != 200:
        abort(503)
    return response.json()


@cache.memoize(timeout=300)
def get_popular_recipes():
    """Get the most popular main course recipes from Spoonacular as JSON (cached 5 mins)"""
    url = "https://api.spoonacular.com/recipes/complexSearch"

    params = {
        "apiKey": api_key,
        "number": 20,
        "sort": "popularity",
        "type": "main course",
        "addRecipeInformation": True
    }

    response = requests.get(url, params=params, timeout=10)
    if response.status_code != 200:
        abort(503)
    return response.json()


def get_random_recipes():
    """Gets a random recipe from the API and return them as JSON"""
    url = "https://api.spoonacular.com/recipes/random"

    params = {
        "apiKey": api_key,
        "number": 20,
    }
    response = requests.get(url, params=params, timeout=10)
    if response.status_code != 200:
        abort(503)
    return response.json()


@app.route("/favourites")
@login_required
def favourites():
    """Show the logged in user's favourite recipes and their own uploaded recipes"""
    favourite_rows = Favourite.query.filter_by(user_id=current_user.id).all()
    recipes = []
    for favourite_row in favourite_rows:
        try:
            recipe_data = get_recipe(favourite_row.recipe_id)
            if recipe_data:
                recipes.append(recipe_data)
        except HTTPException:
            # Skip any recipe that can't be loaded so the page still works (API down)
            continue

    uploaded_recipes = UserRecipe.query.filter_by(
        user_id=current_user.id).all()
    return render_template("favourites.html",recipes=recipes, uploaded_recipes=uploaded_recipes)


@app.route("/favourite/<int:recipe_id>", methods=["POST"])
@login_required
def favourite(recipe_id):
    """Add a recipe to the user's favouites, or remove it if its allready saved"""
    existing_favourite = Favourite.query.filter_by(
        user_id=current_user.id,
        recipe_id=str(recipe_id)
    ).first()

    if existing_favourite:
        db.session.delete(existing_favourite)
        db.session.commit()

    else:
        new_favourite = Favourite(user_id=current_user.id,recipe_id=str(recipe_id))
        db.session.add(new_favourite)
        db.session.commit()

    # Send the user back to the page they came from
    return redirect(
        request.referrer or url_for("home")
    )


@app.route("/uploaded-recipe/<int:recipe_id>")
@login_required
def uploaded_recipe(recipe_id):
    """Show one of the user's own uploadede recipes"""
    user_recipe = UserRecipe.query.get_or_404(recipe_id)

    # Users can only view their own uploads, any else shows a 404
    if user_recipe.user_id != current_user.id:
        abort(404)

    return render_template("recipe.html", recipe=user_recipe, uploaded=True, is_favourite=False)


def allowed_file(filename):
    """Return True if the file name ends with an allowed image extension"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    """Show the upload or save a new recipe"""
    if request.method == "POST":
        recipe_name = request.form.get("recipe_name")
        cuisine = request.form.get("cuisine")
        cook_time = request.form.get("cook_time")
        method = request.form.get("method")

        # Each ingredient row has a quantity box and an ingredient box
        quantities = request.form.getlist("quantity[]")
        ingredients = request.form.getlist("ingredient[]")
        recipe_ingredients = []
        for quantity, ingredient in zip(quantities, ingredients):
            if ingredient.strip():
                recipe_ingredients.append(
                    f"{quantity} {ingredient}".strip()
                )

        image = request.files.get("recipe_image")
        image_filename = None
        # Only save an image if one was actaully chosen
        if image and image.filename:
            # secure_filename removes unsafe characters from the file name
            safe_name = secure_filename(image.filename)
            # Reject anything that is not an allowed image type
            if not allowed_file(safe_name):
                flash("Only PNG, JPG, JPEG, GIF or WEBP images are allowed")
                return redirect(url_for("upload"))
            # Prefix with user id and time so files with the same name don't overwrite each other
            image_filename = f"{current_user.id}_{int(time.time())}_{safe_name}"
            upload_folder = os.path.join(
                app.root_path,
                "static",
                "uploads"
            )
            os.makedirs(upload_folder, exist_ok=True)
            image.save(
                os.path.join(upload_folder, image_filename)
            )

        new_recipe = UserRecipe(user_id=current_user.id, name=recipe_name,
            cuisine=cuisine, cook_time=cook_time, image=image_filename,
            ingredients="\n".join(recipe_ingredients), method=method)
        db.session.add(new_recipe)
        db.session.commit()
        return redirect(url_for("home"))
    return render_template("upload.html")


@app.route("/recipe/<int:recipe_id>")
def recipe(recipe_id):
    """Show a single recipe, either a user upload or Spoonacular recipe"""
    # Check the database first, so uploaded recipes don't use an API request
    user_recipe = UserRecipe.query.get(recipe_id)

    if user_recipe:
        return render_template(
            "recipe.html",
            recipe=user_recipe,
            uploaded=True,
            is_favourite=False
            )

    # If the API has hit the limit, send the user back to the home page
    disabled_until = session.get("api_disabled_until")
    if disabled_until and time.time() < disabled_until:
        return redirect(url_for("home"))
    session.pop("api_disabled_until", None)

    recipe_data = get_recipe(recipe_id)
    is_favourite = False

    # Only logged in users can have favourites
    if current_user.is_authenticated:
        is_favourite = Favourite.query.filter_by(
            user_id=current_user.id,
            recipe_id=str(recipe_id)
        ).first() is not None

    return render_template("recipe.html", recipe=recipe_data, is_favourite=is_favourite)


@cache.memoize(timeout=300)
def get_recipe(recipe_id):
    """Get the full detail of one recipe from Spoonacular as JSON (cached 5 min)"""
    url = f"https://api.spoonacular.com/recipes/{recipe_id}/information"

    params = {
        "apiKey": api_key,
        "includeNutrition": False
    }

    try:
        # The timeout stops the site hanging if the API is slow to respond
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            abort(503)
        return response.json()
    except requests.exceptions.RequestException:
        abort(503)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log a user in if their username and passowrd are correct"""
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(
            username=form.username.data).first()

        # Compare the typed password against the stored hash
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
    """Log the current user out and return to the home page"""
    logout_user()
    return redirect(url_for("home"))


@app.route("/register", methods=["GET", "POST"])
def register():
    """Create a new account, refusing usernames that already exist"""
    form = RegisterForm()
    if form.validate_on_submit():
        existing_user = User.query.filter_by(
            username=form.username.data
        ).first()
        if existing_user:
            flash("Username already exists")
            return redirect(url_for("register"))
        # Hash the password before saving
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
def page_not_found(_error):
    """Show the custom 404 page when a page is not found"""
    return render_template('404.html'), 404


@app.errorhandler(413)
def file_too_large(_error):
    """Tell the user when an upload is over the 5 MB limit and send them back to the form"""
    flash("That file is too large. The limit is 5 MB.")
    return redirect(url_for("upload"))


@app.errorhandler(503)
def service_unavailable(_error):
    """Shows the custom 503 page when the API daily limit is reached or fails,
    Also pauses API calls for 10 mins so that the rest of the site can work"""
    session["api_disabled_until"] = time.time() + 600  # 10 minutes
    return render_template("503.html"), 503


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

