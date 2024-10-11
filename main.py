import os
import sys
os.environ["ALO_HOME"] = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.dirname(os.path.abspath(__file__)) + "/solution/src/"
if os.path.exists(src_path) and os.path.isdir(src_path):
    sys.path.append(src_path)
else:
    pass

from alo.alo import main


if __name__ == "__main__":
    main()
