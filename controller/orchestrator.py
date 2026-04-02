import uuid
from datetime import datetime

class TaskModel:
    def __init__(self, task_id=None, status="PENDING", iteration_count=0):
        self.task_id = task_id if task_id else str(uuid.uuid4())
        self.status = status
        self.iteration_count = iteration_count

class ResultClassifier:
    def classify_result(self, result):
        if "error" in result.lower():
            return "RED"
        elif "warning" in result.lower() or "timeout" in result.lower():
            return "YELLOW"
        else:
            return "GREEN"

def evaluate_task(task_id, result):
    classifier = ResultClassifier()
    classification = classifier.classify_result(result)
    
    if classification == "GREEN":
        print(f"Task {task_id} completed successfully.")
        return True
    elif classification == "YELLOW":
        print(f"Task {task_id} has a warning or timeout. Replanning...")
        return False
    else:
        print(f"Task {task_id} failed. Stopping...")
        return False

def run_task(task):
    task_id = task.task_id
    iteration_count = task.iteration_count + 1
    
    # Simulate running the task and getting a result
    result = f"Task {task_id} executed at {datetime.now()}. Status: Success"
    
    if evaluate_task(task_id, result):
        return TaskModel(task_id=task_id, status="COMPLETED", iteration_count=iteration_count)
    else:
        return TaskModel(task_id=task_id, status="PENDING", iteration_count=iteration_count)

def main():
    task = TaskModel()
    while True:
        updated_task = run_task(task)
        if updated_task.status == "COMPLETED":
            break
        elif updated_task.status == "PENDING":
            # Simulate a delay before retrying
            import time
            time.sleep(5)
        task = updated_task

if __name__ == "__main__":
    main()
