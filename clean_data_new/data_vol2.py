from pathlib import Path
from datetime import datetime

out = Path("Data2.txt")
with out.open("a") as f:
    f.write(f"Hello docker data2 volume! [{datetime.now()}]\n")