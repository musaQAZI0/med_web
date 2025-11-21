"""
List all categories to find the correct name
"""
from modules.database import execute_query

query = "SELECT id, categoryName FROM category"
result = execute_query(query)

if result.get("data"):
    print("Categories in database:")
    for cat in result["data"]:
        print(f"  ID: {cat['id']}, Name: '{cat['categoryName']}'")
else:
    print(f"Error: {result}")
