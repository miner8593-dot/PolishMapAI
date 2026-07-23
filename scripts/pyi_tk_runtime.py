import os
import sys

bundle = getattr(sys, "_MEIPASS", "")
if bundle:
    # Tcl 8.6.15 on Windows may reject the backslash form injected by the
    # stock PyInstaller hook even though init.tcl exists. Tcl always accepts
    # its native forward-slash path form.
    os.environ["TCL_LIBRARY"] = os.path.join(bundle, "_tcl_data").replace("\\", "/")
    os.environ["TK_LIBRARY"] = os.path.join(bundle, "_tk_data").replace("\\", "/")
