"""Make the repository root importable for the test suite.

``component`` is an application package that is never installed. Under the bare
``pytest`` console script ``sys.path[0]`` is the test directory, so
``import component...`` would fail without this.
"""

import os
import sys

# Tests must never attempt a real SEPAL login even if the shell exported it.
os.environ["PYSEPAL_DEV_AUTH"] = "0"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
