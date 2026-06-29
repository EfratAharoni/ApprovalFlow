import sys
import os

# Allow "from app.xxx import yyy" from within the tests directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
