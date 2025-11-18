from flask import Flask, render_template, request, jsonify, redirect, url_for
from config import Config
from modules import database, tasks
import os
import uuid

app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload folder exists
os.makedirs(app.config.get('UPLOAD_FOLDER', 'uploads'), exist_ok=True)

# --- Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/questions')
def questions():
    return render_template('questions.html')

@app.route('/mcq-generation')
def mcq_generation():
    return render_template('mcq_generation.html')


@app.route('/health', methods=['GET'])
def health():
    """
    Health check endpoint - tests database connectivity via PHP bridge or direct connection.
    """
    health_info = {
        "status": "checking",
        "connection_method": "PHP Bridge" if Config.USE_PHP_BRIDGE else "Direct MySQL",
        "php_bridge_url": Config.PHP_BRIDGE_URL if Config.USE_PHP_BRIDGE else None
    }

    # --- Check Database Connection ---
    try:
        test_query = "SELECT 1 as test"
        result = database.execute_query(test_query)

        if result.get("error"):
            health_info["status"] = "unhealthy"
            health_info["database"] = "error"
            health_info["error"] = result.get("error")
        elif result.get("data") and len(result["data"]) > 0 and result["data"][0].get("test") == 1:
            health_info["status"] = "healthy"
            health_info["database"] = "connected"
            if not Config.USE_PHP_BRIDGE:
                health_info["host"] = Config.MYSQL_HOST
                health_info["port"] = Config.MYSQL_PORT
                health_info["database_name"] = Config.MYSQL_DATABASE
        else:
            health_info["status"] = "unhealthy"
            health_info["database"] = "disconnected"
            health_info["error"] = "Test query returned unexpected result"
            health_info["result"] = result
    except Exception as e:
        health_info["status"] = "unhealthy"
        health_info["database"] = "error"
        health_info["error"] = str(e)
        health_info["error_type"] = type(e).__name__

    status_code = 200 if health_info.get("status") == "healthy" else 500
    return jsonify(health_info), status_code


@app.route('/fetch-categories', methods=['GET'])
def fetch_categories():
    """
    Returns the hardcoded list of categories.
    """
    try:
        return jsonify({"data": Config.CATEGORIES})
    except Exception as e:
        return jsonify({"error": f"Error retrieving categories: {str(e)}"}), 500


# Fetch Subjects
@app.route('/fetch-subjects', methods=['POST'])
def fetch_subjects():
    try:
        data = request.get_json()
        category_id = data.get("categoryId")
        if not category_id:
            return jsonify({"error": "Missing categoryId"}), 400
        sql_query = "SELECT * FROM subject WHERE categoryId = %s"
        response = database.execute_query(sql_query, (category_id,))
        if response.get("error"):
            return jsonify({"error": "Failed to query subjects"}), 500
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Fetch Topics
@app.route('/fetch-topics', methods=['POST'])
def fetch_topics():
    try:
        data = request.get_json()
        subject_id = data.get("subjectId")
        if not subject_id:
            return jsonify({"error": "Missing subjectId"}), 400
        sql_query = "SELECT * FROM topics WHERE subjectId = %s"
        response = database.execute_query(sql_query, (subject_id,))
        if response.get("error"):
            return jsonify({"error": "Failed to query topics"}), 500
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Fetch Questions by Topic
@app.route('/fetch-questions-by-topic', methods=['POST'])
def fetch_questions_by_topic():
    try:
        data = request.get_json()
        topic_id = data.get("topicId")
        if not topic_id:
            return jsonify({"error": "Missing topicId"}), 400

        query_ids = "SELECT questionId FROM topicQueRel WHERE topicId = %s"
        response_ids = database.execute_query(query_ids, (topic_id,))
        if response_ids.get("error"):
            return jsonify({"error": "Failed to fetch question IDs"}), 500

        id_data = response_ids
        rows = id_data.get("data", [])
        question_ids = [row["questionId"] for row in rows if row.get("questionId")]
        if not question_ids:
            return jsonify({"data": []})

        ids_placeholders = ",".join(["%s"] * len(question_ids))
        query_questions = f"SELECT * FROM tblquestion WHERE questionId IN ({ids_placeholders})"
        response_questions = database.execute_query(query_questions, question_ids)
        if response_questions.get("error"):
            return jsonify({"error": "Failed to fetch questions"}), 500

        return jsonify(response_questions)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# NEW: Fetch Single Question Explanation
@app.route('/fetch-question-explanation', methods=['POST'])
def fetch_question_explanation():
    try:
        data = request.get_json()
        question_id = data.get("questionId")
        if not question_id:
            return jsonify({"error": "Missing questionId"}), 400

        query_question = "SELECT questionId, question, description FROM tblquestion WHERE questionId = %s"
        response_question = database.execute_query(query_question, (question_id,))
        if response_question.get("error"):
            return jsonify({"error": "Failed to fetch question"}), 500
        
        question_data = response_question.get("data", [])
        if not question_data:
            return jsonify({"error": "Question not found"}), 404

        question = question_data[0]
        query_options = "SELECT questionImageText, isCorrectAnswer FROM tblquestionoption WHERE questionId = %s"
        response_options = database.execute_query(query_options, (question_id,))
        options_data = response_options.get("data", [])
        
        options = [opt["questionImageText"] for opt in options_data]
        correct_option = next((opt["questionImageText"] for opt in options_data 
                              if opt["isCorrectAnswer"] == 1 or opt["isCorrectAnswer"] == "1"), None)

        result = {
            "questionId": question["questionId"],
            "question": question["question"],
            "options": options,
            "correctAnswer": correct_option,
            "explanation": question["description"]
        }

        return jsonify({"data": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# NEW: Fetch Explanations by Topic
@app.route('/fetch-explanations-by-topic', methods=['POST'])
def fetch_explanations_by_topic():
    try:
        data = request.get_json()
        category_id = int(data.get("categoryId"))
        subject_name = data.get("subjectName")
        topic_name = data.get("topicName")
        query_subject = "SELECT id FROM subject WHERE categoryId = %s AND subjectName = %s"
        res_sub = database.execute_query(query_subject, (category_id, subject_name))
        subject_data = res_sub.get("data", [])
        if not subject_data:
            return jsonify({"error": "Subject not found"}), 404
        subject_id = subject_data[0]["id"]


        query_topic = "SELECT id FROM topics WHERE subjectId = %s AND topicName = %s"
        res_topic = database.execute_query(query_topic, (subject_id, topic_name))
        topic_data = res_topic.get("data", [])
        if not topic_data:
            return jsonify({"error": "Topic not found"}), 404
        topic_id = topic_data[0]["id"]

        query_qids = "SELECT questionId FROM topicQueRel WHERE topicId = %s"
        res_qids = database.execute_query(query_qids, (topic_id,))
        qid_data = res_qids.get("data", [])
        if not qid_data:
            return jsonify({"data": []})
        
        question_ids = [row["questionId"] for row in qid_data]
        
        ids_placeholders = ",".join(["%s"] * len(question_ids))
        query_questions = f"""
            SELECT questionId, question, description 
            FROM tblquestion 
            WHERE questionId IN ({ids_placeholders}) 
            AND description IS NOT NULL AND TRIM(description) != ''
        """
        res_questions = database.execute_query(query_questions, question_ids)
        questions_data = res_questions.get("data", [])

        results = []
        for question in questions_data:
            query_options = "SELECT questionImageText, isCorrectAnswer FROM tblquestionoption WHERE questionId = %s"
            res_options = database.execute_query(query_options, (question["questionId"],))
            options_data = res_options.get("data", [])
            
            options = [opt["questionImageText"] for opt in options_data]
            correct_option = next((opt["questionImageText"] for opt in options_data 
                                  if opt["isCorrectAnswer"] == 1 or opt["isCorrectAnswer"] == "1"), None)

            results.append({
                "questionId": question["questionId"],
                "question": question["question"],
                "options": options,
                "correctAnswer": correct_option,
                "explanation": question["description"]
            })

        return jsonify({"data": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# NEW: Generate Single Question Description
@app.route('/generate-single-question-description', methods=['POST'])
def generate_single_question_description():
    try:
        data = request.get_json()
        question_id = int(data.get("questionId"))

        task_id = tasks.start_single_question_explanation_task(question_id)
        return jsonify({"status": "started", "taskId": task_id})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

# NEW: Cancel All Tasks
@app.route('/cancel-all-tasks', methods=['POST'])
def cancel_all_tasks():
    try:
        cancelled_count = tasks.cancel_all_tasks()
        return jsonify({
            "status": "success", 
            "message": f"Cancelled {cancelled_count} running tasks"
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

# Generate Explanations (By Topic)
@app.route('/generate-category-questions', methods=['POST'])
def generate_category_questions():
    try:
        data = request.get_json()
        category_id = int(data.get("categoryId"))
        subject_name = data.get("subjectName")
        topic_name = data.get("topicName")

        task_id = tasks.start_explanation_task(category_id, subject_name, topic_name, generate_all=False)
        return jsonify({"status": "started", "taskId": task_id})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

# Generate Explanations (All Topics in Subject)
@app.route('/generate-all-topic-descriptions', methods=['POST'])
def generate_all_topic_descriptions():
    try:
        data = request.get_json()
        category_id = int(data.get("categoryId"))
        subject_name = data.get("subjectName")

        task_id = tasks.start_explanation_task(category_id, subject_name, "", generate_all=True)
        return jsonify({"status": "started", "taskId": task_id})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

# Generate Explanations (Global) Unfinished
@app.route('/generate-missing-descriptions', methods=['POST'])
def generate_missing_descriptions():
    try:
        task_id = str(uuid.uuid4())
        tasks.task_status[task_id] = {"status": "queued", "progress": 0, "results": [], "error": None}
        
        import threading
        thread = threading.Thread(target=process_global_explanations, args=(task_id,))
        tasks.running_tasks[task_id] = {'thread': thread, 'cancelled': False}
        thread.start()
        
        return jsonify({"status": "started", "taskId": task_id})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# Delete Explanation by ID
@app.route('/delete-description', methods=['POST'])
def delete_question_description():
    try:
        data = request.get_json()
        question_id = int(data.get("questionId"))
        if not question_id:
            return jsonify({"status": "error", "message": "Missing questionId"}), 400

        check_query = "SELECT description FROM tblquestion WHERE questionId = %s"
        check_response = database.execute_query(check_query, (question_id,))
        check_data = check_response.get("data", [])

        if not check_data or not check_data[0].get("description"):
            return jsonify({"status": "no", "message": "No description to remove."})

        nullify_query = "UPDATE tblquestion SET description = NULL WHERE questionId = %s"
        update_response = database.execute_query(nullify_query, (question_id,))

        if not update_response.get("error"):
            return jsonify({"status": "success", "message": f"Description removed for questionId={question_id}"})
        else:
            return jsonify({"status": "error", "message": "DB update failed"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Delete Explanations by Topic
@app.route('/delete-question-descriptions-by-topic', methods=['POST'])
def delete_question_descriptions_by_topic():
    try:
        data = request.get_json()
        category_id = int(data.get("categoryId"))
        subject_name = data.get("subjectName")
        topic_name = data.get("topicName")

        query_subject = "SELECT id FROM subject WHERE categoryId = %s AND subjectName = %s"
        res_sub = database.execute_query(query_subject, (category_id, subject_name))
        subject_data = res_sub.get("data", [])
        if not subject_data:
            return jsonify({"status": "error", "message": "Subject not found"}), 404
        subject_id = subject_data[0]["id"]

        query_topic = "SELECT id FROM topics WHERE subjectId = %s AND topicName = %s"
        res_topic = database.execute_query(query_topic, (subject_id, topic_name))
        topic_data = res_topic.get("data", [])
        if not topic_data:
            return jsonify({"status": "error", "message": "Topic not found"}), 404
        topic_id = topic_data[0]["id"]

        query_qids = "SELECT questionId FROM topicQueRel WHERE topicId = %s"
        res_qids = database.execute_query(query_qids, (topic_id,))
        qid_data = res_qids.get("data", [])
        if not qid_data:
            return jsonify({"status": "error", "message": "No questions linked to this topic"}), 404
        question_ids = [str(row["questionId"]) for row in qid_data]

        ids_placeholders = ",".join(["%s"] * len(question_ids))
        update_query = f"UPDATE tblquestion SET description = NULL WHERE questionId IN ({ids_placeholders})"
        res_update = database.execute_query(update_query, question_ids)

        if not res_update.get("error"):
            return jsonify({"status": "success", "message": f"Descriptions removed from {len(question_ids)} questions."})
        else:
            return jsonify({"status": "error", "message": "Failed to update descriptions"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Task Status
@app.route('/task-status/<task_id>', methods=['GET'])
def task_status_check(task_id):
    task = tasks.get_task_status(task_id)
    if not task or task.get("status") == "not_found":
        return jsonify({"status": "not_found"}), 404
    return jsonify(task)


# Cancel Task
@app.route('/cancel-task/<task_id>', methods=['POST'])
def cancel_task(task_id):
    success = tasks.cancel_task(task_id)
    if success:
        return jsonify({"status": "success", "message": "Task cancelled"}), 200
    else:
        return jsonify({"status": "error", "error": "Task not found or could not be cancelled"}), 404

# --- MCQ Generation Endpoints ---

# Start MCQ Generation
@app.route('/start-generate-mcqs', methods=['POST'])
def start_generate_mcqs():
    try:
        if 'pdf' not in request.files:
            return jsonify({'error': 'No PDF uploaded'}), 400
        
        pdf_file = request.files['pdf']
        if pdf_file.filename == '':
            return jsonify({'error': 'No PDF selected'}), 400
            
        filename = pdf_file.filename
        task_id = tasks.start_mcq_generation_task(pdf_file, filename)
        return jsonify({'task_id': task_id}), 202
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# MCQ Task Status
@app.route('/mcq-status/<task_id>', methods=['GET'])
def get_mcq_status(task_id):
    task_info = tasks.get_task_status(task_id)
    if not task_info or task_info.get("status") == "not_found":
        return jsonify({'error': 'Invalid task ID'}), 404
    return jsonify(task_info)
    
    
#New routes for persistency
@app.route('/all-tasks', methods=['GET'])
def get_all_tasks():
    """Get all tasks with their status"""
    try:
        all_tasks = tasks.get_all_tasks()
        return jsonify({
            "status": "success",
            "tasks": all_tasks,
            "count": len(all_tasks)
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/running-tasks', methods=['GET'])
def get_running_tasks():
    """Get only running tasks"""
    try:
        running_info = tasks.get_running_tasks_info()
        return jsonify({
            "status": "success",
            "tasks": running_info,
            "count": len(running_info)
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/task-details/<task_id>', methods=['GET'])
def get_task_details(task_id):
    """Get detailed information about a specific task including recent results"""
    try:
        status = tasks.get_task_status(task_id)
        if status.get("status") == "not_found":
            return jsonify({
                "status": "error",
                "error": "Task not found"
            }), 404
        
        # Get the last 5 results if available
        recent_results = status.get("results", [])[-5:] if status.get("results") else []
        
        return jsonify({
            "status": "success",
            "task": {
                **status,
                "recent_results": recent_results,
                "total_results": len(status.get("results", []))
            }
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/clear-completed-tasks', methods=['POST'])
def clear_completed_tasks():
    """Clear all completed/failed/cancelled tasks from memory"""
    try:
        cleared_count = 0
        task_ids_to_remove = []
        
        for task_id, status in tasks.task_status.items():
            if status.get("status") in ["completed", "failed", "cancelled"]:
                task_ids_to_remove.append(task_id)
        
        for task_id in task_ids_to_remove:
            tasks.task_status.pop(task_id, None)
            cleared_count += 1
        
        tasks.save_task_status()
        
        return jsonify({
            "status": "success",
            "message": f"Cleared {cleared_count} completed tasks",
            "cleared_count": cleared_count
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
