import os
import requests
from flask import Flask, render_template, request, redirect
from dotenv import load_dotenv
from models import db


load_dotenv()


app = Flask(__name__)


app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///recipes.db'
db.init_app(app)


api_key = os.getenv("API_KEY")

url = "https://api.spoonacular.com/recipes/complexSearch"

params = {
    "apiKey": api_key,
    "includeNutrition": "false",
    "number": "5"
}

response = requests.get(url, params=params)

# print(response.json())

#https://api.spoonacular.com/recipes/716429/information?apiKey={api_key}&includeNutrition=true


@app.route("/")
def home():
    data = search_recipes("chicken")
    return render_template("results.html", recipes=data["results"])


# @app.route("/my-recipes")
# def my_recipes():
#     recipes = Recipe.query.all()
#     return render_template("home.html", recipes = recipes)

print(response.status_code)
print(response.text)

if __name__ == '__main__':
    app.run(debug=True)