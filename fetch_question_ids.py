import requests
import json

# PHP Bridge URL
PHP_BRIDGE_URL = "https://medfellows.app/db_query.php"

def fetch_question_ids(limit=10):
    """
    Fetch sample question IDs from the database
    """
    # Query to get some question IDs
    query = f"SELECT questionId, question FROM tblquestion LIMIT {limit}"

    payload = {
        "query": query
    }

    try:
        print(f"Fetching question IDs from: {PHP_BRIDGE_URL}")
        print(f"Query: {query}\n")

        response = requests.post(PHP_BRIDGE_URL, data=payload)
        response.raise_for_status()

        data = response.json()

        if data.get("error"):
            print(f"Error: {data['error']}")
            return None

        questions = data.get("data", [])

        if questions:
            print(f"Found {len(questions)} questions:\n")
            print("-" * 80)
            for q in questions:
                question_id = q.get("questionId")
                try:
                    question_text = q.get("question", "")[:100]  # First 100 chars
                    print(f"Question ID: {question_id}")
                    print(f"Question: {question_text}...")
                except UnicodeEncodeError:
                    print(f"Question ID: {question_id}")
                    print(f"Question: [Contains special characters]")
                print("-" * 80)

            # Return the first question ID for easy use
            return questions[0].get("questionId")
        else:
            print("No questions found in database")
            return None

    except Exception as e:
        print(f"Error fetching questions: {str(e)}")
        return None


def fetch_question_with_options(question_id):
    """
    Fetch a specific question with its options
    """
    # Get question details
    query_question = f"SELECT questionId, question, description FROM tblquestion WHERE questionId = {question_id}"

    payload = {
        "query": query_question
    }

    try:
        print(f"\nFetching question {question_id} details...")
        response = requests.post(PHP_BRIDGE_URL, data=payload)
        response.raise_for_status()

        data = response.json()
        question_data = data.get("data", [])

        if not question_data:
            print(f"Question {question_id} not found")
            return

        question = question_data[0]

        # Get options
        query_options = f"SELECT questionImageText, isCorrectAnswer FROM tblquestionoption WHERE questionId = {question_id}"

        payload_options = {
            "query": query_options
        }

        response_options = requests.post(PHP_BRIDGE_URL, data=payload_options)
        response_options.raise_for_status()

        options_data = response_options.json().get("data", [])

        print("\n" + "=" * 80)
        print(f"QUESTION ID: {question['questionId']}")
        print("=" * 80)
        print(f"Question: {question.get('question', '')}")
        print("\nOptions:")
        for i, opt in enumerate(options_data, 1):
            correct_marker = " ✓ CORRECT" if opt.get("isCorrectAnswer") in [1, "1"] else ""
            print(f"  {i}. {opt.get('questionImageText', '')}{correct_marker}")

        has_explanation = question.get('description') and question.get('description').strip()
        print(f"\nHas Explanation: {'Yes' if has_explanation else 'No'}")
        if has_explanation:
            print(f"Explanation: {question['description'][:200]}...")

        print("=" * 80)

    except Exception as e:
        print(f"Error fetching question details: {str(e)}")


if __name__ == "__main__":
    # Fetch sample question IDs
    first_question_id = fetch_question_ids(10)

    # If we got a question ID, fetch its full details
    if first_question_id:
        fetch_question_with_options(first_question_id)
        print(f"\n\nYou can use Question ID: {first_question_id} to generate explanation")
