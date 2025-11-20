"""
Simple count of questions with multiple topics
"""
from modules.database import execute_query

# Get a small sample
query = """
SELECT questionId, COUNT(DISTINCT topicId) as topic_count
FROM topicQueRel
GROUP BY questionId
HAVING COUNT(DISTINCT topicId) > 1
LIMIT 5
"""

result = execute_query(query)

if "data" in result:
    print(f"\nFound {len(result['data'])} questions (showing first 5):\n")
    for row in result['data']:
        print(f"Question ID: {row['questionId']} belongs to {row['topic_count']} topics")
else:
    print(f"Error: {result}")
