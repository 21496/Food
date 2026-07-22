import os
import requests
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///recipes.db'
app.secret_key = os.getenv("SECRET_KEY")
db = SQLAlchemy(app)


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

api_key = os.getenv("API_KEY")


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

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
    submit = SubmitField("Register")


def search_recipes(query):
    url = "https://api.spoonacular.com/recipes/complexSearch"

    params = {
        "apiKey": api_key,
        "query": query,
        "number": 5
    }

    response = requests.get(url, params=params)
    return response.json()

@app.route("/")
def home():
    query = request.args.get("query", "chicken")
    data = search_recipes(query)
    recipes = data.get("results", [])
    return render_template("home.html", recipes = recipes, query = query)

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


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
