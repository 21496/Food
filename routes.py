import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("API_KEY")

headers = {"Authorization": f"Bearer {api_key}"}
response = requests.get(f"https://api.spoonacular.com/recipes/716429/information?apiKey={api_key}&includeNutrition=false", headers=headers)

print(response.json())

#https://api.spoonacular.com/recipes/716429/information?apiKey={api_key}&includeNutrition=true

