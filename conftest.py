"""
Root conftest.py — ensures that internal imports within biobot/ work.

The biobot modules use bare imports like 'from config import get_api_key'
because in Docker they run from /app/ where config.py is in the same directory.

For pytest, we need to add biobot/ to sys.path so these imports resolve.
"""
import sys
import os

# Add the biobot/ directory to sys.path so that 'from config import ...',
# 'from crypt import ...', 'from engine import ...' etc. all work.
biobot_dir = os.path.join(os.path.dirname(__file__), "biobot")
if biobot_dir not in sys.path:
    sys.path.insert(0, biobot_dir)