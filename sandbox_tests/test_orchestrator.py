import sys
import os

project_root = "/Users/philip/WintripAI"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sandbox_tests.orchestrator_test_versie import TaskModel, ResultClassifier
from controller.reflector import Reflector

class MockKB:
    def ingest_reflection(self, text, reflection_type, tags, interaction_id):
        return True

def test_task_model_initialization():
    task = TaskModel("Test Task", max_iterations=3)
    assert task.status == "PENDING"
    assert task.iteration_count == 0

def test_task_model_green_path():
    task = TaskModel("Green Task")
    task.record_iteration("GREEN", "Works perfectly")
    assert task.status == "COMPLETED"
    assert task.iteration_count == 1

def test_task_model_red_retry_logic():
    task = TaskModel("Red Task", max_iterations=2)
    task.record_iteration("RED", "First failure")
    assert task.status == "RETRYING"
    assert task.iteration_count == 1
    
    task.record_iteration("RED", "Second failure")
    assert task.status == "FAILED"
    assert task.iteration_count == 2

def test_task_model_yellow_logic():
    task = TaskModel("Yellow Task")
    task.record_iteration("YELLOW", "Needs manual check")
    assert task.status == "INVESTIGATING"

def test_result_classifier_green():
    mock_kb = MockKB()
    reflector = Reflector(kb=mock_kb)
    classifier = ResultClassifier(reflector=reflector)
    
    color, insight = classifier.classify_result("Test task", "The process finished with success.")
    assert color == "GREEN", "Expected GREEN"

def test_result_classifier_red():
    mock_kb = MockKB()
    reflector = Reflector(kb=mock_kb)
    classifier = ResultClassifier(reflector=reflector)
    
    color, insight = classifier.classify_result("Test err task", "Fout in error trace")
    assert color == "RED", "Expected RED"

def test_result_classifier_yellow():
    mock_kb = MockKB()
    reflector = Reflector(kb=mock_kb)
    classifier = ResultClassifier(reflector=reflector)
    
    color, insight = classifier.classify_result("Test neutral task", "Observation action voltooid.")
    assert color == "YELLOW", "Expected YELLOW"

if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    success = True
    for test_func in tests:
        try:
            test_func()
            print(f"PASSED {test_func.__name__}")
        except Exception as e:
            print(f"FAILED {test_func.__name__} - {e}")
            success = False
    
    if success:
        print("\nAll tests passed (100% green).")
        sys.exit(0)
    else:
        print("\nSome tests failed.")
        sys.exit(1)
