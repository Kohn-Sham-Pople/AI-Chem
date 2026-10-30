# Set before package submodules are imported. Invoke Python with -B as well.
import sys
sys.dont_write_bytecode = True
from .cli import main
raise SystemExit(main())
