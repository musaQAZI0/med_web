import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import uuid
import os
from . import q_generation_func
from . import func_gpt5 as board_explainer
from .database import execute_query
import cloudinary
import cloudinary.uploader
from config import Config

# Initialize Cloudinary
cloudinary.config(
    cloud_name=Config.CLOUDINARY_CLOUD_NAME,
    api_key=Config.CLOUDINARY_API_KEY,
    api_secret=Config.CLOUDINARY_API_SECRET,
    secure=True
)

task_status = {}
running_tasks = {}

def get_task_status(task_id):
    return task_status.get(task_id, {"status": "not_found"})

def cancel_task(task_id):
    if task_id in running_tasks:
        # Set cancellation flag - the task will check this periodically
        running_tasks[task_id]['cancelled'] = True
        task_status[task_id]["status"] = "cancelling"
        task_status[task_id]["error"] = "Cancellation requested by user."
        return True
    return False

def cancel_all_tasks():
    """Cancel all currently running tasks"""
    cancelled_count = 0
    for task_id in list(running_tasks.keys()):
        if cancel_task(task_id):
            cancelled_count += 1
    return cancelled_count

def get_running_tasks_info():
    """Get information about all running tasks"""
    info = []
    for task_id, task_info in running_tasks.items():
        status = task_status.get(task_id, {})
        info.append({
            "task_id": task_id,
            "status": status.get("status", "unknown"),
            "progress": status.get("progress", 0),
            "total": status.get("total", 0),
            "thread_alive": task_info["thread"].is_alive() if "thread" in task_info else False,
            "latest_result": status.get("latest_result", None)
        })
    return info


def get_all_tasks_info(status_filter=None):
    """
    Get information about all tasks (running, completed, failed).
    Optionally filter by status.
    """
    info = []
    for task_id, status in task_status.items():
        # Apply status filter if provided
        if status_filter and status.get("status") != status_filter:
            continue

        # Check if task is still running
        is_running = task_id in running_tasks
        thread_alive = False
        if is_running and "thread" in running_tasks[task_id]:
            thread_alive = running_tasks[task_id]["thread"].is_alive()

        info.append({
            "task_id": task_id,
            "status": status.get("status", "unknown"),
            "progress": status.get("progress", 0),
            "total": status.get("total", 0),
            "is_running": is_running,
            "thread_alive": thread_alive,
            "error": status.get("error", None),
            "latest_result": status.get("latest_result", None),
            "results_count": len(status.get("results", []))
        })

    # Sort by status: processing first, then queued, then completed, then failed
    status_priority = {"processing": 1, "queued": 2, "completed": 3, "failed": 4, "cancelled": 5}
    info.sort(key=lambda x: status_priority.get(x["status"], 999))

    return info

# --- Single Question Explanation Task ---
def start_single_question_explanation_task(question_id):
    task_id = str(uuid.uuid4())
    task_status[task_id] = {"status": "queued", "progress": 0, "results": [], "error": None}

    thread = threading.Thread(
        target=process_single_question_explanation,
        args=(task_id, question_id),
        daemon=False  # IMPORTANT: Non-daemon thread keeps running after browser close
    )
    running_tasks[task_id] = {'thread': thread, 'cancelled': False}
    thread.start()

    return task_id

def process_single_question_explanation(task_id, question_id):
    try:
        task_status[task_id]["status"] = "processing"
        
        # Get the question
        query_question = "SELECT questionId, question FROM tblquestion WHERE questionId = %s"
        question_resp = execute_query(query_question, (question_id,))
        question_data = question_resp.get("data", [])
        
        if not question_data:
            raise Exception(f"Question with ID {question_id} not found")
        
        question = question_data[0]
        
        # Get options for this question
        query_options = "SELECT questionId, questionImageText, isCorrectAnswer FROM tblquestionoption WHERE questionId = %s"
        options_resp = execute_query(query_options, (question_id,))
        options = options_resp.get("data", [])
        
        if not options:
            raise Exception("No options found for this question")
        
        # Find correct option
        correct = next((opt for opt in options if opt["isCorrectAnswer"] == 1 or opt["isCorrectAnswer"] == "1"), None)
        
        if not correct:
            raise Exception("No correct answer found for this question")
        
        # Check for cancellation before expensive AI operation
        if running_tasks.get(task_id, {}).get('cancelled', False):
            task_status[task_id]["status"] = "cancelled"
            task_status[task_id]["error"] = "Task was cancelled."
            running_tasks.pop(task_id, None)
            return
        
        # Generate explanation
        explainer = board_explainer.GenericBoardStyleMedicalExplainer()
        label_map = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        
        def check_cancellation():
            return running_tasks.get(task_id, {}).get('cancelled', False)
        
        formatted_question = format_complete_question(question, options, correct, label_map)
        explanation = explainer.generate_board_explanation(formatted_question, check_cancellation)
        
        # Check for cancellation after AI operation
        if running_tasks.get(task_id, {}).get('cancelled', False):
            task_status[task_id]["status"] = "cancelled"
            task_status[task_id]["error"] = "Task was cancelled after explanation generation."
            running_tasks.pop(task_id, None)
            return
        
        # Update database
        update_query = "UPDATE tblquestion SET description = %s WHERE questionId = %s"
        response = execute_query(update_query, (explanation, question_id))
        
        if response.get("error"):
            raise Exception("Database update failed")
        
        # Prepare result
        labeled_opts = [opt['questionImageText'] for opt in options]
        correct_text = correct["questionImageText"] if correct else ""
        
        result = {
            "index": 1,
            "questionId": question["questionId"],
            "question": question.get("question", ""),
            "options": labeled_opts,
            "correctAnswer": correct_text,
            "explanation": explanation,
            "completed_at": time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        task_status[task_id]["results"].append(result)
        task_status[task_id]["progress"] = 1
        task_status[task_id]["status"] = "completed"
        task_status[task_id]["latest_result"] = result
        
        running_tasks.pop(task_id, None)
        
    except Exception as e:
        if "cancelled" in str(e).lower():
            task_status[task_id] = {
                "status": "cancelled",
                "error": str(e)
            }
        else:
            task_status[task_id] = {
                "status": "failed",
                "error": str(e)
            }
        running_tasks.pop(task_id, None)

# --- Question Explanation Task ---
status_lock = threading.Lock()
RATE_LIMIT_DELAY = 2.5  # Seconds between API calls (adjust based on your rate limits)
rate_limit_lock = threading.Lock()
last_api_call_time = 0

def rate_limited_delay():
    """Implement rate limiting between API calls."""
    global last_api_call_time
    with rate_limit_lock:
        current_time = time.time()
        time_since_last_call = current_time - last_api_call_time
        if time_since_last_call < RATE_LIMIT_DELAY:
            sleep_time = RATE_LIMIT_DELAY - time_since_last_call
            time.sleep(sleep_time)
        last_api_call_time = time.time()
        
def start_explanation_task(category_id, subject_name, topic_name, generate_all=False, max_workers=3):
    task_id = str(uuid.uuid4())
    task_status[task_id] = {
        "status": "queued", 
        "progress": 0, 
        "total": 0,
        "results": [], 
        "error": None
    }
    
    thread = threading.Thread(
        target=process_question_explanation,
        args=(task_id, category_id, subject_name, topic_name, generate_all, max_workers),
        daemon=False  # IMPORTANT: Non-daemon thread keeps running after browser close
    )
    running_tasks[task_id] = {'thread': thread, 'cancelled': False}
    thread.start()

    return task_id


def process_question_explanation(task_id, category_id, subject_name, topic_name, generate_all, max_workers=3):
    try:
        with status_lock:
            task_status[task_id]["status"] = "processing"
        
        # Get subject ID
        query_subject = "SELECT id FROM subject WHERE categoryId = %s AND subjectName = %s"
        subject = execute_query(query_subject, (category_id, subject_name))
        if not subject.get("data"):
            raise Exception("Subject not found")
        subject_id = subject.get("data")[0]["id"]

        # Get topic ID (if not generating for all topics)
        topic_id = None
        if not generate_all:
            query_topic = "SELECT id FROM topics WHERE subjectId = %s AND topicName = %s"
            topic = execute_query(query_topic, (subject_id, topic_name))
            if not topic.get("data"):
                raise Exception("Topic not found")
            topic_id = topic.get("data")[0]["id"]

        # Get question IDs
        if generate_all:
            query_ids = """
                SELECT DISTINCT q.questionId 
                FROM tblquestion q
                JOIN topicQueRel rel ON rel.questionId = q.questionId
                JOIN topics t ON t.id = rel.topicId
                WHERE t.subjectId = %s AND (q.description IS NULL OR TRIM(q.description) = '')
            """
            ids_resp = execute_query(query_ids, (subject_id,))
        else:
            query_ids = "SELECT questionId FROM topicQueRel WHERE topicId = %s"
            ids_resp = execute_query(query_ids, (topic_id,))
            
        question_data = ids_resp.get("data", [])
        if not isinstance(question_data, list) or not question_data:
            raise Exception("No questions found")
        question_ids = [str(row["questionId"]) for row in question_data]

        # Get questions needing explanations
        if question_ids:
            ids_placeholders = ",".join(["%s"] * len(question_ids))
            query_questions = f"SELECT questionId, question FROM tblquestion WHERE questionId IN ({ids_placeholders})"
            questions_resp = execute_query(query_questions, question_ids)
            questions = questions_resp.get("data", [])
        else:
            questions = []

        if not questions:
            with status_lock:
                task_status[task_id] = {
                    "status": "completed",
                    "progress": 0,
                    "total": 0,
                    "results": [],
                    "error": "All questions already explained."
                }
            return

        # Get options
        ids_placeholders = ",".join(["%s"] * len(question_ids))
        query_options = f"SELECT questionId, questionImageText, isCorrectAnswer FROM tblquestionoption WHERE questionId IN ({ids_placeholders})"
        options_resp = execute_query(query_options, question_ids)
        options = options_resp.get("data", [])

        # Update total count
        with status_lock:
            task_status[task_id]["total"] = len(questions)

        # Process questions in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all questions to the thread pool
            future_to_question = {
                executor.submit(
                    process_single_question, 
                    task_id, 
                    idx, 
                    q, 
                    options
                ): (idx, q) for idx, q in enumerate(questions, start=1)
            }
            
            # Process completed tasks as they finish
            for future in as_completed(future_to_question):
                idx, q = future_to_question[future]
                
                # Check for cancellation
                if running_tasks.get(task_id, {}).get('cancelled', False):
                    # Cancel all pending futures
                    for f in future_to_question:
                        f.cancel()
                    
                    with status_lock:
                        task_status[task_id]["status"] = "cancelled"
                        task_status[task_id]["error"] = "Task was cancelled."
                    running_tasks.pop(task_id, None)
                    return
                
                try:
                    result = future.result()
                    
                    # Update progress and results thread-safely
                    with status_lock:
                        task_status[task_id]["results"].append(result)
                        task_status[task_id]["progress"] = len(task_status[task_id]["results"])
                        task_status[task_id]["status"] = "processing"
                        task_status[task_id]["latest_result"] = result
                    
                    print(f"Completed question {result['questionId']} ({task_status[task_id]['progress']}/{task_status[task_id]['total']})")
                    
                except Exception as e:
                    error_result = {
                        "index": idx,
                        "questionId": q["questionId"],
                        "error": str(e)
                    }
                    with status_lock:
                        task_status[task_id]["results"].append(error_result)
                        task_status[task_id]["progress"] = len(task_status[task_id]["results"])
                    print(f"Error processing question {q.get('questionId', 'unknown')}: {str(e)}")
        
        # Mark as completed
        with status_lock:
            task_status[task_id]["status"] = "completed"
        running_tasks.pop(task_id, None)

    except Exception as outer_e:
        # Check if it was a cancellation
        with status_lock:
            if "cancelled" in str(outer_e).lower():
                task_status[task_id] = {
                    "status": "cancelled",
                    "error": str(outer_e)
                }
            else:
                task_status[task_id] = {
                    "status": "failed",
                    "error": str(outer_e)
                }
        running_tasks.pop(task_id, None)


def process_single_question(task_id, idx, q, options):
    """
    Process a single question - this runs in a worker thread, attached with numerous generation
    """
    # Check for cancellation
    if running_tasks.get(task_id, {}).get('cancelled', False):
        raise Exception("Task cancelled")
    
    try:
        q_opts = [opt for opt in options if opt["questionId"] == q["questionId"]]
        
        # Handle both integer and string values for isCorrectAnswer
        correct = next((opt for opt in q_opts if opt["isCorrectAnswer"] == 1 or opt["isCorrectAnswer"] == "1"), None)

        if not q_opts:
            raise Exception("No options found.")

        labeled_opts = [opt['questionImageText'] for opt in q_opts]
        correct_text = correct["questionImageText"] if correct else ""

        # Debug: Print what we found
        print(f"\nDEBUG - Processing question {q['questionId']} (Thread: {threading.current_thread().name})")
        print(f"Found {len(q_opts)} options")
        print(f"Correct option found: {'Yes' if correct else 'No'}")
        if correct:
            print(f"Correct answer text: {correct['questionImageText'][:50]}...")

        # Check for cancellation before expensive AI operation
        if running_tasks.get(task_id, {}).get('cancelled', False):
            raise Exception("Task cancelled before explanation generation")
        
        rate_limited_delay()
        
        # Generate explanation with cancellation support
        def check_cancellation():
            return running_tasks.get(task_id, {}).get('cancelled', False)
        
        label_map = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        formatted_question = format_complete_question(q, q_opts, correct, label_map)
        print(f"Formatted question length: {len(formatted_question)}")
        
        # Create explainer instance (thread-safe)
        explainer = board_explainer.GenericBoardStyleMedicalExplainer()
        explanation = explainer.generate_board_explanation(formatted_question, check_cancellation)

        # Check for cancellation after expensive AI operation
        if running_tasks.get(task_id, {}).get('cancelled', False):
            raise Exception("Task cancelled after explanation generation")

        # Update database
        update_query = "UPDATE tblquestion SET description = %s WHERE questionId = %s"
        response = execute_query(update_query, (explanation, int(q['questionId'])))

        if response.get("error"):
            raise Exception("DB update failed")

        result = {
            "index": idx,
            "questionId": q["questionId"],
            "question": q.get("question", ""),
            "options": labeled_opts,
            "correctAnswer": correct_text,
            "explanation": explanation,
            "completed_at": time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        print(f"Result correct answer: {result['correctAnswer']}")
        
        # Sleep to avoid overwhelming the AI service (optional - adjust as needed)
        time.sleep(1)
        
        return result

    except Exception as e:
        print(f"Error in worker thread processing question {q.get('questionId', 'unknown')}: {str(e)}")
        raise
        
def format_complete_question(question_data, options, correct_option, label_map):
    """
    Format the complete question with options and correct answer
    for the board explainer to process properly
    """
    formatted_question = question_data['question'].strip()
    
    if not formatted_question.endswith(':'):
        formatted_question += ':'
    
    # Add numbered options (if they exist)
    if options:
        formatted_question += "\n\n"
        for i, option in enumerate(options, 1):
            formatted_question += f"{i}) {option['questionImageText']};\n"
    
    # Add answer choices and find correct answer
    if len(options) > 1:
        formatted_question += f"\nPrawidłowa odpowiedź to: "
        
        # Find the correct answer index by checking isCorrectAnswer field directly
        # Don't rely on the correct_option parameter since it might be None
        correct_index = None
        for i, opt in enumerate(options):
            # Check for both string and integer values for isCorrectAnswer
            if opt['isCorrectAnswer'] == 1 or opt['isCorrectAnswer'] == "1":
                correct_index = i
                break
        
        # Create answer choice letters based on number of options
        choices = []
        for i in range(min(5, len(options))):  # Limit to 5 choices max
            choices.append(f"{label_map[i]}. {i+1}")
        
        formatted_question += " ".join(choices) + "."
        
        # Add the correct answer if available
        if correct_index is not None:
            correct_letter = label_map[correct_index]
            formatted_question += f" (Correct: {correct_letter})"
    
    return formatted_question

# --- MCQ Generation Task ---
def start_mcq_generation_task(pdf_file, filename):
    task_id = str(uuid.uuid4())
    task_status[task_id] = {
        'status': 'queued',
        'progress': 'Queued',
        'download_url': None,
        'error': None
    }
    
    # Save PDF temporarily
    pdf_path = os.path.join('uploads', f"{task_id}_{filename}")
    os.makedirs('uploads', exist_ok=True)
    pdf_file.save(pdf_path)

    thread = threading.Thread(
        target=process_mcqs_task,
        args=(task_id, pdf_path, filename),
        daemon=False  # IMPORTANT: Non-daemon thread keeps running after browser close
    )
    running_tasks[task_id] = {'thread': thread, 'cancelled': False}
    thread.start()

    return task_id

def process_mcqs_task(task_id, pdf_path, filename):
    try:
        import openai
        client = openai.OpenAI(api_key=Config.OPENAI_API_KEY)
        
        task_status[task_id]['status'] = 'processing'
        task_status[task_id]['progress'] = 'Extracting text...'
        time.sleep(0.1) # Simulate async yield

        full_text = q_generation_func.extract_pdf_text(pdf_path)
        time.sleep(0.1)

        chunks = q_generation_func.sliding_window_chunks(full_text, 1200, 600)
        time.sleep(0.1)

        is_relevant = q_generation_func.is_clinically_relevant(client, chunks[0])
        if not is_relevant:
            task_status[task_id]['status'] = 'error'
            task_status[task_id]['error'] = 'PDF is not clinically relevant'
            return

        all_mcqs = []
        for i, chunk in enumerate(chunks[:4]): # Limit chunks for demo
            if running_tasks.get(task_id, {}).get('cancelled', False):
                task_status[task_id]["status"] = "cancelled"
                task_status[task_id]["error"] = "Task was cancelled."
                running_tasks.pop(task_id, None)
                return
            
            task_status[task_id]['progress'] = f'Processing chunk {i + 1} of {len(chunks)}...'
            time.sleep(0.1)

            rate_limited_delay()

            # Generate MCQs (synchronous call)
            mcqs = q_generation_func.generate_mcqs_with_assistant(client, "dummy_assistant_id", task_id, {}, chunk) # Adapt function call
            all_mcqs.extend(mcqs)

        task_status[task_id]['progress'] = 'Exporting MCQs to Excel...'
        time.sleep(0.1)

        final_mcqs = q_generation_func.deduplicate_mcqs(all_mcqs)
        temp_excel_path = os.path.join("/tmp", filename.replace('.pdf', '_mcqs.xlsx'))

        q_generation_func.mcqs_to_excel(final_mcqs, temp_excel_path)

        task_status[task_id]['progress'] = 'Uploading to Cloudinary...'
        time.sleep(0.1)

        upload_result = cloudinary.uploader.upload(
            temp_excel_path,
            resource_type="raw",
            folder="mcqs_outputs",
            public_id=filename.replace('.pdf', '_mcqs'),
            use_filename=True,
            unique_filename=False,
            overwrite=True
        )

        task_status[task_id]['status'] = 'completed'
        task_status[task_id]['progress'] = 'Generation complete.'
        task_status[task_id]['download_url'] = upload_result.get('secure_url')
        
        # Cleanup
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        if os.path.exists(temp_excel_path):
            os.remove(temp_excel_path)
            
        running_tasks.pop(task_id, None)

    except Exception as outer_e:
        # Check if it was a cancellation
        if "cancelled" in str(outer_e).lower():
            task_status[task_id] = {
                "status": "cancelled",
                "error": str(outer_e)
            }
        else:
            task_status[task_id] = {
                "status": "failed",
                "error": str(outer_e)
            }
        running_tasks.pop(task_id, None)
