import sys
import os

project_root = "/Users/philip/WintripAI"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from controller.reflector import Reflector

class TaskModel:
    def __init__(self, task_name, max_iterations=3):
        self.task_name = task_name
        self.status = "PENDING"
        self.iteration_count = 0
        self.max_iterations = max_iterations
        self.history = []

    def update_status(self, new_status):
        self.status = new_status

    def record_iteration(self, result_classification, insight):
        self.iteration_count += 1
        self.history.append({"iteration": self.iteration_count, "classification": result_classification, "insight": insight})
        if result_classification == "GREEN":
            self.status = "COMPLETED"
        elif result_classification == "RED":
            if self.iteration_count >= self.max_iterations:
                self.status = "FAILED"
            else:
                self.status = "RETRYING"
        elif result_classification == "YELLOW":
            self.status = "INVESTIGATING"

class ResultClassifier:
    def __init__(self, reflector=None):
        self.reflector = reflector or Reflector()

    def classify_result(self, task_name, raw_output):
        eval_result = self.reflector.evaluate_action(task_name, raw_output)
        ref_type = eval_result.get("type", "insight")
        
        if ref_type == "success":
            return "GREEN", eval_result.get("insight", "")
        elif ref_type == "failure":
            return "RED", eval_result.get("insight", "")
        else:
            return "YELLOW", eval_result.get("insight", "")
