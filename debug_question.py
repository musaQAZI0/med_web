import requests

# PHP Bridge URL
PHP_BRIDGE_URL = "https://medfellows.app/db_query.php"

def debug_question(question_id):
    """
    Debug why a question ID is not being found
    """
    print(f"=== DEBUGGING QUESTION ID: {question_id} ===\n")

    # Step 1: Check if question exists in tblquestion
    print("Step 1: Checking if question exists in tblquestion table...")
    query1 = f"SELECT * FROM tblquestion WHERE questionId = {question_id}"

    response1 = requests.post(PHP_BRIDGE_URL, data={"query": query1})
    data1 = response1.json()

    if data1.get("error"):
        print(f"ERROR: {data1['error']}\n")
        return

    question_data = data1.get("data", [])
    print(f"Found {len(question_data)} records")

    if question_data:
        try:
            print(f"Question data keys: {list(question_data[0].keys())}")
        except:
            pass
        print(f"QuestionId type: {type(question_data[0].get('questionId'))}")
        print(f"QuestionId value: {question_data[0].get('questionId')}")
    else:
        print("No question found with this ID!")
        print(f"Response: {data1}\n")

        # Try to find similar IDs
        print("\nSearching for similar question IDs...")
        query_similar = "SELECT questionId FROM tblquestion LIMIT 20"
        response_similar = requests.post(PHP_BRIDGE_URL, data={"query": query_similar})
        similar_data = response_similar.json()
        if similar_data.get("data"):
            print(f"Found these question IDs: {[q['questionId'] for q in similar_data['data'][:10]]}")
        return

    print()

    # Step 2: Check options for this question
    print("Step 2: Checking options in tblquestionoption table...")
    query2 = f"SELECT * FROM tblquestionoption WHERE questionId = {question_id}"

    response2 = requests.post(PHP_BRIDGE_URL, data={"query": query2})
    data2 = response2.json()

    if data2.get("error"):
        print(f"ERROR: {data2['error']}\n")
        return

    options_data = data2.get("data", [])
    print(f"Found {len(options_data)} options")

    if options_data:
        for i, opt in enumerate(options_data, 1):
            print(f"  Option {i}: isCorrectAnswer={opt.get('isCorrectAnswer')} (type: {type(opt.get('isCorrectAnswer'))})")
    else:
        print("No options found for this question!")

    print()

    # Step 3: Check if question is linked to any topic
    print("Step 3: Checking topic relations in topicQueRel table...")
    query3 = f"SELECT * FROM topicQueRel WHERE questionId = {question_id}"

    response3 = requests.post(PHP_BRIDGE_URL, data={"query": query3})
    data3 = response3.json()

    if data3.get("error"):
        print(f"ERROR: {data3['error']}\n")
        return

    topic_data = data3.get("data", [])
    print(f"Found {len(topic_data)} topic relations")

    if topic_data:
        for rel in topic_data:
            print(f"  Topic ID: {rel.get('topicId')}")
    else:
        print("This question is not linked to any topic!")

    print()

    # Step 4: Test the exact query used in the code
    print("Step 4: Testing exact query from process_single_question_explanation...")
    query4 = f"SELECT questionId, question FROM tblquestion WHERE questionId = {question_id}"

    response4 = requests.post(PHP_BRIDGE_URL, data={"query": query4})
    data4 = response4.json()

    print(f"Query: {query4}")
    print(f"Response data count: {len(data4.get('data', []))}")
    print(f"Full response: {data4}")

    print()

    # Step 5: Try with string parameter
    print("Step 5: Testing with questionId as string (in quotes)...")
    query5 = f"SELECT questionId, question FROM tblquestion WHERE questionId = '{question_id}'"

    response5 = requests.post(PHP_BRIDGE_URL, data={"query": query5})
    data5 = response5.json()

    print(f"Query: {query5}")
    print(f"Response data count: {len(data5.get('data', []))}")
    print(f"Full response: {data5}")

if __name__ == "__main__":
    debug_question(6561)
