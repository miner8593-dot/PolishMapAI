import os
import sys

bundle = getattr(sys, "_MEIPASS", "")
if bundle:
    os.environ.setdefault("TCL_LIBRARY", os.path.join(bundle, "_tcl_data"))
    os.environ.setdefault("TK_LIBRARY", os.path.join(bundle, "_tk_data"))
