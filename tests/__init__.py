import sys
from os.path import abspath, dirname


# inserts the root of the repo folder into the python path so we can just import the codebase
# without relative import issues or needing to install the package.
repo_root = abspath(dirname(dirname(abspath(__file__))))

# repo_root = abspath(__file__).rsplit('/', 2)[0]
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
    print(f"\nAdding repo root to sys.path: {repo_root}\n")

# mano_folder_in_repo = path_join(repo_root, 'mano')
# if mano_folder_in_repo not in sys.path:
#     sys.path.insert(0, mano_folder_in_repo)
#     print(f"\nAdding mano folder in repo: {mano_folder_in_repo}\n")
