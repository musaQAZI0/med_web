import requests

PHP_BRIDGE_URL = "https://medfellows.app/db_query.php"

def find_valid_questions():
    """
    Find questions that have a correct answer marked (isCorrectAnswer = 1)
    """
    print("Searching for questions with correct answers marked...\n")

    # Get questions with correct answers
    query = """
        SELECT DISTINCT q.questionId
        FROM tblquestion q
        INNER JOIN tblquestionoption opt ON opt.questionId = q.questionId
        WHERE opt.isCorrectAnswer = '1'
        LIMIT 20
    """

    response = requests.post(PHP_BRIDGE_URL, data={"query": query})
    data = response.json()

    if data.get("error"):
        print(f"Error: {data['error']}")
        return

    questions = data.get("data", [])

    if not questions:
        print("No questions found with correct answers marked!")
        return

    print(f"Found {len(questions)} questions with correct answers:\n")

    for q in questions[:10]:
        question_id = q['questionId']
        print(f"Question ID: {question_id}")

        # Get details for this question
        query_details = f"""
            SELECT q.questionId, q.question,
                   (SELECT COUNT(*) FROM tblquestionoption WHERE questionId = q.questionId) as option_count,
                   (SELECT COUNT(*) FROM tblquestionoption WHERE questionId = q.questionId AND isCorrectAnswer = '1') as correct_count
            FROM tblquestion q
            WHERE q.questionId = '{question_id}'
        """

        response_details = requests.post(PHP_BRIDGE_URL, data={"query": query_details})
        details = response_details.json().get("data", [])

        if details:
            d = details[0]
            print(f"  Options: {d.get('option_count')}")
            print(f"  Correct answers: {d.get('correct_count')}")
            print(f"  Has description: {bool(d.get('description'))}")

        print("-" * 60)

    # Return first valid question ID
    if questions:
        first_id = questions[0]['questionId']
        print(f"\n✓ You can use Question ID: {first_id}")
        return first_id

if __name__ == "__main__":
    find_valid_questions()
