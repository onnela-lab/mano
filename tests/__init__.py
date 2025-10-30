import os
import sys

# inserts the root of the repo folder into the python path so we can just import the codebase
# without relative import issues or needing to install the package.
repo_root = os.path.abspath(__file__).rsplit('/', 2)[0]
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
