import sys
import os
import time
import json

# Add parent dir to path to import runner_interface
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from runner_interface import SmartVastStatus

def test_smart_status():
    print("Testing SmartVastStatus Logic...")
    status = SmartVastStatus()
    
    # Test 1: Loading Phase (Heuristic Curve)
    print("\n[Test 1] Loading Phase (Docker Pull)")
    status.update({"actual_status": "loading"}, 0)
    print(f"T=0s: {status.progress:.1f}% (Expected ~0%)")
    
    # Simulate time passing
    status.step_start_time -= 30 
    status.update({"actual_status": "loading"}, 30)
    print(f"T=30s: {status.progress:.1f}% (Expected ~50%)")
    
    status.step_start_time -= 30 # total 60s
    status.update({"actual_status": "loading"}, 60)
    print(f"T=60s: {status.progress:.1f}% (Expected ~65%)")
    
    # Test 2: Stuck Detection
    print("\n[Test 2] Stuck Detection")
    status.step_start_time -= 600 # total 660s > 10 mins
    status.update({"actual_status": "loading"}, 660)
    print(f"T=660s: Stuck? {status.is_stuck} (Expected: True)")
    
    # Test 3: Connecting Phase
    print("\n[Test 3] Connecting Phase")
    status.update({"actual_status": "connecting"}, 700) # Status change resets timer
    print(f"T=0s (Connecting): {status.progress:.1f}% (Expected 0-10%)")
    
    status.step_start_time -= 10
    status.update({"actual_status": "connecting"}, 710)
    print(f"T=10s (Connecting): {status.progress:.1f}% (Expected ~50%)")

    print("\nVerification Complete.")

if __name__ == "__main__":
    test_smart_status()
